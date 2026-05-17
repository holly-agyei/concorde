export class AgentPhoneApiError extends Error {
  constructor(message, { status, responseBody, path }) {
    super(message);
    this.name = "AgentPhoneApiError";
    this.status = status;
    this.responseBody = responseBody;
    this.path = path;
  }
}

function toQueryString(query) {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query || {})) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }

  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

async function parseResponse(response) {
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function createAgentPhoneClient({ apiKey, baseUrl = "https://api.agentphone.ai/v1", fetchImpl = fetch }) {
  if (!apiKey) throw new Error("AgentPhone API key is required");

  const normalizedBaseUrl = baseUrl.replace(/\/+$/, "");

  async function request(path, { method = "GET", query, body } = {}) {
    const url = `${normalizedBaseUrl}${path}${toQueryString(query)}`;
    const headers = {
      Authorization: `Bearer ${apiKey}`
    };

    const init = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }

    const response = await fetchImpl(url, init);
    const responseBody = await parseResponse(response);

    if (!response.ok) {
      const apiMessage = responseBody?.error?.message || responseBody?.message;
      throw new AgentPhoneApiError(apiMessage || `AgentPhone request failed with ${response.status}`, {
        status: response.status,
        responseBody,
        path
      });
    }

    return responseBody;
  }

  return {
    request,
    getUsage: () => request("/usage"),
    listAgents: (query = { limit: 100, offset: 0 }) => request("/agents", { query }),
    listNumbers: (query = { limit: 100, offset: 0 }) => request("/numbers", { query }),
    getWebhook: () => request("/webhooks"),
    listCalls: (query = { limit: 10, offset: 0 }) => request("/calls", { query }),
    createWebCall: (body) => request("/calls/web", { method: "POST", body }),
    createOutboundCall: (body) => request("/calls", { method: "POST", body })
  };
}
