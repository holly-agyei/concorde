/* Uber driver POV — map + trip strip + always-visible chat + non-blocking call pill. */

const $ = (s, r = document) => r.querySelector(s);

const params = new URLSearchParams(location.search);
const DRIVER_KEY = (params.get('driver') || 'david').toLowerCase();
const DRIVER_PERSONA = DRIVER_KEY === 'vivya' ? 'uber-vivya' : 'uber-david';

const DRIVER_PROFILES = {
  david: { name: 'David', initials: 'D', vehicle: 'Toyota Camry · 7ABC123' },
  vivya: { name: 'Vivya', initials: 'V', vehicle: 'Tesla Model 3 · 8XYZ901' },
};
const me = DRIVER_PROFILES[DRIVER_KEY] || DRIVER_PROFILES.david;

$('#driverAvatar').textContent = me.initials;
$('#driverName').textContent = me.name;
$('#driverSub').textContent = me.vehicle;

/* ---------- map ---------- */
const map = UberMap.initMap('map', [37.7, -122.4], 11, { dark: true });
const route = new UberMap.RouteLayer(map, { color: '#06c167', showPickup: true });

let lastDriver = null;
let lastPickup = null;
let lastDestination = null;

function setEta(min) { $('#etaNum').textContent = String(min ?? '—'); }

async function bootState() {
  try {
    const res = await fetch('/api/state');
    const state = await res.json();
    const ride = state?.uber?.rides?.ride_001;
    const driver = state?.uber?.drivers?.driver_001;
    if (!ride || !driver) return;
    lastDriver = driver.current_location;
    lastPickup = ride.pickup;
    lastDestination = driver.destination;
    const riderName = ride.customer_name || 'Alex';
    $('#riderName').textContent = riderName;
    $('#riderAvatar').textContent = riderName[0];
    $('#callPillName').textContent = riderName;
    $('#riderRating').textContent = ride.rating || '4.9';
    $('#pickupLabel').textContent = ride.pickup?.label || '—';
    $('#dropLabel').textContent = driver.destination?.label || '—';
    $('#dropDoor').textContent = driver.destination?.door || '';
    $('#chatInput').placeholder = `Message ${riderName}…`;
    setEta(driver.eta_minutes);
    route.render({ driver: lastDriver, pickup: lastPickup, destination: lastDestination });
  } catch (_) { /* noop */ }
}

/* ---------- SSE ---------- */
function subscribe() {
  const es = new EventSource('/events');
  es.addEventListener('message', (ev) => {
    let p; try { p = JSON.parse(ev.data); } catch { return; }
    handle(p);
  });
}

function handle({ type, data }) {
  if (!type || !data) return;
  switch (type) {
    case 'uber_rerouted': return onReroute(data);
    case 'driver_notified': return toast(data.message || 'Notification');
    case 'passenger_message':
      if (data.persona === DRIVER_PERSONA) onPassengerMessage(data);
      break;
    case 'passenger_call':
      if (data.persona === DRIVER_PERSONA) onPassengerCall(data);
      break;
    case 'gemini_unavailable':
    case 'gemini_plan_failed':
    case 'gemini_final_failed':
      toast(`Gemini ${type.replace('gemini_', '')}: ${data.reason || data.error || 'check terminal'}`);
      break;
    case 'demo_reset':
      bootState();
      messages.length = 0; renderMessages();
      hideCallPill(); endActiveCall();
      break;
    default: break;
  }
}

async function onReroute(data) {
  $('#rerouteSub').textContent = `${data.to}${data.door ? ' · ' + data.door : ''}`;
  $('#rerouteBanner').hidden = false;
  setTimeout(() => { $('#rerouteBanner').hidden = true; }, 2400);

  $('#dropLabel').textContent = data.to;
  $('#dropDoor').textContent = data.door || '';
  setEta(data.eta_minutes);

  try {
    const res = await fetch('/api/state');
    const state = await res.json();
    const driver = state?.uber?.drivers?.driver_001;
    if (driver) {
      lastDestination = driver.destination;
      lastDriver = driver.current_location;
      route.render({ driver: lastDriver, pickup: lastPickup, destination: lastDestination });
    }
  } catch (_) { /* noop */ }
}

/* ---------- messaging ---------- */
const messages = [];

function timeStr(d = new Date()) {
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function renderMessages() {
  const body = $('#chatBody');
  if (!messages.length) {
    body.innerHTML = '<div class="chat-empty">No messages yet — say hi to your rider.</div>';
    return;
  }
  body.innerHTML = '';
  messages.forEach((m) => {
    const el = document.createElement('div');
    el.className = `chat-bubble chat-bubble--${m.side}`;
    el.textContent = m.text;
    const t = document.createElement('span');
    t.className = 'chat-bubble__time';
    t.textContent = timeStr(m.ts);
    el.appendChild(t);
    body.appendChild(el);
  });
  body.scrollTop = body.scrollHeight;
}

function onPassengerMessage(data) {
  messages.push({ side: 'in', text: data.text || '', ts: new Date() });
  renderMessages();
}

$('#chatForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = $('#chatInput').value.trim();
  if (!text) return;
  messages.push({ side: 'out', text, ts: new Date() });
  $('#chatInput').value = '';
  renderMessages();
});

/* ---------- call pill (non-blocking) ---------- */
let callTimer = null;
let callStart = null;
const callPill = $('#callPill');
const callText = callPill.querySelector('.call-pill__text');
const acceptBtn = $('#acceptBtn');
const declineBtn = $('#declineBtn');

function showCallPill(name = 'Alex') {
  callText.innerHTML = `<span id="callPillName">${name}</span> is calling…`;
  acceptBtn.hidden = false;
  acceptBtn.textContent = 'Accept';
  declineBtn.textContent = 'Dismiss';
  callPill.hidden = false;
}
function hideCallPill() {
  callPill.hidden = true;
  endActiveCall();
}

function startActiveCall(name = 'Alex') {
  callStart = Date.now();
  acceptBtn.hidden = true;
  declineBtn.textContent = 'End';
  const tick = () => {
    const s = Math.floor((Date.now() - callStart) / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    callText.textContent = `On call · ${name} · ${mm}:${ss}`;
  };
  tick();
  callTimer = setInterval(tick, 500);
}
function endActiveCall() {
  if (callTimer) { clearInterval(callTimer); callTimer = null; }
  callStart = null;
}

acceptBtn.addEventListener('click', () => startActiveCall($('#riderName').textContent || 'Alex'));
declineBtn.addEventListener('click', () => {
  hideCallPill();
  fetch('/api/demo/passenger-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persona: DRIVER_PERSONA, kind: 'call_end', from_name: me.name }),
  }).catch(() => {});
});

function onPassengerCall(data) {
  if (data.kind === 'call_start') {
    showCallPill($('#riderName').textContent || 'Alex');
  } else if (data.kind === 'call_end') {
    hideCallPill();
    toast('Call ended');
  }
}

/* ---------- toast ---------- */
let toastT = null;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  if (toastT) clearTimeout(toastT);
  toastT = setTimeout(() => { t.hidden = true; }, 2600);
}

/* ---------- boot ---------- */
bootState();
subscribe();
