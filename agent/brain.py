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


def respond(session_id, caller_phone, utterance):
    utterance = (utterance or "").strip()
    if not utterance:
        return "I heard silence. Tell me what you need changed, and I’ll help."

    _history[session_id].append({"role": "user", "content": utterance})
    push_event("agent_transcript", {"caller_phone": caller_phone, "text": utterance})

    plan = _plan_with_gemini(session_id, caller_phone, utterance) or _fallback_plan(utterance)
    tool_results = _execute_plan(plan, {"caller_phone": caller_phone, "session_id": session_id})

    final = _final_with_gemini(session_id, utterance, tool_results, plan) or _fallback_final(utterance, tool_results, plan)
    _history[session_id].append({"role": "agent", "content": final})
    push_event("agent_response", {"text": final})
    return final


def _model():
    if os.getenv("CONCORDE_OFFLINE_TESTS"):
        return None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
    except Exception as error:
        push_event("gemini_unavailable", {"error": str(error)})
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))


def _plan_with_gemini(session_id, caller_phone, utterance):
    model = _model()
    if not model:
        return None
    context = {
        "caller_phone": caller_phone,
        "history": _history[session_id][-6:],
        "latest_utterance": utterance,
    }
    prompt = f"{SYSTEM_PROMPT}\n\n{PLANNER_PROMPT}\n\nContext:\n{json.dumps(context, indent=2)}"
    try:
        response = model.generate_content(prompt)
        text = _extract_text(response)
        plan = _parse_json(text)
        if isinstance(plan, dict):
            push_event("gemini_plan", {"reason": plan.get("reason"), "tool_count": len(plan.get("tool_calls", []))})
            return plan
    except Exception as error:
        push_event("gemini_plan_failed", {"error": str(error)})
    return None


def _final_with_gemini(session_id, utterance, tool_results, plan):
    model = _model()
    if not model:
        return None
    context = {
        "history": _history[session_id][-8:],
        "latest_utterance": utterance,
        "plan": plan,
        "tool_results": tool_results,
    }
    prompt = f"{SYSTEM_PROMPT}\n\n{FINAL_PROMPT}\n\nContext:\n{json.dumps(context, indent=2, default=str)}"
    try:
        response = model.generate_content(prompt)
        text = _extract_text(response).strip()
        if text:
            return text[:700]
    except Exception as error:
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
    if any(word in text for word in ["walmart", "cereal", "substitute", "substitution", "order"]):
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


def _fallback_final(utterance, tool_results, plan):
    names = [result["name"] for result in tool_results if result.get("ok")]
    if "reroute_uber_driver" in names:
        reroute = next(result["result"] for result in tool_results if result["name"] == "reroute_uber_driver")
        destination = reroute["destination"]["label"]
        eta = reroute.get("eta_minutes")
        return f"Got it. I updated your driver’s route to {destination}. They should meet you there in about {eta} minutes."
    if "apply_walmart_substitution" in names:
        result = next(result["result"] for result in tool_results if result["name"] == "apply_walmart_substitution")
        if result.get("applied"):
            return f"Done. I applied the substitution from {result['substitution']['from']} to {result['substitution']['to']}."
    if "propose_walmart_substitution" in names:
        result = next(result["result"] for result in tool_results if result["name"] == "propose_walmart_substitution")
        pending = result["pending"]
        return f"I found your Walmart order. {pending['from']} is unavailable. {pending['to']} is in stock and matches your history. Want me to apply that substitution?"
    return plan.get("direct_response") or "I can help with that. Tell me whether this is for your ride or your Walmart order."


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
