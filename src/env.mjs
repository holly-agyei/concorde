import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const KEY_NAMES = ["AGENT_PHONE_API_KEY", "agent_phone_api_key", "AGENTPHONE_API_KEY"];
const WEBHOOK_SECRET_NAMES = ["AGENT_PHONE_WEBHOOK_SECRET", "agent_phone_webhook_secret", "WEBHOOK_SECRET"];

function parseEnvLine(line) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) return null;

  const equalsIndex = trimmed.indexOf("=");
  if (equalsIndex === -1) return null;

  const key = trimmed.slice(0, equalsIndex).trim();
  let value = trimmed.slice(equalsIndex + 1).trim();

  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1);
  }

  return key ? [key, value] : null;
}

export function parseEnv(contents) {
  const parsed = {};

  for (const line of contents.split(/\r?\n/)) {
    const pair = parseEnvLine(line);
    if (!pair) continue;
    const [key, value] = pair;
    parsed[key] = value;
  }

  return parsed;
}

export function findEnvFiles(startDir = process.cwd()) {
  const files = [];
  let current = resolve(startDir);

  while (true) {
    const candidate = join(current, ".env");
    if (existsSync(candidate)) files.push(candidate);

    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }

  return files;
}

export function loadEnvValues(startDir = process.cwd()) {
  const values = {};
  const files = findEnvFiles(startDir).reverse();

  for (const file of files) {
    Object.assign(values, parseEnv(readFileSync(file, "utf8")));
  }

  return {
    ...values,
    ...process.env
  };
}

export function getFirstValue(values, names) {
  for (const name of names) {
    const value = values[name];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

export function loadAgentPhoneConfig({ requireApiKey = false, startDir = process.cwd() } = {}) {
  const values = loadEnvValues(startDir);
  const apiKey = getFirstValue(values, KEY_NAMES);
  const webhookSecret = getFirstValue(values, WEBHOOK_SECRET_NAMES);
  const baseUrl = values.AGENT_PHONE_BASE_URL || "https://api.agentphone.ai/v1";

  if (requireApiKey && !apiKey) {
    throw new Error(
      "Missing AgentPhone API key. Save .env with AGENT_PHONE_API_KEY=... or agent_phone_api_key=..."
    );
  }

  return {
    apiKey,
    webhookSecret,
    baseUrl
  };
}

export function maskSecret(value) {
  if (!value) return null;
  if (value.length <= 8) return "****";
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

export function maskPhoneNumber(value) {
  if (!value) return null;
  const digits = value.replace(/\D/g, "");
  if (digits.length < 4) return "****";
  return `${value.startsWith("+") ? "+" : ""}***${digits.slice(-4)}`;
}
