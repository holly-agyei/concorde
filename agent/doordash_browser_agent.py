import json
import os
import re
import time
import uuid
from collections import defaultdict

from events import push_event
from integrations.doordash_browser import run_doordash_browser_task


_sessions = defaultdict(lambda: {"messages": [], "runs": []})

GEMINI_MODEL = "gemini-2.5-pro"

# Routing keywords ONLY — this is just to decide whether an inbound SMS
# should be routed to the DoorDash agent at all. It does NOT decide intent,
# does NOT extract anything, and is NOT used by handle_doordash_text.
_DOORDASH_ROUTING_KEYWORDS = (
    "doordash",
    "door dash",
    "restaurant",
    "food delivery",
    "cart",
    "pizza",
    "burger",
    "sushi",
    "taco",
    "burrito",
    "remove",
    "replace",
    "swap",
)


DOORDASH_AGENT_PROMPT = """You are Concorde, a careful DoorDash customer support agent in a WhatsApp-style chat.

You can control a real visible Chrome browser on the user's DoorDash account to perform these actions:
- "add"        — add a SPECIFIC named item from a SPECIFIC (or clearly nearby) restaurant
- "remove"     — remove a SPECIFIC named item currently in the cart
- "replace"    — swap one SPECIFIC named item for another SPECIFIC named item
- "view_cart"  — show what is currently in the cart
- "search"     — search for a SPECIFIC restaurant or dish

CRITICAL RULE: should_browse DEFAULTS TO false.
Launching the browser opens a visible Chrome window on the user's screen. It is
expensive and disruptive. NEVER set should_browse=true unless you are confident
the user has given you a fully-specified, actionable request RIGHT NOW.

When in doubt, ASK ONE friendly clarifying question. Multi-turn conversation
is encouraged. Re-read the conversation history before deciding — if you
already asked a clarifying question and the user has now answered it, you may
combine the prior context with the new answer to act.

should_browse MUST be false for:
- Greetings: "hi", "hello", "hey", "good morning", "yo", "sup"
- Small talk / acknowledgements: "thanks", "ok", "cool", "great", "got it"
- Vague problem statements: "i have a problem with my order", "something is
  wrong", "my order is messed up", "fix my order", "i need help"
- Questions about capabilities: "what can you do", "how does this work"
- Incomplete actions missing the target item:
    "add something", "remove an item", "swap my order", "change my order"
- Incomplete actions missing the restaurant for an ADD:
    "add pizza to my cart"          → ask which restaurant or what kind
    "get me a burger"               → ask which restaurant
    "order tacos"                   → ask which restaurant or what kind of tacos
- Hypothetical / future tense: "i might want pizza later", "what if i want sushi"
- Single ambiguous words: "food", "hungry", "lunch"

should_browse MAY be true ONLY when ALL of these hold:
1. The user named a SPECIFIC action (add / remove / replace / view cart / search).
2. For "add": the user named a SPECIFIC dish AND a restaurant (or said
   "any nearby <cuisine> place" / "from any <cuisine> place" — that counts
   as a restaurant choice).
3. For "remove": the user named a SPECIFIC item already in the cart.
4. For "replace": BOTH the old item and the new item are named.
5. For "view_cart" / "search": the intent is unambiguous.
6. The user is asking right NOW, not hypothetically.
7. Nothing important is missing.

POSITIVE EXAMPLES (should_browse=true):
- "add a pepperoni pizza from any nearby pizza place"
    → action: "add", search_term: "pepperoni pizza"
- "add tacos from Taco Bell"
    → action: "add", search_term: "tacos from Taco Bell"
- "remove the fries"
    → action: "remove", remove_query: "fries"
- "swap the burger for sushi from any nearby sushi place"
    → action: "replace", remove_query: "burger", search_term: "sushi"
- "what's in my cart"
    → action: "view_cart"
- "find Thai food near me"
    → action: "search", search_term: "Thai food"

NEGATIVE EXAMPLES (should_browse=false, write a reply that asks a question):
- "hi"
    → reply: "Hey! What can I help you with on DoorDash today?"
- "i have a problem with my order"
    → reply: "I'm sorry to hear that. What's going on with your order? I can
       remove an item, replace something, or check your cart."
- "add pizza to my cart"
    → reply: "Got it — pizza from anywhere in particular, or should I pick
       any nearby pizza place? And any topping preference?"
- "add something"
    → reply: "Sure — what would you like me to add, and from which restaurant?"
- "remove an item"
    → reply: "Which item should I remove from your cart?"
- "swap my order"
    → reply: "What would you like to swap, and what should it become?"
- "thanks"
    → reply: "You're welcome! Let me know if you need anything else."

CLEAN EXTRACTION RULES (only relevant when should_browse=true):
The browser layer trusts your `search_term` and `remove_query` VERBATIM and types
them straight into search boxes. Provide ONLY the bare item / dish / restaurant.
- DO NOT include verbs like "add", "remove", "get me", "order", "find".
- DO NOT include filler like "to my cart", "from my cart", "please", "for me",
  "some", "a", "an", "the".
- "add pepperoni pizza to my cart"     → search_term: "pepperoni pizza"
- "can you get me some tacos please"   → search_term: "tacos"
- "remove the fries from my cart"      → remove_query: "fries"
- "add tacos from Taco Bell"           → search_term: "tacos from Taco Bell"
  (Restaurant context inside search_term is fine when the user named one.)

Return ONLY valid JSON in this exact shape (no markdown, no prose, no code fences):
{
  "should_browse": false,
  "reply": "Conversational reply when NOT browsing (REQUIRED if should_browse is false). Ask one clear clarifying question or acknowledge politely.",
  "action": "add | remove | replace | view_cart | search",
  "search_term": "bare item / dish / restaurant name only — empty string if not applicable",
  "remove_query": "bare cart item to remove only — empty string if not applicable",
  "browser_task": "Detailed instruction for the browser agent (REQUIRED if should_browse is true). Must say 'never checkout or buy anything'.",
  "reason": "one short internal sentence explaining the decision"
}
"""


