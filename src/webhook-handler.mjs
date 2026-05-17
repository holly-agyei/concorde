function jsonResponse(status, body, headers = {}) {
  return {
    status,
    headers: {
      "Content-Type": "application/json",
      ...headers
    },
    body: JSON.stringify(body)
  };
}

function ndjsonResponse(chunks) {
  return {
    status: 200,
    headers: {
      "Content-Type": "application/x-ndjson"
    },
    body: chunks.map((chunk) => JSON.stringify(chunk)).join("\n") + "\n"
  };
}

export function buildVoiceReply(transcript = "") {
  const normalized = transcript.trim();

  if (!normalized) {
    return "I heard silence on that turn. Can you repeat that?";
  }

  if (/order|shipment|delivery/i.test(normalized)) {
    return "I can help with that order. What is the order number?";
  }

  if (/hours|open|close/i.test(normalized)) {
    return "Our support team is available every weekday from 9 AM to 5 PM.";
  }

  return `I heard: ${normalized}`;
}

export function buildSmsReply(message = "") {
  const normalized = message.trim();

  if (!normalized) {
    return "Thanks for texting Concorde. We received your message and will follow up shortly.";
  }

  if (/order|shipment|delivery/i.test(normalized)) {
    return "Thanks for texting Concorde. We can help with that order. What is the order number?";
  }

  if (/hours|open|close/i.test(normalized)) {
    return "Thanks for texting Concorde. Our support team is available every weekday from 9 AM to 5 PM.";
  }

  return `Thanks for texting Concorde. We received: ${normalized}`;
}

function isTextChannel(channel) {
  return channel === "sms" || channel === "mms" || channel === "imessage";
}

function isReplyableTextMessage(payload) {
  return isTextChannel(payload.channel) && payload.data?.direction === "inbound";
}

function buildSmsReplyRequest(payload, text) {
  return {
    agent_id: payload.agentId,
    to_number: payload.data.from,
    body: text,
    number_id: payload.data.numberId
  };
}

async function sendSmsReply(payload, text, client) {
  const body = buildSmsReplyRequest(payload, text);

  if (typeof client?.messages?.sendMessage === "function") {
    return client.messages.sendMessage(body);
  }

  if (typeof client?.request === "function") {
    return client.request("/messages", { method: "POST", body });
  }

  throw new Error("SMS reply client must expose request() or messages.sendMessage()");
}

export function handleAgentPhoneWebhook(
  payload,
  { streamVoice = false, smsAutoReply = false, smsReplyClient = null } = {}
) {
  if (!payload || typeof payload !== "object") {
    return jsonResponse(400, { error: "Invalid JSON payload" });
  }

  if (payload.event === "agent.call_ended") {
    return jsonResponse(200, { status: "ok" });
  }

  if (payload.event !== "agent.message") {
    return jsonResponse(200, { status: "ignored" });
  }

  if (isTextChannel(payload.channel)) {
    if (!smsAutoReply || !isReplyableTextMessage(payload)) {
      return jsonResponse(200, { status: "ok" });
    }

    const text = buildSmsReply(payload.data?.message || "");

    if (!smsReplyClient) {
      return jsonResponse(200, { status: "ok", smsReply: "skipped", reason: "missing_client" });
    }

    return sendSmsReply(payload, text, smsReplyClient)
      .then(() => jsonResponse(200, { status: "ok", smsReply: "sent" }))
      .catch((error) =>
        jsonResponse(200, {
          status: "ok",
          smsReply: "failed",
          error: error.message
        })
      );
  }

  if (payload.channel === "voice") {
    const text = buildVoiceReply(payload.data?.transcript || "");

    if (streamVoice) {
      return ndjsonResponse([
        { text: "One moment, let me check that.", interim: true },
        { text }
      ]);
    }

    return jsonResponse(200, { text });
  }

  return jsonResponse(200, { status: "ok" });
}
