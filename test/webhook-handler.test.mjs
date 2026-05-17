import assert from "node:assert/strict";
import test from "node:test";
import { handleAgentPhoneWebhook } from "../src/webhook-handler.mjs";
import { sampleCallEndedPayload, sampleSmsPayload, sampleVoicePayload } from "../src/samples.mjs";
import { signAgentPhoneWebhook, verifyAgentPhoneWebhook } from "../src/webhook-security.mjs";

test("voice webhook returns a JSON object with speakable text", () => {
  const response = handleAgentPhoneWebhook(sampleVoicePayload);
  const body = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.equal(response.headers["Content-Type"], "application/json");
  assert.match(body.text, /order/i);
});

test("voice webhook can return NDJSON streaming chunks", () => {
  const response = handleAgentPhoneWebhook(sampleVoicePayload, { streamVoice: true });
  const chunks = response.body
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));

  assert.equal(response.status, 200);
  assert.equal(response.headers["Content-Type"], "application/x-ndjson");
  assert.equal(chunks[0].interim, true);
  assert.equal(typeof chunks.at(-1).text, "string");
});

test("sms webhook acknowledges without voice text", () => {
  const response = handleAgentPhoneWebhook(sampleSmsPayload);
  const body = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.deepEqual(body, { status: "ok" });
});

test("call-ended webhook acknowledges completed calls", () => {
  const response = handleAgentPhoneWebhook(sampleCallEndedPayload);
  const body = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.deepEqual(body, { status: "ok" });
});

test("webhook signatures verify timestamp plus raw body", () => {
  const rawBody = JSON.stringify(sampleVoicePayload);
  const timestamp = "1764770700";
  const secret = "test_secret";
  const signature = signAgentPhoneWebhook(rawBody, timestamp, secret);

  assert.equal(verifyAgentPhoneWebhook(rawBody, signature, timestamp, secret, Number(timestamp)).ok, true);
  assert.equal(verifyAgentPhoneWebhook(`${rawBody} `, signature, timestamp, secret, Number(timestamp)).ok, false);
});
