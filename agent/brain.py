import json
import os
import re
from collections import defaultdict

from agent.prompts import FINAL_PROMPT, PLANNER_PROMPT, SYSTEM_PROMPT
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

    _history[session_id].append({"role": "user", "content": utterance})
    push_event("agent_transcript", {"caller_phone": caller_phone, "text": utterance, "persona": persona})

    plan = _plan_with_gemini(session_id, caller_phone, utterance, persona) or _fallback_plan(utterance)
    tool_results = _execute_plan(plan, {"caller_phone": caller_phone, "session_id": session_id})

    final = (
        _final_with_gemini(session_id, utterance, tool_results, plan, persona)
        or _fallback_final(utterance, tool_results, plan, persona)
    )
    _history[session_id].append({"role": "agent", "content": final})
    push_event("agent_response", {"text": final, "persona": persona})
    return final


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


def _client():
    if os.getenv("CONCORDE_OFFLINE_TESTS"):
        return None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
    except Exception as error:
        print(f"[Gemini] unavailable: {error}")
        push_event("gemini_unavailable", {"error": str(error)})
        return None
    return genai.Client(api_key=api_key)


def _gemini_model_name():
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _plan_with_gemini(session_id, caller_phone, utterance, persona=None):
    client = _client()
    if not client:
        return None
    context = {
        "caller_phone": caller_phone,
        "history": _history[session_id][-6:],
        "latest_utterance": utterance,
        "persona": _persona_block(persona),
    }
    prompt = f"{SYSTEM_PROMPT}\n\n{PLANNER_PROMPT}\n\nContext:\n{json.dumps(context, indent=2)}"
    try:
        response = client.models.generate_content(model=_gemini_model_name(), contents=prompt)
        text = _extract_text(response)
        plan = _parse_json(text)
        if isinstance(plan, dict):
            print(f"[Gemini] plan: {plan.get('reason')} | tools: {[c.get('name') for c in plan.get('tool_calls', [])]}")
            push_event("gemini_plan", {"reason": plan.get("reason"), "tool_count": len(plan.get("tool_calls", []))})
            return plan
    except Exception as error:
        print(f"[Gemini] plan failed: {error}")
        push_event("gemini_plan_failed", {"error": str(error)})
    return None


def _final_with_gemini(session_id, utterance, tool_results, plan, persona=None):
    client = _client()
    if not client:
        return None
    context = {
        "history": _history[session_id][-8:],
        "latest_utterance": utterance,
        "plan": plan,
        "tool_results": tool_results,
        "persona": _persona_block(persona),
    }
    prompt = f"{SYSTEM_PROMPT}\n\n{FINAL_PROMPT}\n\nContext:\n{json.dumps(context, indent=2, default=str)}"
    try:
        response = client.models.generate_content(model=_gemini_model_name(), contents=prompt)
        text = _extract_text(response).strip()
        if text:
            print(f"[Gemini] final: {text[:200]}")
            return text[:700]
    except Exception as error:
        print(f"[Gemini] final failed: {error}")
        push_event("gemini_final_failed", {"error": str(error)})
    return None


def _execute_plan(plan, context):
    results = []
    calls = plan.get("tool_calls", []) if isinstance(plan, dict) else []
    for call in calls[:5]:
        name = call.get("name")
        args = call.get("args") or {}
        tool = TOOL_REGISTRY.get(name)
        if not tool:
            results.append({"name": name, "ok": False, "error": "unknown_tool"})
            continue
        try:
            result = tool(args, context)
            results.append({"name": name, "ok": True, "result": _summarize(result)})
        except Exception as error:
            results.append({"name": name, "ok": False, "error": str(error)})
            push_event("tool_failed", {"tool": name, "error": str(error)})
    return results