FAILURE_REPLY = (
    "Sorry, I'm having trouble understanding right now — could you rephrase "
    "what you'd like me to do on DoorDash?"
)


def handle_doordash_text(session_id, caller_phone, message, source="api"):
    message = (message or "").strip()
    session_id = session_id or f"doordash-{uuid.uuid4().hex[:10]}"
    session = _sessions[session_id]

    if not message:
        reply = "Hey! I'm your DoorDash assistant. What can I help you with today?"
        _append(session, "agent", reply)
        return {
            "session_id": session_id,
            "reply": reply,
            "doordash_browser": {"status": "not_started", "reason": "empty_message"},
        }

    _append(session, "user", message)
    push_event(
        "doordash_text_received",
        {"session_id": session_id, "caller_phone": caller_phone, "source": source, "text": message},
    )

    plan = _plan_with_gemini(session["messages"], message)

    # Gemini failed entirely (no key, exception, malformed JSON) — graceful
    # conversational reply. We NEVER fall back to launching the browser.
    if plan is None:
        reply = FAILURE_REPLY
        _append(session, "agent", reply)
        push_event(
            "doordash_text_replied",
            {"session_id": session_id, "reply": reply, "browser_status": "skipped"},
        )
        return {
            "session_id": session_id,
            "reply": reply,
            "doordash_browser": {"status": "not_started", "reason": "gemini_unavailable"},
        }

    # Gemini decided: just chat / clarify — no browser
    if not plan.get("should_browse"):
        reply = (plan.get("reply") or "").strip() or "What would you like to do on DoorDash?"
        _append(session, "agent", reply)
        push_event(
            "doordash_text_replied",
            {"session_id": session_id, "reply": reply, "browser_status": "skipped"},
        )
        return {
            "session_id": session_id,
            "reply": reply,
            "doordash_browser": {"status": "not_started", "reason": "conversational"},
        }

    # Gemini decided: launch the browser
    task = (plan.get("browser_task") or "").strip()
    if not task:
        task = (
            f"Handle this DoorDash request in visible Chrome: {message}. "
            f"Never checkout or buy anything."
        )

    result = run_doordash_browser_task(task, session_id=session_id, plan=plan)
    reply = _reply_from_result(result)
    _append(session, "agent", reply)

    run_record = {
        "id": f"ddr_{uuid.uuid4().hex[:12]}",
        "created_at": time.time(),
        "request": message,
        "plan": _public_plan(plan),
        "doordash_browser": result,
    }
    session["runs"].append(run_record)
    session["runs"] = session["runs"][-12:]

    push_event(
        "doordash_text_replied",
        {
            "session_id": session_id,
            "reply": reply,
            "browser_status": result.get("status"),
            "action": plan.get("action"),
        },
    )

    return {
        "session_id": session_id,
        "reply": reply,
        "doordash_browser": result,
        "run": run_record,
    }


def get_doordash_session(session_id):
    return _sessions.get(session_id, {"messages": [], "runs": []})


