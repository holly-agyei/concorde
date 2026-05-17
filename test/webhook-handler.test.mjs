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

test("sms webhook can send an AgentPhone reply when explicitly enabled", async () => {
  const requests = [];
  const smsReplyClient = {
    request: async (path, options) => {
      requests.push({ path, options });
      return { id: "msg_reply" };
    }
  };

  const response = await handleAgentPhoneWebhook(sampleSmsPayload, {
    smsAutoReply: true,
    smsReplyClient
  });
  const body = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.deepEqual(body, { status: "ok", smsReply: "sent" });
  assert.deepEqual(requests, [
    {
      path: "/messages",
      options: {
        method: "POST",
        body: {
          agent_id: sampleSmsPayload.agentId,
          to_number: sampleSmsPayload.data.from,
          body: "Thanks for texting Concorde. We received: Test message",
          number_id: sampleSmsPayload.data.numberId
        }
      }
    }
  ]);
});

test("sms webhook does not auto-reply to outbound messages", () => {
  const outboundPayload = {
    ...sampleSmsPayload,
    data: {
      ...sampleSmsPayload.data,
      direction: "outbound"
    }
  };
  const smsReplyClient = {
    request: async () => {
      throw new Error("should not send");
    }
  };

  const response = handleAgentPhoneWebhook(outboundPayload, {
    smsAutoReply: true,
    smsReplyClient
  });
  const body = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.deepEqual(body, { status: "ok" });
});

test("imessage webhook can use the same auto-reply path", async () => {
  const requests = [];
  const imessagePayload = {
    ...sampleSmsPayload,
    channel: "imessage"
  };
  const smsReplyClient = {
    request: async (path, options) => {
      requests.push({ path, options });
      return { id: "msg_reply" };
    }
  };

  const response = await handleAgentPhoneWebhook(imessagePayload, {
    smsAutoReply: true,
    smsReplyClient
  });
  const body = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.deepEqual(body, { status: "ok", smsReply: "sent" });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].path, "/messages");
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
