#!/usr/bin/env node
import { loadAgentPhoneConfig } from "../src/env.mjs";
import { getSamplePayload } from "../src/samples.mjs";
import { signAgentPhoneWebhook } from "../src/webhook-security.mjs";

const kind = process.argv[2] || "voice";
const url = process.env.WEBHOOK_URL || "http://localhost:3000/webhook";
const { webhookSecret } = loadAgentPhoneConfig();
const payload = getSamplePayload(kind);
const rawBody = JSON.stringify(payload);
const timestamp = String(Math.floor(Date.now() / 1000));
const headers = {
  "Content-Type": "application/json",
  "X-Webhook-ID": `local_${kind}_${timestamp}`,
  "X-Webhook-Event": payload.event,
  "X-Webhook-Timestamp": timestamp
};

if (webhookSecret) {
  headers["X-Webhook-Signature"] = signAgentPhoneWebhook(rawBody, timestamp, webhookSecret);
}

const response = await fetch(url, {
  method: "POST",
  headers,
  body: rawBody
});

const responseText = await response.text();
console.log(`${response.status} ${response.statusText}`);
console.log(response.headers.get("content-type") || "no content-type");
console.log(responseText);
