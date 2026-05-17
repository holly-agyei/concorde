#!/usr/bin/env node
import { createAgentPhoneClient } from "../src/agentphone-client.mjs";
import { loadAgentPhoneConfig, maskSecret } from "../src/env.mjs";

function readArg(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? null : process.argv[index + 1];
}

const dryRun = process.argv.includes("--dry-run") || !process.argv.includes("--live");
const agentId = readArg("--agent-id");
const variablesArg = readArg("--variables");
const variables = variablesArg ? JSON.parse(variablesArg) : undefined;
const body = { agentId, variables };

if (!agentId) {
  console.error("Missing --agent-id agt_...");
  process.exit(1);
}

if (dryRun) {
  console.log(JSON.stringify({ dryRun: true, method: "POST", path: "/calls/web", body }, null, 2));
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
const result = await client.createWebCall(body);

console.log(
  JSON.stringify(
    {
      callId: result.callId,
      accessToken: maskSecret(result.accessToken),
      note: "Access token is masked. Re-run with a frontend flow when you are ready to start a browser call."
    },
    null,
    2
  )
);
