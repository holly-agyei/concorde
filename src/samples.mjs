export const sampleSmsPayload = {
  event: "agent.message",
  channel: "sms",
  timestamp: "2025-12-03T10:05:00Z",
  agentId: "agent_123",
  data: {
    conversationId: "conv_test456",
    numberId: "num_abc",
    from: "+14155551234",
    to: "+18571234567",
    message: "Test message",
    direction: "inbound",
    receivedAt: "2025-12-03T10:05:00Z"
  },
  conversationState: { testMode: true },
  recentHistory: [
    {
      content: "Hello",
      direction: "inbound",
      channel: "sms",
      at: "2025-12-03T10:04:00Z"
    }
  ]
};

export const sampleVoicePayload = {
  event: "agent.message",
  channel: "voice",
  timestamp: "2025-12-03T10:05:00Z",
  agentId: "agent_123",
  data: {
    callId: "call_abc123",
    numberId: "num_abc",
    from: "+14155551234",
    to: "+18571234567",
    status: "in-progress",
    transcript: "I need help with my order",
    confidence: 0.95,
    direction: "inbound"
  },
  conversationState: null,
  recentHistory: [
    {
      content: "Hello, how can I help?",
      direction: "outbound",
      channel: "voice",
      at: "2025-12-03T10:04:30Z"
    }
  ]
};

export const sampleCallEndedPayload = {
  event: "agent.call_ended",
  channel: "voice",
  timestamp: "2025-12-03T10:08:00Z",
  agentId: "agent_123",
  data: {
    callId: "call_abc123",
    numberId: "num_abc",
    from: "+14155551234",
    to: "+18571234567",
    direction: "inbound",
    status: "completed",
    startedAt: "2025-12-03T10:05:00Z",
    endedAt: "2025-12-03T10:08:00Z",
    durationSeconds: 180,
    disconnectionReason: "agent_hangup",
    transcript: [
      { role: "agent", content: "Hello! How can I help you today?" },
      { role: "user", content: "I need help with my order." },
      { role: "agent", content: "Sure. Can you share your order number?" }
    ],
    summary: "Customer called about an order inquiry.",
    userSentiment: "Neutral",
    callSuccessful: true
  }
};

export function getSamplePayload(kind) {
  if (kind === "sms") return sampleSmsPayload;
  if (kind === "voice") return sampleVoicePayload;
  if (kind === "call-ended") return sampleCallEndedPayload;
  throw new Error(`Unknown sample payload kind: ${kind}`);
}
