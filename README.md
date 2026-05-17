# Concorde AgentPhone API Config

This branch contains a safe AgentPhone test harness for checking API access and mocking call webhooks before building the real app.

## What The Docs Say

- API base URL: `https://api.agentphone.ai/v1`
- Auth: `Authorization: Bearer <api key>`
- Voice webhooks receive `agent.message` events with `channel: "voice"` and must return a JSON object like `{ "text": "..." }`.
- For slower voice turns, return `application/x-ndjson` with an interim chunk first.
- `agent.call_ended` includes the full transcript and only needs a `200 OK`.
- Browser calls use `POST /v1/calls/web` with an `agentId` and return a short-lived `accessToken`.
- Real outbound phone calls use `POST /v1/calls` and require an agent with an attached phone number.

Docs read:

- https://docs.agentphone.ai/welcome
- https://docs.agentphone.ai/documentation/guides/phone-numbers
- https://docs.agentphone.ai/documentation/guides/calls
- https://docs.agentphone.ai/integrations/connect-your-ai/coding-agents

## Setup

Save your key in either the repo `.env` or the parent folder `.env`:

```bash
AGENT_PHONE_API_KEY=sk_live_...
```

The scripts also support the lower-case name from your local note:

```bash
agent_phone_api_key=sk_live_...
```

Do not commit `.env`.

## Safe Local Mock

Run the webhook server:

```bash
npm run mock:webhook
```

In another terminal, send mock AgentPhone payloads:

```bash
npm run mock:voice
npm run mock:sms
npm run mock:call-ended
```

To test AgentPhone-style HMAC verification locally, set `AGENT_PHONE_WEBHOOK_SECRET` in `.env`; the mock sender signs requests automatically.

## API Smoke Test

This checks API auth and lists usage, agents, numbers, webhook config, and recent calls. It does not create resources or place calls.

```bash
npm run api:smoke
```

## Call Dry Runs

These show the exact payloads without hitting the live call endpoints:

```bash
npm run api:web-call:dry-run -- --agent-id agt_abc123
npm run api:call:dry-run -- --agent-id agt_abc123 --to +15551234567
```

## Guarded Live Calls

Browser web-call token, no PSTN dialing:

```bash
node scripts/create-web-call.mjs --agent-id agt_abc123 --live
```

Real outbound phone call:

```bash
node scripts/create-outbound-call.mjs \
  --agent-id agt_abc123 \
  --to +15551234567 \
  --live \
  --place-call
```

The outbound script requires both `--live` and `--place-call` on purpose.