def _fallback_plan(utterance):
    text = utterance.lower()
    if any(word in text for word in ["walmart", "cereal", "substitute", "substitution"]) or (
        "order" in text and "walmart" in text
    ):
        confirmed = bool(re.search(r"\b(yes|confirm|approved|do it|save it|apply)\b", text))
        if confirmed:
            return {
                "tool_calls": [
                    {"name": "lookup_walmart_order", "args": {}},
                    {"name": "apply_walmart_substitution", "args": {}},
                ],
                "reason": "caller confirmed pending Walmart substitution",
            }
        return {
            "tool_calls": [
                {"name": "lookup_walmart_order", "args": {}},
                {"name": "semantic_lookup", "args": {"query": "Walmart cereal substitution policy customer preference"}},
                {
                    "name": "propose_walmart_substitution",
                    "args": {"item_name": "cereal", "substitute_name": "Cinnamon Oat Squares"},
                },
                {
                    "name": "run_walmart_browser_task",
                    "args": {
                        "task": "Inspect Walmart substitution options for Honey Crunch Cereal and Cinnamon Oat Squares.",
                        "caller_confirmed": False,
                    },
                },
            ],
            "reason": "fallback Walmart substitution negotiation",
        }

    if any(word in text for word in ["doordash", "door dash", "restaurant", "food", "cart", "pizza", "burger", "sushi"]):
        action = "add"
        remove_query = ""
        search_term = _extract_doordash_search_term(utterance)
        replace = re.search(r"\b(?:replace|swap|change)\s+(.+?)\s+(?:with|for|to)\s+(.+)$", utterance, re.I)
        remove = re.search(r"\b(?:remove|delete|take out)\s+(.+?)(?:\s+from\s+(?:my\s+)?cart|$)", utterance, re.I)
        if replace:
            action = "replace"
            remove_query = _clean_doordash_term(replace.group(1))
            search_term = _clean_doordash_term(replace.group(2))
        elif remove:
            action = "remove"
            remove_query = _clean_doordash_term(remove.group(1))
            search_term = ""
        elif any(marker in text for marker in ["show cart", "view cart", "check cart"]):
            action = "view_cart"
            search_term = ""
        return {
            "tool_calls": [
                {
                    "name": "run_doordash_browser_task",
                    "args": {
                        "task": f"Handle this DoorDash cart request safely without checkout: {utterance}",
                        "action": action,
                        "search_term": search_term,
                        "remove_query": remove_query,
                    },
                }
            ],
            "reason": "fallback DoorDash browser cart workflow",
        }

    if any(word in text for word in ["terminal", "pickup", "dropoff", "driver", "uber", "ride", "door", "reroute"]):
        destination = "SFO Terminal D" if "d" in text or "wrong" in text else "SFO Terminal C"
        if "tower 2" in text:
            destination = "Salesforce Tower 2"
        return {
            "tool_calls": [
                {"name": "lookup_uber_trip", "args": {}},
                {"name": "semantic_lookup", "args": {"query": f"{destination} ride reroute driver safety policy"}},
                {"name": "reroute_uber_driver", "args": {"destination_label": destination}},
            ],
            "reason": "fallback Uber reroute negotiation",
        }

    return {
        "tool_calls": [],
        "direct_response": "I can help with your ride or Walmart order. What do you need changed?",
        "reason": "fallback general response",
    }


def _fallback_final(utterance, tool_results, plan, persona=None):
    names = [result["name"] for result in tool_results if result.get("ok")]
    body = None
    if "reroute_uber_driver" in names:
        reroute = next(result["result"] for result in tool_results if result["name"] == "reroute_uber_driver")
        destination = reroute["destination"]["label"]
        eta = reroute.get("eta_minutes")
        body = f"Heading to {destination} now — see you in about {eta} min."
    elif "apply_walmart_substitution" in names:
        result = next(result["result"] for result in tool_results if result["name"] == "apply_walmart_substitution")
        if result.get("applied"):
            body = f"Done — swapped {result['substitution']['from']} for {result['substitution']['to']} on your order."
    elif "propose_walmart_substitution" in names:
        result = next(result["result"] for result in tool_results if result["name"] == "propose_walmart_substitution")
        pending = result["pending"]
        body = (
            f"Quick heads-up: {pending['from']} is out of stock. "
            f"We can swap it for {pending['to']} — want me to apply that?"
        )
    elif "run_doordash_browser_task" in names:
        result = next(result["result"] for result in tool_results if result["name"] == "run_doordash_browser_task")
        body = result.get("output") or result.get("message") or "I opened DoorDash and stopped before checkout."
    if body is None:
        body = plan.get("direct_response") or "Can you tell me a bit more about what you need?"
    return _apply_persona_prefix(body, persona)


def _extract_doordash_search_term(message):
    match = re.search(r"(?:add|order|get|find|search for|look for)\s+(.+?)(?:\s+(?:on|from|to)\s+doordash|$)", message, re.I)
    if match:
        return _clean_doordash_term(match.group(1))
    return "pizza"


def _clean_doordash_term(value):
    value = re.sub(r"\b(to cart|to my cart|in cart|in my cart|without buying|without checkout|do not buy|don't buy|please)\b", "", str(value), flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" .,")
    return value[:90]


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


def _summarize(value):
    if isinstance(value, dict):
        return value
    return {"value": value}