def reset_doordash_session(session_id):
    if session_id in _sessions:
        del _sessions[session_id]


def is_doordash_message(message):
    """Routing helper for inbound SMS. Pure keyword check — NOT used for
    intent extraction. Intent always goes through Gemini."""
    text = (message or "").lower()
    return any(marker in text for marker in _DOORDASH_ROUTING_KEYWORDS)


def _append(session, role, content):
    session["messages"].append({"role": role, "content": content, "at": time.time()})
    session["messages"] = session["messages"][-16:]


def _plan_with_gemini(messages, latest_message):
    """Ask Gemini to decide should_browse + extract clean fields. Returns
    None on any failure (no key, SDK missing, exception, bad JSON). The
    caller treats None as a graceful failure — it does NOT browse."""
    if os.getenv("CONCORDE_OFFLINE_TESTS"):
        push_event("gemini_doordash_plan_failed", {"error": "offline_tests_enabled"})
        return None
    if not os.getenv("GEMINI_API_KEY"):
        push_event("gemini_doordash_plan_failed", {"error": "missing_GEMINI_API_KEY"})
        return None

    try:
        from google import genai
        from google.genai import types as genai_types
    except Exception as error:
        push_event("gemini_doordash_plan_failed", {"error": f"sdk_import_failed: {error}"})
        return None

    # Always send the full recent conversation so Gemini can reason about
    # clarifications it has already asked the user.
    history = [{"role": m["role"], "content": m["content"]} for m in messages[-12:]]
    user_prompt = (
        "Conversation so far (oldest first):\n"
        f"{json.dumps(history, indent=2)}\n\n"
        f"Latest message from user: {json.dumps(latest_message)}\n\n"
        "Decide whether to respond conversationally or to launch the visible "
        "Chrome DoorDash browser. Remember: default to should_browse=false and "
        "ask a clarifying question unless the request is fully specified.\n"
        "Return ONLY the JSON object described in the system instruction."
    )

    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        model = os.getenv("GEMINI_MODEL", GEMINI_MODEL)
        config = genai_types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            system_instruction=DOORDASH_AGENT_PROMPT,
        )
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config,
        )
        text = getattr(response, "text", None) or str(response)
    except Exception as error:
        push_event("gemini_doordash_plan_failed", {"error": str(error)})
        return None

    try:
        plan = _parse_json(text)
    except Exception as error:
        push_event(
            "gemini_doordash_plan_failed",
            {"error": f"json_parse_failed: {error}", "raw": (text or "")[:400]},
        )
        return None

    if not isinstance(plan, dict):
        push_event(
            "gemini_doordash_plan_failed",
            {"error": "plan_not_object", "raw": (text or "")[:400]},
        )
        return None

    # Normalize fields without any regex-based intent inference. We only
    # coerce types and trim whitespace — Gemini owns the values.
    plan["should_browse"] = bool(plan.get("should_browse"))
    plan["reply"] = (plan.get("reply") or "").strip()
    plan["search_term"] = (plan.get("search_term") or "").strip()
    plan["remove_query"] = (plan.get("remove_query") or "").strip()
    plan["browser_task"] = (plan.get("browser_task") or "").strip()
    plan["reason"] = (plan.get("reason") or "").strip()
    action = (plan.get("action") or "").strip().lower()
    if action not in {"add", "remove", "replace", "view_cart", "search"}:
        action = "" if not plan["should_browse"] else "add"
    plan["action"] = action

    push_event(
        "gemini_doordash_plan",
        {
            "should_browse": plan["should_browse"],
            "action": plan["action"],
            "search_term": plan["search_term"],
            "reason": plan["reason"],
        },
    )
    return plan


def _reply_from_result(result):
    status = result.get("status")
    if status == "completed":
        return result.get("output") or "Done — I stopped before checkout."
    if status == "dry_run":
        action = (result.get("plan") or {}).get("action", "task")
        return f"Dry run is on. I planned the DoorDash {action} step but did not open Chrome."
    reason = result.get("reason") or result.get("message") or "DoorDash browser automation is blocked"
    return f"I could not complete that: {reason}"


def _parse_json(text):
    """Tolerant JSON extraction. Regex here is ONLY for stripping markdown
    code fences off Gemini's response — it is NOT used to understand user
    intent or extract search terms."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        # Last resort: grab the first {...} block. Still no intent parsing.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _public_plan(plan):
    public = dict(plan or {})
    task = public.get("browser_task")
    if task and len(task) > 900:
        public["browser_task"] = task[:900] + "..."
    return public
