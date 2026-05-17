#!/usr/bin/env node
import { createServer } from "node:http";
import { createAgentPhoneClient } from "../src/agentphone-client.mjs";
import { loadAgentPhoneConfig } from "../src/env.mjs";
import { handleAgentPhoneWebhook } from "../src/webhook-handler.mjs";
import { verifyAgentPhoneWebhook } from "../src/webhook-security.mjs";

const port = Number(process.env.PORT || 3000);
const streamVoice = process.env.STREAM_VOICE === "1";
const smsAutoReply =
  process.env.AGENT_PHONE_AUTO_REPLY_SMS === "1" || process.env.AGENT_PHONE_SMS_AUTO_REPLY === "1";
const { apiKey, webhookSecret, baseUrl } = loadAgentPhoneConfig();
const smsReplyClient = smsAutoReply && apiKey ? createAgentPhoneClient({ apiKey, baseUrl }) : null;

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function send(response, result) {
  response.writeHead(result.status, result.headers);
  response.end(result.body);
}

const server = createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    send(response, {
      status: 200,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "ok" })
    });
    return;
  }

  if (request.method !== "POST" || request.url !== "/webhook") {
    send(response, {
      status: 404,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: "Not found" })
    });
    return;
  }

  const rawBody = await readBody(request);
  const verification = verifyAgentPhoneWebhook(
    rawBody,
    request.headers["x-webhook-signature"],
    request.headers["x-webhook-timestamp"],
    webhookSecret
  );

  if (!verification.ok) {
    send(response, {
      status: 401,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: verification.reason })
    });
    return;
  }

  let payload;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    send(response, {
      status: 400,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: "Invalid JSON" })
    });
    return;
  }

  const result = await handleAgentPhoneWebhook(payload, {
    streamVoice,
    smsAutoReply,
    smsReplyClient
  });
  send(response, result);
});

server.listen(port, () => {
  console.log(`AgentPhone mock webhook listening on http://localhost:${port}/webhook`);
  console.log(`Health check: http://localhost:${port}/health`);
  console.log(`Streaming voice responses: ${streamVoice ? "on" : "off"}`);
  console.log(`SMS auto-reply: ${smsAutoReply ? "on" : "off"}`);
  if (smsAutoReply && !apiKey) {
    console.log("SMS auto-reply needs AGENT_PHONE_API_KEY before it can send replies");
  }
  console.log(`Webhook signature verification: ${webhookSecret ? "on" : "off"}`);
});
