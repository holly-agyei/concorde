#!/usr/bin/env node
import { createServer } from "node:http";
import { loadAgentPhoneConfig } from "../src/env.mjs";
import { handleAgentPhoneWebhook } from "../src/webhook-handler.mjs";
import { verifyAgentPhoneWebhook } from "../src/webhook-security.mjs";

const port = Number(process.env.PORT || 3000);
const streamVoice = process.env.STREAM_VOICE === "1";
const { webhookSecret } = loadAgentPhoneConfig();

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

  const result = handleAgentPhoneWebhook(payload, { streamVoice });
  send(response, result);
});

server.listen(port, () => {
  console.log(`AgentPhone mock webhook listening on http://localhost:${port}/webhook`);
  console.log(`Health check: http://localhost:${port}/health`);
  console.log(`Streaming voice responses: ${streamVoice ? "on" : "off"}`);
  console.log(`Webhook signature verification: ${webhookSecret ? "on" : "off"}`);
});
