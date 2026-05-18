import json
import os
import re
import traceback
from collections import defaultdict

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_REGISTRY
from events import push_event


_history = defaultdict(list)


def reset_session(session_id):
    if session_id in _history:
        del _history[session_id]


def respond(session_id, caller_phone, utterance, persona=None):
    utterance = (utterance or "").strip()
    if not utterance:
        return "I heard silence. Tell me what you need changed, and I’ll help."

    print(f"[Respond] session={session_id} caller={caller_phone} utterance={utterance!r} persona={persona}", flush=True)
    _history[session_id].append({"role": "user", "content": utterance})
    push_event("agent_transcript", {"caller_phone": caller_phone, "text": utterance, "persona": persona})

    scenario = _scenario_for(persona, utterance)
    print(f"[Respond] scenario={scenario}", flush=True)

    if scenario == "uber":
        from agent.brain_uber import respond_uber

        final = respond_uber(session_id, caller_phone, utterance, persona, _deps(session_id))
    elif scenario == "walmart":
        from agent.brain_walmart import respond_walmart

        final = respond_walmart(session_id, caller_phone, utterance, persona, _deps(session_id))
    else:
        final = _apply_persona_prefix(
            "I can help with your ride or Walmart order. What do you need changed?",
            persona,
        )

    _history[session_id].append({"role": "agent", "content": final})
    push_event("agent_response", {"text": final, "persona": persona})
    return final


def _scenario_for(persona, utterance):
    role = persona.get("role") if isinstance(persona, dict) else None
    if role == "uber_driver":
        return "uber"
    if role == "walmart_cs":
        return "walmart"
    return _route_by_text(utterance)


def _route_by_text(utterance):
    text = utterance.lower()
    if re.search(r"\b(walmart|grocery|cereal|substitute|substitution)\b", text):
        return "walmart"
    if re.search(r"\b(terminal|uber|ride|driver|pickup|dropoff|reroute|door)\b", text):
        return "uber"
    if re.search(r"\bdrop\s*off\b", text):
        return "uber"
    return "none"


def _persona_block(persona):
    if not isinstance(persona, dict):
        return None
    name = persona.get("name")
    role = persona.get("role")
    if not name or not role:
        return None
    if role == "uber_driver":
        voice = (
            "You are texting AS the Uber driver named " + name + ". "
            "Reply in first person, casual, short (max 2 sentences), no formalities, no mention of being an AI or assistant. "
            "Confirm the action like a real driver would."
        )
    elif role == "walmart_cs":
        voice = (
            "You are texting AS a Walmart Grocery support agent (sign as " + name + "). "
            "Reply in first person, polite and professional, max 2 short sentences, no mention of AI. "
            "Reference the order/item naturally."
        )
    else:
        voice = "You are texting AS " + name + ". Reply in first person, short, no mention of being an AI."
    return {"name": name, "role": role, "instruction": voice}


def _apply_persona_prefix(body, persona):
    block = _persona_block(persona)
    if not block:
        return body
    name = block["name"]
    role = block["role"]
    if role == "uber_driver":
        return f"Hey, this is {name}. {body}"
    if role == "walmart_cs":
        return f"Hi, this is {name} from Walmart. {body}"
    return f"{name}: {body}"


def _client():
    if os.getenv("CONCORDE_OFFLINE_TESTS"):
        print("[Gemini] client unavailable: offline_tests", flush=True)
        return None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[Gemini] client unavailable: no_api_key", flush=True)
        push_event("gemini_unavailable", {"reason": "no_api_key"})
        return None
    try:
        from google import genai
    except Exception as error:
        print(f"[Gemini] client unavailable: sdk_import_failed: {error}", flush=True)
        push_event("gemini_unavailable", {"error": str(error)})
        return None
    return genai.Client(api_key=api_key)


def _gemini_model_name():
    return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


def _execute_plan(plan, context):
    results = []
    calls = plan.get("tool_calls", []) if isinstance(plan, dict) else []
    for call in calls[:5]:
        name = call.get("name")
        args = call.get("args") or {}
        tool = TOOL_REGISTRY.get(name)
        print(f"[Tool] -> {name} args={json.dumps(args, default=str)[:300]}", flush=True)
        if not tool:
            print(f"[Tool] {name} unknown", flush=True)
            results.append({"name": name, "ok": False, "error": "unknown_tool"})
            continue
        try:
            result = tool(args, context)
            summary = _summarize(result)
            print(f"[Tool] <- {name} ok result={json.dumps(summary, default=str)[:300]}", flush=True)
            results.append({"name": name, "ok": True, "result": summary})
        except Exception as error:
            print(f"[Tool] <- {name} FAILED: {error}\n{traceback.format_exc()}", flush=True)
            results.append({"name": name, "ok": False, "error": str(error)})
            push_event("tool_failed", {"tool": name, "error": str(error)})
    return results


def _summarize(value):
    if isinstance(value, dict):
        return value
    return {"value": value}


def _extract_text(response):
    if hasattr(response, "text"):
        return response.text
    return str(response)


def _parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


def _deps(session_id):
    return {
        "client": _client,
        "model_name": _gemini_model_name,
        "history": _history[session_id],
        "execute_plan": _execute_plan,
        "apply_persona_prefix": _apply_persona_prefix,
        "persona_block": _persona_block,
        "parse_json": _parse_json,
        "extract_text": _extract_text,
        "system_prompt": SYSTEM_PROMPT,
    }
