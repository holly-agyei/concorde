# Concorde AgentPhone Integration

This branch is the AgentPhone setup guide and test harness for coding agents. It is written so a future coding agent can read it, reproduce the integration, and avoid accidentally placing live calls.

## Current Account Snapshot

From the live read-only smoke test:

- Agent name: `Holy Agyei's Agent`
- Agent ID: `cmpa6fsnp085rjz008rwxt9g6`
- Voice mode: `hosted`
- Attached AgentPhone number: `+18154738613`
- Attached phone number ID: `cmpa6fver0869jz00zapzbujw`
- Extra unattached number: ends in `4412`

Do not commit API keys. The API key belongs in `.env`, which is ignored.

## How AgentPhone Works

AgentPhone has four important resources:

- `Agent`: the AI persona. It can use `hosted` voice mode or `webhook` voice mode.
- `Phone number`: the SMS/voice number provisioned by AgentPhone.
- `Attachment`: a number must be attached to an agent before that agent can receive calls/texts on it or place outbound calls.
- `Webhook`: the public HTTPS endpoint AgentPhone calls when a message, voice turn, reaction, or call-ended event happens.

For this project:

- Voice calls currently work through hosted AI because `Holy Agyei's Agent` is `voiceMode: "hosted"`.
- SMS/text responses are webhook-based. To make texting work as an auto-reply agent, run a public webhook and have it call `POST /v1/messages` back to the sender.

## AgentPhone API Facts

- Base URL: `https://api.agentphone.ai/v1`
- Auth header: `Authorization: Bearer <api key>`
- List agents: `GET /v1/agents`
- List numbers: `GET /v1/numbers`
- Attach number: `POST /v1/agents/{agent_id}/numbers` with `{ "numberId": "..." }`
- Configure project webhook: `POST /v1/webhooks`
- Configure per-agent webhook: `POST /v1/agents/{agent_id}/webhook`
- Send SMS/iMessage: `POST /v1/messages`
- Create web/browser call token: `POST /v1/calls/web`
- Create outbound phone call: `POST /v1/calls`

Docs read:

- https://docs.agentphone.ai/welcome
- https://docs.agentphone.ai/documentation/guides/phone-numbers
- https://docs.agentphone.ai/documentation/guides/calls
- https://docs.agentphone.ai/integrations/connect-your-ai/coding-agents
- https://docs.agentphone.ai/api-reference/messages/send-message-v-1-messages-post

## Environment

Save the key in the repo `.env` or the parent folder `.env`:

```bash
AGENT_PHONE_API_KEY=sk_live_...
```

This repo also supports the lower-case name:

```bash
agent_phone_api_key=sk_live_...
```

Optional webhook settings:

```bash
AGENT_PHONE_WEBHOOK_SECRET=whsec_...
AGENT_PHONE_AUTO_REPLY_SMS=1
AGENT_PHONE_AUTO_REPLY_BODY=Hey, this is Holy's test agent. I got your text.
```

`AGENT_PHONE_WEBHOOK_SECRET` is returned when you create/update a webhook. Store it so the webhook server can verify AgentPhone signatures.

## Read-Only Smoke Test

Use this first. It checks auth and lists usage, agents, numbers, webhook config, and recent calls. It does not create resources, send texts, or place calls.

```bash
npm run api:smoke
```

Expected readiness for this account:

- `webCallReady: true` because there is an agent.
- `outboundCallReady: true` because the agent has an attached number.
- webhook may be unconfigured until you expose and register a public webhook.

## Local Webhook Mock

Run the local webhook:

```bash
npm run mock:webhook
```

Send local mock events:

```bash
npm run mock:voice
npm run mock:sms
npm run mock:call-ended
```

Expected behavior:

- Voice `agent.message` returns JSON like `{ "text": "..." }`.
- SMS `agent.message` returns `200 OK` by default.
- `agent.call_ended` returns `200 OK`.

For streaming voice tests:

```bash
STREAM_VOICE=1 npm run mock:webhook
```

## Correct SMS Auto-Reply Setup

SMS does not use hosted voice mode. Texting needs a webhook. The webhook receives `agent.message` with `channel: "sms"` and then sends a reply with `POST /v1/messages`.

End-to-end setup:

