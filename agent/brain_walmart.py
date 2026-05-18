import json
import re
import traceback

from events import push_event


PLANNER_PROMPT_WALMART = """Return JSON only. Decide which Walmart tools to call for the caller's latest utterance.
Available tools:
- lookup_walmart_order
- propose_walmart_substitution with {"item_name": "...", "substitute_name": "..."}
- apply_walmart_substitution
- run_walmart_browser_task with {"task": "...", "caller_confirmed": true|false}
- semantic_lookup with {"query": "..."}

Rules:
- Never call `apply_walmart_substitution` unless the caller has explicitly confirmed (yes/approve/do it/apply).
- Never set `caller_confirmed: true` on `run_walmart_browser_task` without explicit caller confirmation.
- This is a Walmart grocery order conversation only. Never call Uber tools.

Return shape:
{
  "tool_calls": [{"name": "...", "args": {}}],
  "reason": "short internal reason",
  "direct_response": "only if no tools are needed"
}
"""

FINAL_PROMPT_WALMART = """Write the final SMS/voice reply for a Walmart grocery support conversation.
Use the tool results. Be concise, natural, and confident — speak as a Walmart support agent.
If a tool failed, fall back to a brief safe acknowledgement. Do not mention JSON or internal tool names."""


def respond_walmart(session_id, caller_phone, utterance, persona, deps):
    plan = (
        _plan_with_gemini(session_id, caller_phone, utterance, persona, deps)
        or _fallback_plan_walmart(utterance)
    )
    tool_results = deps["execute_plan"](plan, {"caller_phone": caller_phone, "session_id": session_id})
    return (
        _final_with_gemini(session_id, utterance, tool_results, plan, persona, deps)
        or _fallback_final_walmart(tool_results, plan, persona, deps)
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
    prompt = f"{deps['system_prompt']}\n\n{PLANNER_PROMPT_WALMART}\n\nContext:\n{json.dumps(context, indent=2)}"
    print(f"[Gemini/walmart] planner model={deps['model_name']()} session={session_id} utterance={utterance!r}", flush=True)
    try:
        response = client.models.generate_content(model=deps["model_name"](), contents=prompt)
        text = deps["extract_text"](response)
        print(f"[Gemini/walmart] planner raw: {text[:1000]!r}", flush=True)
        plan = deps["parse_json"](text)
        if isinstance(plan, dict):
            push_event(
                "gemini_plan",
                {"scenario": "walmart", "reason": plan.get("reason"), "tool_count": len(plan.get("tool_calls", []))},
            )
            return plan
        print(f"[Gemini/walmart] planner returned non-dict: {plan!r}", flush=True)
    except Exception as error:
        print(f"[Gemini/walmart] plan failed: {error}\n{traceback.format_exc()}", flush=True)
        push_event("gemini_plan_failed", {"scenario": "walmart", "error": str(error)})
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
    prompt = f"{deps['system_prompt']}\n\n{FINAL_PROMPT_WALMART}\n\nContext:\n{json.dumps(context, indent=2, default=str)}"
    try:
        response = client.models.generate_content(model=deps["model_name"](), contents=prompt)
        text = deps["extract_text"](response).strip()
        if text:
            return text[:700]
    except Exception as error:
        print(f"[Gemini/walmart] final failed: {error}\n{traceback.format_exc()}", flush=True)
        push_event("gemini_final_failed", {"scenario": "walmart", "error": str(error)})
    return None


def _fallback_plan_walmart(utterance):
    text = utterance.lower()
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


def _fallback_final_walmart(tool_results, plan, persona, deps):
    names = [r["name"] for r in tool_results if r.get("ok")]
    body = None
    if "apply_walmart_substitution" in names:
        result = next(r["result"] for r in tool_results if r["name"] == "apply_walmart_substitution")
        if result.get("applied"):
            body = f"Done — swapped {result['substitution']['from']} for {result['substitution']['to']} on your order."
    elif "propose_walmart_substitution" in names:
        result = next(r["result"] for r in tool_results if r["name"] == "propose_walmart_substitution")
        pending = result["pending"]
        body = (
            f"Quick heads-up: {pending['from']} is out of stock. "
            f"We can swap it for {pending['to']} — want me to apply that?"
        )
    if body is None:
        body = plan.get("direct_response") or "Can you tell me a bit more about what you need on your order?"
    return deps["apply_persona_prefix"](body, persona)
