# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source-of-truth docs

- [CONTEXT.md](CONTEXT.md) — product vision, the five user stories, north-star demo.
- [TECHNICAL_CONTEXT.md](TECHNICAL_CONTEXT.md) — binding build spec: stack, hard constraints, failure modes.
- [integrations/agentphone/README.md](integrations/agentphone/README.md) — live AgentPhone account info (agent ID `cmpa6fsnp085rjz008rwxt9g6`, number `+18154738613`), API endpoints, webhook flow.
- [integrations/moss/README.md](integrations/moss/README.md) — Moss env vars, seed corpus, `semantic_lookup` shape.

When `TECHNICAL_CONTEXT.md` and the code disagree, the code wins for what is — the doc still wins for what should be. Both are short; read them before non-trivial changes.

## Run & verify

```bash
python3 -m pip install -r requirements.txt
python3 app.py                              # serves http://localhost:5000

python3 -m compileall .                     # syntax check
python3 -m unittest tests/smoke_test.py     # smoke tests
python3 scripts/replay_voice.py             # end-to-end voice replay
```

Run a single test: `python3 -m unittest tests.smoke_test.TestClassName.test_method`.

There is no linter, no formatter, no JS build step — frontend is plain HTML/CSS/JS in [static/](static/).

## Offline mode

Set `CONCORDE_OFFLINE_TESTS=1` to force `agent.brain._model()` to return `None`. The agent then uses the deterministic `_fallback_plan` / `_fallback_final` paths in [agent/brain.py](agent/brain.py) — no Gemini key needed. Tests rely on this; demos do not.

The app also boots in "fallback mode" with no secrets at all: missing `GEMINI_API_KEY`, `MOSS_*`, `BROWSER_USE_API_KEY` are tolerated and each integration silently degrades.

## Environment variables

`.env.example` and the live `.env` use lowercase aliases (`agent_phone_api_key`, `gemini_api_key`, `moss_api_key`, `moss_project_key`). [config.py](config.py) runs at import and maps these to the canonical uppercase names (`AGENT_PHONE_API_KEY`, `GEMINI_API_KEY`, `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`). Note `moss_api_key` aliases to `MOSS_PROJECT_ID`, not a key. When adding a new secret: write to `.env.example` first, then extend the `aliases` dict in `config.py` if the team's `.env` uses a non-canonical name. Never invent new env var names without updating both files.

[config.py](config.py) is imported for side effects in [app.py](app.py) — keep that `# noqa: F401` import in place; it's what loads `.env`.

## Architecture

**Request flow.** AgentPhone POSTs to `/webhook/agentphone` ([app.py](app.py)). The handler verifies the signature via `integrations.agentphone.verify_webhook`, dispatches on `event` (`agent.message` / `agent.call_ended`) and `channel` (`voice` / `sms` / `mms` / `imessage`), and calls `agent.brain.respond(session_id, caller_phone, utterance)`. Voice responses stream as `application/x-ndjson` (interim "Let me check that for you." then a final line); SMS returns JSON.

**Agent brain is two Gemini calls, not one.** [agent/brain.py](agent/brain.py):

1. `_plan_with_gemini` → returns JSON `{"tool_calls": [...], "reason": "..."}` (planner prompt).
2. `_execute_plan` runs each tool through `TOOL_REGISTRY` in [agent/tools.py](agent/tools.py) (capped at 5 calls).
3. `_final_with_gemini` → composes the spoken reply from the plan + tool results (final prompt).

If Gemini is unavailable at either step, `_fallback_plan` / `_fallback_final` kick in with keyword-matched plans for the two hero scenarios (Uber reroute, Walmart substitution). The fallback paths are demo-critical — do not let refactors break them.

`_history` is an in-memory `defaultdict(list)` keyed by `session_id`; `reset_session(session_id)` is called on `agent.call_ended`. No cross-call persistence.

**Tools are the only thing that mutate state.** Every tool in [agent/tools.py](agent/tools.py) calls `push_event(...)` after mutating mocks. To add a new agent capability: write the mock action, write the tool wrapper that emits an SSE event, register it in `TOOL_REGISTRY`, and reference it by name in the planner prompt or fallback plan.

**Events are the single SSE bus.** [events.py](events.py) is an in-process pub/sub (Lock + per-subscriber `queue.Queue` + last-80 history replay on subscribe). `push_event(type, data)` fans out to all `/events` subscribers and to a bounded history that new subscribers replay on connect. The frontend's `EventSource("/events")` is what drives the live map + log.

**Mocks are the source of truth for demo state.** [mocks/uber.py](mocks/uber.py), [mocks/walmart.py](mocks/walmart.py), and [mocks/store.py](mocks/store.py) load `data/*.json` into memory at import and persist back on change. There is no DB. Manual stage controls in the web UI hit `/api/demo/reset`, `/api/demo/uber/reroute`, `/api/demo/walmart/substitution` — these are the demo safety net if the live phone call fails mid-stage.

**Integrations degrade gracefully.** [integrations/moss_runtime.py](integrations/moss_runtime.py), [integrations/browser_walmart.py](integrations/browser_walmart.py), and [integrations/agentphone.py](integrations/agentphone.py) each check for keys/SDKs at call time and no-op (or return stubs) when absent, emitting an SSE event so the absence is visible on the projector.

## Hard constraints (from TECHNICAL_CONTEXT.md)

- 8-hour hackathon, team of 2. Optimize for the demo, not production. No refactor sweeps.
- No DB — JSON files only. No ORM, no migrations.
- No frontend build step. Plain HTML/CSS/vanilla JS. No React/Vue/TS/bundler/Tailwind.
- One Gemini call (well, two — planner + final) with tool use is the entire agent. No LangChain/CrewAI/agent framework.
- Hero demo ("Wrong Terminal at SFO") first. Walmart substitution is the secondary scenario. Delta upgrade, group call, and Supermemory are stretch — do not build them until the hero is bulletproof.
