#!/usr/bin/env node
import { createAgentPhoneClient } from "../src/agentphone-client.mjs";
import { loadAgentPhoneConfig } from "../src/env.mjs";

function readArg(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? null : process.argv[index + 1];
}

const dryRun = process.argv.includes("--dry-run") || !process.argv.includes("--live");
const placeCall = process.argv.includes("--place-call");
const agentId = readArg("--agent-id");
const toNumber = readArg("--to");
const initialGreeting = readArg("--initial-greeting") || "Hi, this is a test call from Concorde.";
const systemPrompt =
  readArg("--system-prompt") ||
  "You are a concise test agent. Confirm audio is working, ask one short question, and end politely.";
const fromNumberId = readArg("--from-number-id") || undefined;
const voice = readArg("--voice") || undefined;

const body = {
  agentId,
  toNumber,
  initialGreeting,
  systemPrompt,
  fromNumberId,
  voice
};

for (const key of Object.keys(body)) {
  if (body[key] === undefined || body[key] === null || body[key] === "") delete body[key];
}

if (!agentId || !toNumber) {
  console.error("Missing required args: --agent-id agt_... --to +15551234567");
  process.exit(1);
}

if (dryRun || !placeCall) {
  console.log(
    JSON.stringify(
      {
        dryRun: true,
        method: "POST",
        path: "/calls",
        body,
        liveRequirement: "To actually dial, pass both --live and --place-call."
      },
      null,
      2
    )
  );
  process.exit(0);
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
const result = await client.createOutboundCall(body);
console.log(JSON.stringify(result, null, 2));
