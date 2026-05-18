import json
import re
import traceback

from events import push_event


PLANNER_PROMPT_UBER = """Return JSON only. Decide which Uber tools to call for the caller's latest utterance.
Available tools:
- lookup_uber_trip
- reroute_uber_driver with {"destination_label": "..."}
- semantic_lookup with {"query": "..."}

Valid `destination_label` values (use one of these EXACTLY):
- "SFO Terminal 1"
- "SFO Terminal 2"
- "SFO Terminal 3"
- "SFO International Terminal"
- "Salesforce Tower 2"

Reroute rules — read carefully, the wrong terminal ruins the demo:
- If the caller names a terminal number (1, 2, or 3) or "International" / "Intl" in the latest utterance, `destination_label` MUST match that exact terminal. Echo the caller's number; never substitute another.
- If the latest utterance is ambiguous (e.g. "the terminal", "change it", "wrong place") and no number/international is given, DO NOT call `reroute_uber_driver`. Instead return `direct_response` asking which terminal — 1, 2, 3, or International.
- Short follow-ups containing just a number (e.g. the caller replies "3") count as naming that terminal, when the previous turn was about the terminal.
- If the caller's requested destination already equals the current trip destination (visible in history or in `lookup_uber_trip` results), do NOT reroute again — return a `direct_response` confirming you're already heading there.

This is an Uber ride / driver conversation only. Never call Walmart tools.

Return shape:
{
  "tool_calls": [{"name": "...", "args": {}}],
  "reason": "short internal reason",
  "direct_response": "only if no tools are needed"
}
"""

FINAL_PROMPT_UBER = """Write the final SMS/voice reply for an Uber ride conversation.
Use the tool results. Be concise, natural, and confident — speak as the driver in first person.
If a tool failed, fall back to a brief safe acknowledgement. Do not mention JSON or internal tool names."""


def respond_uber(session_id, caller_phone, utterance, persona, deps):
    plan = (
        _plan_with_gemini(session_id, caller_phone, utterance, persona, deps)
        or _fallback_plan_uber(utterance, deps["history"])
    )
    tool_results = deps["execute_plan"](plan, {"caller_phone": caller_phone, "session_id": session_id})
    return (
        _final_with_gemini(session_id, utterance, tool_results, plan, persona, deps)
        or _fallback_final_uber(tool_results, plan, persona, deps)
    )


def _plan_with_gemini(session_id, caller_phone, utterance, persona, deps):
    client = deps["client"]()
    if not client:
        return None
    context = {
        "caller_phone": caller_phone,
        "history": deps["history"][-6:],
        "latest_utterance": utterance,
        "persona": deps["persona_block"](persona),
    }
    prompt = f"{deps['system_prompt']}\n\n{PLANNER_PROMPT_UBER}\n\nContext:\n{json.dumps(context, indent=2)}"
    print(f"[Gemini/uber] planner model={deps['model_name']()} session={session_id} utterance={utterance!r}", flush=True)
    try:
        response = client.models.generate_content(model=deps["model_name"](), contents=prompt)
        text = deps["extract_text"](response)
        print(f"[Gemini/uber] planner raw: {text[:1000]!r}", flush=True)
        plan = deps["parse_json"](text)
        if isinstance(plan, dict):
            push_event(
                "gemini_plan",
                {"scenario": "uber", "reason": plan.get("reason"), "tool_count": len(plan.get("tool_calls", []))},
            )
            return plan
        print(f"[Gemini/uber] planner returned non-dict: {plan!r}", flush=True)
    except Exception as error:
        print(f"[Gemini/uber] plan failed: {error}\n{traceback.format_exc()}", flush=True)
        push_event("gemini_plan_failed", {"scenario": "uber", "error": str(error)})
    return None


def _final_with_gemini(session_id, utterance, tool_results, plan, persona, deps):
    client = deps["client"]()
    if not client:
        return None
    context = {
        "history": deps["history"][-8:],
        "latest_utterance": utterance,
        "plan": plan,
        "tool_results": tool_results,
        "persona": deps["persona_block"](persona),
    }
    prompt = f"{deps['system_prompt']}\n\n{FINAL_PROMPT_UBER}\n\nContext:\n{json.dumps(context, indent=2, default=str)}"
    try:
        response = client.models.generate_content(model=deps["model_name"](), contents=prompt)
        text = deps["extract_text"](response).strip()
        if text:
            return text[:700]
    except Exception as error:
        print(f"[Gemini/uber] final failed: {error}\n{traceback.format_exc()}", flush=True)
        push_event("gemini_final_failed", {"scenario": "uber", "error": str(error)})
    return None


def _fallback_plan_uber(utterance, history):
    text = utterance.lower()
    recent_terminal_turn = False
    if history:
        for turn in reversed(history[-4:]):
            if "terminal" in str(turn.get("content", "")).lower():
                recent_terminal_turn = True
                break

    destination = None
    if re.search(r"\b(international|intl)\b", text):
        destination = "SFO International Terminal"
    else:
        number_hits = re.findall(r"(?:terminal\s+|to\s+(?:terminal\s+)?)([123])\b", text)
        if number_hits:
            destination = f"SFO Terminal {number_hits[-1]}"
        elif recent_terminal_turn:
            bare_number = re.findall(r"\b([123])\b", text)
            if bare_number:
                destination = f"SFO Terminal {bare_number[-1]}"
    if not destination and "tower 2" in text:
        destination = "Salesforce Tower 2"

    if destination:
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
        "direct_response": "Which terminal — 1, 2, 3, or International?",
        "reason": "fallback Uber reroute: ambiguous terminal",
    }


def _fallback_final_uber(tool_results, plan, persona, deps):
    names = [r["name"] for r in tool_results if r.get("ok")]
    body = None
    if "reroute_uber_driver" in names:
        reroute = next(r["result"] for r in tool_results if r["name"] == "reroute_uber_driver")
        destination = reroute["destination"]["label"]
        eta = reroute.get("eta_minutes")
        body = f"Heading to {destination} now — see you in about {eta} min."
    if body is None:
        body = plan.get("direct_response") or "Got it — which terminal should I head to?"
    return deps["apply_persona_prefix"](body, persona)
