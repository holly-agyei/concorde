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

export function handleAgentPhoneWebhook(payload, { streamVoice = false } = {}) {
  if (!payload || typeof payload !== "object") {
    return jsonResponse(400, { error: "Invalid JSON payload" });
  }

  if (payload.event === "agent.call_ended") {
    return jsonResponse(200, { status: "ok" });
  }

  if (payload.event !== "agent.message") {
    return jsonResponse(200, { status: "ignored" });
  }

  if (payload.channel === "sms") {
    return jsonResponse(200, { status: "ok" });
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
