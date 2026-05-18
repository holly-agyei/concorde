import json
import os
import re
import time
import uuid
from collections import defaultdict

from events import push_event
from integrations.browser_walmart import run_walmart_browser_task


_sessions = defaultdict(lambda: {"messages": [], "runs": []})


WALMART_TASK_PROMPT = """You are Concorde's BrowserUseAgent for Walmart.

You are operating the user's own Walmart account in a Browser Use cloud browser profile.
Use Walmart.com purchase history, active orders, grocery order details, and editable substitution screens when available.

Caller request:
{latest_message}

Recent conversation:
{history}

Execution rules:
- First inspect the live Walmart account/order state. Do not invent order status.
- If the request is ambiguous, still open Walmart and find the relevant active/editable order, then report the options or the exact question needed.
- If Walmart requires login, 2FA, CAPTCHA, unavailable account access, or no editable order exists, stop and report that blocker.
- Do not buy, cancel, pay, refund, submit delivery changes, or save final substitutions unless the caller clearly confirmed and the server says saving is allowed.
- If saving is not allowed, stop before the final irreversible button and report exactly what would change.
- Keep the final result short enough for a text message.
"""


def handle_walmart_text(session_id, caller_phone, message, source="api"):
    message = (message or "").strip()
    session_id = session_id or f"walmart-{uuid.uuid4().hex[:10]}"
    session = _sessions[session_id]

    if not message:
        reply = "Tell me what you want changed on your Walmart order, and I’ll open Walmart to check it."
        _append(session, "agent", reply)
        return {
            "session_id": session_id,
            "reply": reply,
            "browser_use": {"status": "not_started", "reason": "empty_message"},
        }

    _append(session, "user", message)
    push_event(
        "walmart_text_received",
        {"session_id": session_id, "caller_phone": caller_phone, "source": source, "text": message},
    )

    plan = _plan_with_gemini(session["messages"], message)
    caller_confirmed = bool(plan.get("caller_confirmed_irreversible")) or _caller_confirmed_irreversible_action(message)
    task = plan.get("browser_task") or _build_browser_task(session["messages"], message)

    if plan.get("needs_clarification") and not plan.get("should_browse", True):
        reply = plan.get("clarifying_question") or "What would you like changed on the Walmart order?"
        _append(session, "agent", reply)
        return {
            "session_id": session_id,
            "reply": reply,
            "browser_use": {"status": "not_started", "reason": "needs_clarification"},
        }

    result = run_walmart_browser_task(
        task,
        caller_confirmed=caller_confirmed,
        force_browser=True,
        session_id=session_id,
    )

    reply = _reply_from_browser_result(result, caller_confirmed)
    _append(session, "agent", reply)

    run_record = {
        "id": f"wbr_{uuid.uuid4().hex[:12]}",
        "created_at": time.time(),
        "caller_confirmed": caller_confirmed,
        "request": message,
        "browser_use": _public_browser_result(result),
    }
    session["runs"].append(run_record)
    session["runs"] = session["runs"][-12:]

    push_event(
        "walmart_text_replied",
        {
            "session_id": session_id,
            "reply": reply,
            "browser_status": result.get("status"),
            "allow_save": result.get("allow_save", False),
        },
    )

    return {
        "session_id": session_id,
        "reply": reply,
        "browser_use": _public_browser_result(result),
        "run": run_record,
    }


def get_walmart_session(session_id):
    return _sessions.get(session_id, {"messages": [], "runs": []})


def reset_walmart_session(session_id):
    if session_id in _sessions:
        del _sessions[session_id]


def is_walmart_message(message):
    text = (message or "").lower()
    return any(
        marker in text
        for marker in [
            "walmart",
            "grocery",
            "order",
            "substitute",
            "substitution",
            "replace",
            "cereal",
            "cart",
            "delivery",
            "pickup",
        ]
    )


def _append(session, role, content):
    session["messages"].append({"role": role, "content": content, "at": time.time()})
    session["messages"] = session["messages"][-16:]


def _build_browser_task(messages, latest_message):
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in messages[-8:]
    ]
    return WALMART_TASK_PROMPT.format(
        latest_message=latest_message,
        history=json.dumps(history, indent=2),
    )


def _plan_with_gemini(messages, latest_message):
    if os.getenv("CONCORDE_OFFLINE_TESTS") or not os.getenv("GEMINI_API_KEY"):
        return {"should_browse": True}
    try:
        from google import genai
    except Exception as error:
        push_event("gemini_walmart_unavailable", {"error": str(error)})
        return {"should_browse": True}

    prompt = {
        "role": "Concorde WalmartNegotiationAgent and BrowserUseAgent",
        "instruction": (
            "Return JSON only. Decide how to turn the caller's Walmart text into a Browser Use task. "
            "This is a real Walmart account workflow. Be natural, but do not allow irreversible saves unless the caller clearly confirmed."
        ),
        "latest_message": latest_message,
        "history": [
            {"role": item["role"], "content": item["content"]}
            for item in messages[-8:]
        ],
        "return_shape": {
            "should_browse": True,
            "needs_clarification": False,
            "clarifying_question": "",
            "caller_confirmed_irreversible": False,
            "browser_task": "Specific Browser Use task for Walmart.com",
        },
    }

    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        response = client.models.generate_content(model=model, contents=json.dumps(prompt, indent=2))
        plan = _parse_json(getattr(response, "text", str(response)))
        if isinstance(plan, dict):
            push_event(
                "gemini_walmart_plan",
                {
                    "should_browse": plan.get("should_browse"),
                    "needs_clarification": plan.get("needs_clarification"),
                    "confirmed": plan.get("caller_confirmed_irreversible"),
                },
            )
            return plan
    except Exception as error:
        push_event("gemini_walmart_plan_failed", {"error": str(error)})
    return {"should_browse": True}


def _parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


def _caller_confirmed_irreversible_action(message):
    text = (message or "").lower()
    if re.search(r"\b(no|don't|do not|not yet|wait|stop|hold on)\b", text):
        return False
    return bool(
        re.search(
            r"\b(yes|confirm|confirmed|approve|approved|apply|save|submit|go ahead|do it|that works)\b",
            text,
        )
    )


def _reply_from_browser_result(result, caller_confirmed):
    status = result.get("status")
    if status == "completed":
        output = str(result.get("output") or "").strip()
        if output:
            return _clean_text(output)
        if result.get("allow_save"):
            return "Done. Walmart accepted the confirmed change."
        return "I checked Walmart and stopped before saving anything. Tell me if you want me to apply the change."

    if status == "dry_run":
        return (
            "Dry run is on. I built the Walmart Browser Use task and would open your live Walmart order now. "
            "Turn off dry run to execute it."
        )

    if status == "blocked":
        reason = result.get("reason") or "Browser Use is blocked"
        return f"I couldn’t open Walmart through Browser Use yet: {reason}. Once that is fixed, send the request again."

    if status == "skipped":
        return "Browser Use is not enabled for Walmart yet. Set Walmart mode to browser and send the request again."

    if caller_confirmed:
        return "I received the confirmation, but Walmart did not return a completed browser result."
    return "I started checking Walmart, but I need one more clear instruction before saving any change."


def _clean_text(value):
    value = re.sub(r"\s+", " ", value).strip()
    return value[:900]


def _public_browser_result(result):
    public = dict(result)
    task = public.get("task")
    if task and len(task) > 1200:
        public["task"] = task[:1200] + "..."
    return public
