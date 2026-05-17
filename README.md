# Concorde Conversational Agent MVP

Concorde is a live phone agent demo for delivery/service workflows. AgentPhone handles the phone call, Gemini negotiates with the caller, Moss supplies fast context, and deterministic tools update the demo UI only after the agent decides to act.

## Run Locally

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Open:

```text
http://localhost:5000
```

The app boots in fallback mode without secrets. Add keys to a local `.env` or parent `.env` to enable live integrations.

## Environment

```bash
GEMINI_API_KEY=
AGENT_PHONE_API_KEY=
AGENT_PHONE_AGENT_ID=cmpa6fsnp085rjz008rwxt9g6
AGENT_PHONE_NUMBER_ID=cmpa6fver0869jz00zapzbujw
AGENT_PHONE_PUBLIC_NUMBER=+18154738613
AGENT_PHONE_WEBHOOK_SECRET=
MOSS_PROJECT_ID=
MOSS_PROJECT_KEY=
MOSS_INDEX_NAME=concorde-demo
WALMART_MODE=mock
BROWSER_USE_API_KEY=
WALMART_BROWSER_PROFILE_ID=
BROWSER_USE_ALLOW_SAVE=0
```

Local aliases are also accepted for the current hackathon `.env`:

- `agent_phone_api_key`
- `gemini_api_key`
- `moss_api_key`
- `moss_project_key`

## AgentPhone

Expose the app with ngrok or another tunnel:

```bash
ngrok http 5000
```

Configure the AgentPhone webhook URL:

```text
https://YOUR-TUNNEL/webhook/agentphone
```

Call forwarding from `+13185160977` to the AgentPhone number is manual carrier setup. If forwarding fails, call the AgentPhone number directly.

## Demo Paths

Uber:

```text
I'm at Terminal D, not Terminal C.
```

Walmart:

```text
Substitute the cereal.
Yes, apply that.
```

Manual stage fallbacks are built into the web UI: reset, reroute to Terminal D, propose/apply Walmart substitution.

## Verification

```bash
python3 -m compileall .
python3 -m unittest tests/smoke_test.py
python3 scripts/replay_voice.py
```
