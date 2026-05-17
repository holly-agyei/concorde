#!/usr/bin/env node
import { createAgentPhoneClient } from "../src/agentphone-client.mjs";
import { loadAgentPhoneConfig, maskPhoneNumber, maskSecret } from "../src/env.mjs";

function getItems(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.data)) return response.data;
  if (Array.isArray(response?.items)) return response.items;
  return [];
}

function hasAttachedNumber(agent) {
  return Array.isArray(agent.numbers) && agent.numbers.length > 0;
}

function summarizeAgent(agent) {
  return {
    id: agent.id,
    name: agent.name,
    voiceMode: agent.voiceMode || agent.voice_mode || null,
    numbers: Array.isArray(agent.numbers) ? agent.numbers.length : 0
  };
}

function summarizeNumber(number) {
  return {
    id: number.id,
    phoneNumber: maskPhoneNumber(number.phoneNumber || number.number || number.e164 || number.phone_number),
    agentId: number.agentId || number.agent_id || null
  };
}

let config;
try {
  config = loadAgentPhoneConfig({ requireApiKey: true });
} catch (error) {
  console.error(error.message);
  process.exit(1);
}

const { apiKey, baseUrl } = config;
const client = createAgentPhoneClient({ apiKey, baseUrl });

const [usage, agentsResponse, numbersResponse, webhook, callsResponse] = await Promise.all([
  client.getUsage().catch((error) => ({ error })),
  client.listAgents().catch((error) => ({ error })),
  client.listNumbers().catch((error) => ({ error })),
  client.getWebhook().catch((error) => ({ error })),
  client.listCalls({ limit: 5, offset: 0 }).catch((error) => ({ error }))
]);

function unwrap(label, result) {
  if (!result?.error) return result;
  return {
    label,
    error: {
      name: result.error.name,
      status: result.error.status,
      message: result.error.message
    }
  };
}

const agentsRaw = unwrap("agents", agentsResponse);
const numbersRaw = unwrap("numbers", numbersResponse);
const callsRaw = unwrap("calls", callsResponse);
const agents = getItems(agentsRaw);
const numbers = getItems(numbersRaw);
const calls = getItems(callsRaw);
const outboundReady = agents.some(hasAttachedNumber) || numbers.some((number) => number.agentId || number.agent_id);

console.log(
  JSON.stringify(
    {
      api: {
        baseUrl,
        apiKey: maskSecret(apiKey),
        authenticated: !usage?.error
      },
      usage: unwrap("usage", usage),
      agents: {
        count: agents.length,
        sample: agents.slice(0, 5).map(summarizeAgent)
      },
      numbers: {
        count: numbers.length,
        sample: numbers.slice(0, 5).map(summarizeNumber)
      },
      webhook: webhook?.error
        ? unwrap("webhook", webhook)
        : {
            configured: Boolean(webhook && Object.keys(webhook).length),
            id: webhook?.id || null,
            url: webhook?.url || null,
            contextLimit: webhook?.contextLimit ?? webhook?.context_limit ?? null
          },
      calls: {
        count: calls.length,
        sample: calls.slice(0, 5).map((call) => ({
          id: call.id,
          status: call.status,
          direction: call.direction,
          startedAt: call.startedAt || call.started_at || null
        }))
      },
      readiness: {
        webCallReady: agents.length > 0,
        outboundCallReady: outboundReady,
        notes: [
          agents.length ? null : "Create at least one agent before testing web calls.",
          outboundReady ? null : "Attach a phone number to an agent before placing outbound PSTN calls.",
          webhook?.url ? null : "Configure a webhook before testing webhook-mode voice calls."
        ].filter(Boolean)
      }
    },
    null,
    2
  )
);
