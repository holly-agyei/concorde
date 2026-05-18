# Concorde Browser Action Server

This branch is the text-first server path for real browser workflows:

```text
AgentPhone SMS or local text endpoint -> Concorde service agent -> guarded browser action
```

Walmart uses Browser Use cloud. DoorDash uses visible local Chrome with your configured Chrome profile. The old visual demo is still available at `/demo`, but `/` now returns API status because this branch is focused on the server-side integration.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

## First-time DoorDash login

So the browser agent operates on your real DoorDash account, capture a saved session once:

```bash
python3 scripts/login_doordash.py
```

Re-run if your session expires.

Open:

```text
http://localhost:5000/
http://localhost:5000/user
http://localhost:5000/demo
```

## Environment

Copy `.env.example` into a local `.env` and fill only the values you need.

```bash
WALMART_MODE=browser
BROWSER_USE_API_KEY=...
BROWSER_USE_DRY_RUN=0
BROWSER_USE_ALLOW_SAVE=0
WALMART_BROWSER_PROFILE_ID=
DOORDASH_BROWSER_PROFILE_ID=Default
DOORDASH_COPY_DEFAULT_PROFILE=1
DOORDASH_LATITUDE=37.7749
DOORDASH_LONGITUDE=-122.4194
DOORDASH_DRY_RUN=0
AGENT_PHONE_WEBHOOK_SECRET=
```

Use a Browser Use profile that is already logged into your Walmart account when possible. If Walmart asks for login, 2FA, or CAPTCHA, the browser agent stops and reports the blocker. `BROWSER_USE_ALLOW_SAVE=0` is the safe default: Concorde can inspect and draft changes but must stop before final save/apply/submit.

## Local Text Test

Dry run without opening Walmart:

```bash
BROWSER_USE_DRY_RUN=1 python3 scripts/replay_walmart_text.py \
  "Open my Walmart order and change the cereal substitution to Cinnamon Oat Squares"
```

Live Browser Use run:

```bash
python3 scripts/replay_walmart_text.py --live \
  "Open my Walmart order and change the cereal substitution to Cinnamon Oat Squares"
```

Direct HTTP:

```bash
curl -X POST http://localhost:5000/api/walmart/text \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"local-walmart","message":"Open my Walmart order and change the cereal substitution"}'
```

Inspect conversation state:

```bash
curl http://localhost:5000/api/walmart/session/local-walmart
```

## DoorDash Visible Chrome Test

This opens local Chrome visibly, copies the configured Chrome profile into a temporary automation profile, shares a demo geolocation, and can prepare or edit a DoorDash cart. It never checks out, places an order, submits payment, or buys anything.

```bash
python3 scripts/replay_doordash_text.py \
  "Add pizza to my DoorDash cart, but do not buy anything"
```

Dynamic cart examples:

```bash
python3 scripts/replay_doordash_text.py \
  "Replace the pizza in my cart with sushi, but do not buy anything"

python3 scripts/replay_doordash_text.py \
  "Remove the tacos from my DoorDash cart"
```

Dry run without opening Chrome:

```bash
python3 scripts/replay_doordash_text.py --dry-run \
  "Open DoorDash and add pizza to cart, but do not buy anything"
```

The copied-profile mode avoids Chrome's default-profile DevTools lock while still giving you a visible browser run.

## User DM UI

The pulled user-facing UI lives at:

```text
http://localhost:5000/user
```

It shows WhatsApp-style DM threads for DoorDash, Walmart, and driver personas. Messages post to `POST /api/agent/chat`; DoorDash messages route through Gemini planning when `GEMINI_API_KEY` is configured, then launch the visible Chrome DoorDash workflow. Walmart messages route to the Browser Use workflow.

## AgentPhone SMS

Expose the Flask server with ngrok or another tunnel:

```bash
ngrok http 5000
```

Set the AgentPhone webhook URL to:

```text
https://YOUR-TUNNEL/webhook/agentphone
```

When an inbound `agent.message` arrives over `sms`, `mms`, or `imessage` and looks like a Walmart/order request, Concorde routes it to the Walmart Browser Use agent and returns the text reply in the webhook response.

## Verification

```bash
python3 -m compileall .
CONCORDE_OFFLINE_TESTS=1 python3 -m unittest tests/smoke_test.py
BROWSER_USE_DRY_RUN=1 python3 scripts/replay_walmart_text.py "Change my Walmart cereal substitution"
python3 scripts/replay_doordash_text.py --dry-run "Open DoorDash and add pizza to cart"
```
