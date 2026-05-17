const state = {
  current: null,
};

const els = {
  etaText: document.querySelector("#etaText"),
  dropoffText: document.querySelector("#dropoffText"),
  dropoffSub: document.querySelector("#dropoffSub"),
  destPin: document.querySelector("#destPin"),
  routePath: document.querySelector("#routePath"),
  eventLog: document.querySelector("#eventLog"),
  utteranceForm: document.querySelector("#utteranceForm"),
  utterance: document.querySelector("#utterance"),
  agentResponse: document.querySelector("#agentResponse"),
  manualReroute: document.querySelector("#manualReroute"),
  resetDemo: document.querySelector("#resetDemo"),
  proposeSub: document.querySelector("#proposeSub"),
  applySub: document.querySelector("#applySub"),
  substitutionText: document.querySelector("#substitutionText"),
  walmartMode: document.querySelector("#walmartMode"),
  geminiStatus: document.querySelector("#geminiStatus"),
  mossStatus: document.querySelector("#mossStatus"),
  browserStatus: document.querySelector("#browserStatus"),
};

const routePaths = {
  c: "M42 162 C88 174, 126 214, 164 256 S250 342, 286 386",
  d: "M42 162 C92 168, 132 190, 176 214 S232 248, 262 292",
};

function formatTime(ts) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(ts * 1000));
}

function eventMessage(event) {
  const data = event.data || {};
  switch (event.type) {
    case "incoming_call":
      return `Incoming call from ${data.from || "caller"}`;
    case "agent_transcript":
      return `Caller: ${data.text}`;
    case "gemini_plan":
      return `Gemini chose ${data.tool_count || 0} tool action(s)`;
    case "moss_lookup_started":
      return `Moss lookup: ${data.query}`;
    case "moss_lookup_finished":
      return `Moss returned ${data.count} result(s); top: ${data.top_doc || "none"}`;
    case "moss_lookup_failed":
      return `Moss fallback used: ${data.error}`;
    case "uber_trip_lookup":
      return `Active Uber trip found for ${data.customer}`;
    case "uber_rerouted":
      return `Driver rerouted: ${data.from} → ${data.to}`;
    case "driver_notified":
      return `Driver notification staged: ${data.message}`;
    case "walmart_order_lookup":
      return `Walmart order ${data.order_id} found`;
    case "walmart_substitution_proposed":
      return `Walmart substitution proposed: ${data.from} → ${data.to}`;
    case "walmart_substitution_applied":
      return data.substitution
        ? `Walmart substitution applied: ${data.substitution.from} → ${data.substitution.to}`
        : "Walmart substitution applied";
    case "browser_use_started":
      return "Browser Use started Walmart workflow";
    case "browser_use_failed":
      return `Browser Use blocked: ${data.error}`;
    case "agent_response":
      return `Agent: ${data.text}`;
    case "demo_reset":
      return "Demo state reset";
    default:
      return `${event.type}: ${JSON.stringify(data)}`;
  }
}

function addEvent(event) {
  const item = document.createElement("li");
  const time = document.createElement("time");
  time.dateTime = new Date(event.timestamp * 1000).toISOString();
  time.textContent = formatTime(event.timestamp);
  const text = document.createElement("span");
  text.textContent = eventMessage(event);
  item.append(time, text);
  els.eventLog.prepend(item);
  while (els.eventLog.children.length > 40) {
    els.eventLog.lastElementChild.remove();
  }
  if (event.type === "agent_response" && event.data?.text) {
    els.agentResponse.textContent = event.data.text;
  }
  if (event.type === "uber_rerouted" || event.type === "walmart_substitution_applied") {
    refreshState();
  }
}

function updateUber(data) {
  const ride = data.uber.rides.ride_001;
  const driver = data.uber.drivers[ride.driver_id];
  const dest = driver.destination;
  const isTerminalD = /terminal d/i.test(dest.label);
  els.dropoffText.textContent = dest.label;
  els.dropoffSub.textContent = `San Francisco International Airport · ${dest.door || "Door TBD"}`;
  els.etaText.textContent = `${driver.eta_minutes} min · ${driver.distance_miles} mi`;
  els.destPin.classList.toggle("terminal-d", isTerminalD);
  els.destPin.classList.toggle("terminal-c", !isTerminalD);
  els.routePath.setAttribute("d", isTerminalD ? routePaths.d : routePaths.c);
}

function updateWalmart(data) {
  const order = data.walmart.order_1042;
  const cereal = order.items.find((item) => item.sku === "cereal_honey_crunch");
  els.walmartMode.textContent = data.config.walmart_mode;
  if (order.pending_substitution) {
    els.substitutionText.textContent = `Pending: ${order.pending_substitution.to}`;
  } else if (cereal?.substitution) {
    els.substitutionText.textContent = `Applied: ${cereal.substitution}`;
  } else {
    els.substitutionText.textContent = "No substitution applied";
  }
}

function updateConfig(data) {
  els.geminiStatus.classList.toggle("on", data.config.gemini_enabled);
  els.mossStatus.classList.toggle("on", data.config.moss_enabled);
  els.browserStatus.classList.toggle("on", data.config.browser_use_enabled);
}

async function refreshState() {
  const response = await fetch("/api/state");
  const data = await response.json();
  state.current = data;
  updateUber(data);
  updateWalmart(data);
  updateConfig(data);
}

async function postJson(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

els.utteranceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = els.utterance.value.trim();
  if (!text) return;
  els.agentResponse.textContent = "Thinking…";
  const data = await postJson("/api/demo/local-utterance", { text });
  els.agentResponse.textContent = data.text;
  await refreshState();
});

els.manualReroute.addEventListener("click", async () => {
  await postJson("/api/demo/uber/reroute", { destination: "SFO Terminal D" });
  await refreshState();
});

els.proposeSub.addEventListener("click", async () => {
  await postJson("/api/demo/walmart/substitution", { substitute: "Cinnamon Oat Squares" });
  await refreshState();
});

els.applySub.addEventListener("click", async () => {
  await postJson("/api/demo/walmart/substitution", { apply: true });
  await refreshState();
});

els.resetDemo.addEventListener("click", async () => {
  await postJson("/api/demo/reset", {});
  els.agentResponse.textContent = "Waiting for the first call…";
  await refreshState();
});

const source = new EventSource("/events");
source.onmessage = (message) => {
  addEvent(JSON.parse(message.data));
};

refreshState();