1. Start the webhook locally:

```bash
AGENT_PHONE_AUTO_REPLY_SMS=1 npm run mock:webhook
```

2. Expose it with a tunnel:

```bash
ngrok http 3000
```

or:

```bash
npm install -g localtunnel
lt --port 3000
```

3. Register the public HTTPS URL as a per-agent webhook:

```bash
curl -X POST "https://api.agentphone.ai/v1/agents/cmpa6fsnp085rjz008rwxt9g6/webhook" \
  -H "Authorization: Bearer $AGENT_PHONE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://YOUR-TUNNEL-URL/webhook","contextLimit":10,"timeout":30}'
```

4. Save the returned `secret` in `.env`:

```bash
AGENT_PHONE_WEBHOOK_SECRET=returned_secret_here
```

5. Restart the webhook with both auto-reply and signature verification:

```bash
AGENT_PHONE_AUTO_REPLY_SMS=1 npm run mock:webhook
```

6. Text the attached AgentPhone number:

```text
+18154738613
```

The agent should receive the SMS webhook and reply through `POST /v1/messages`.

## Message Send Payload

When replying to an inbound text, send:

```json
{
  "agent_id": "cmpa6fsnp085rjz008rwxt9g6",
  "to_number": "+13185160977",
  "body": "Hey, this is Holy's test agent. I got your text.",
  "number_id": "cmpa6fver0869jz00zapzbujw"
}
```

Notes:

- `agent_id` is required.
- `to_number` is the human sender from the inbound webhook `data.from`.
- `body` is required.
- `number_id` is optional but recommended when the agent has more than one number.

## Voice Call Tests

Dry run only:

```bash
npm run api:call:dry-run -- --agent-id cmpa6fsnp085rjz008rwxt9g6 --to +13185160977
```

Real outbound call:

```bash
node scripts/create-outbound-call.mjs \
  --agent-id cmpa6fsnp085rjz008rwxt9g6 \
  --to +13185160977 \
  --initial-greeting "Hi Holy, this is your AgentPhone sample agent test." \
  --system-prompt "You are Holy Agyei's sample phone agent. Keep this call short and confirm audio works." \
  --live \
  --place-call
```

The script requires both `--live` and `--place-call` before dialing.

## Web Call Tests

Browser web-call token, no PSTN dialing:

```bash
npm run api:web-call:dry-run -- --agent-id cmpa6fsnp085rjz008rwxt9g6
```

Live token creation:

```bash
node scripts/create-web-call.mjs --agent-id cmpa6fsnp085rjz008rwxt9g6 --live
```

The returned token expires in 30 seconds and should be passed immediately to the frontend AgentPhone Web SDK.

## Webhook Payload Rules

AgentPhone sends:

- `agent.message` with `channel: "sms"`, `mms`, or `imessage` for inbound texts.
- `agent.message` with `channel: "voice"` for transcribed voice turns.
- `agent.call_ended` with the full voice transcript after a call.

Voice webhook responses:

```json
{ "text": "How can I help you?" }
```

Streaming voice response:

```json
{"text":"One moment, let me check.","interim":true}
{"text":"I found the answer."}
```

SMS webhook responses:

- Return `200 OK` quickly.
- To actually text back, call `POST /v1/messages`.

## Security Checklist

- Never commit `.env`.
- Verify webhook signatures with `X-Webhook-Signature` and `X-Webhook-Timestamp`.
- Reject webhook timestamps older than 5 minutes.
- Use `X-Webhook-ID` for idempotency in production so retries do not create duplicate SMS replies.
- Keep real call/text scripts guarded or explicit.
- Rotate any key that was pasted into chat or screenshots.

## Coding Agent Runbook

When a coding agent starts from this repo:

1. Confirm branch:

```bash
git status --short --branch
```

2. Check auth and resources:

```bash
npm run api:smoke
```

3. Run tests:

```bash
npm test
```

4. Test local webhook behavior:

```bash
npm run mock:webhook
npm run mock:voice
npm run mock:sms
npm run mock:call-ended
```

5. For SMS auto-reply, expose `/webhook`, register the per-agent webhook, save the returned secret, restart the mock webhook, then text `+18154738613`.

6. For voice, call `+18154738613` directly or use the guarded outbound call script.
