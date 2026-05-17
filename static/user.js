/* Concorde — User POV (WhatsApp-style, multi-persona) */

const $ = (sel, root = document) => root.querySelector(sel);

const PERSONAS = {
  'uber-david': {
    id: 'uber-david',
    name: 'David',
    role: 'uber_driver',
    subtitle: 'Uber driver · Toyota Camry',
    initials: 'D',
    color: 'linear-gradient(135deg, #1f2937, #0b1220)',
    preview: 'Tap to chat with David',
  },
  'uber-vivya': {
    id: 'uber-vivya',
    name: 'Vivya',
    role: 'uber_driver',
    subtitle: 'Uber driver · Tesla Model 3',
    initials: 'V',
    color: 'linear-gradient(135deg, #0f3a2e, #062019)',
    preview: 'Tap to chat with Vivya',
  },
  walmart: {
    id: 'walmart',
    name: 'Walmart Support',
    role: 'walmart_cs',
    subtitle: 'Walmart Grocery',
    initials: 'W',
    color: 'linear-gradient(135deg, #0071dc, #003a73)',
    preview: 'Tap to chat with Walmart',
  },
};
const PERSONA_ORDER = ['uber-david', 'uber-vivya', 'walmart'];

const threads = Object.fromEntries(PERSONA_ORDER.map((id) => [id, []]));
let activePersonaId = null;

const screens = {
  chats: $('[data-screen="chats"]'),
  thread: $('[data-screen="thread"]'),
  calls: $('[data-screen="calls"]'),
  call: $('[data-screen="call"]'),
};
const threadEl = $('#thread');
const composer = $('#composer');
const composerText = $('#composerText');
const threadName = $('#threadName');
const threadAvatar = $('#threadAvatar');
const threadStatus = $('#threadStatus');
const callName = $('#callName');
const callAvatar = $('#callAvatar');
const callStatus = $('#callStatus');
const callTimer = $('#callTimer');
const callSay = $('#callSay');
const callSayText = $('#callSayText');

let activeScreen = 'chats';
let callStartTs = null;
let callTimerHandle = null;
let inCall = false;

/* ---------- routing ---------- */

function show(name) {
  Object.entries(screens).forEach(([k, el]) => { el.hidden = k !== name; });
  activeScreen = name;
}

document.addEventListener('click', (e) => {
  if (e.target.closest('[data-back]')) { show(inCall ? 'call' : 'chats'); return; }
  const goto = e.target.closest('[data-goto]');
  if (goto) { show(goto.dataset.goto); return; }
});

$('#startCall').addEventListener('click', () => activePersonaId && startCall(activePersonaId));
$('#startVideo').addEventListener('click', () => activePersonaId && startCall(activePersonaId));
$('#endBtn').addEventListener('click', endCall);
$('#muteBtn').addEventListener('click', (e) => e.currentTarget.classList.toggle('callbtn--active'));
$('#spkBtn').addEventListener('click', (e) => e.currentTarget.classList.toggle('callbtn--active'));

/* ---------- theme ---------- */

const storedTheme = localStorage.getItem('concorde:theme');
if (storedTheme) document.documentElement.setAttribute('data-theme', storedTheme);

$('#themeToggle').addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('concorde:theme', next);
});

/* ---------- rendering ---------- */

function timeStr(d = new Date()) {
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function avatarHTML(persona, modifier = '') {
  return `<div class="avatar ${modifier}" style="background:${persona.color}">${persona.initials}</div>`;
}

function renderChatsList() {
  const ul = $('#chatList');
  ul.innerHTML = PERSONA_ORDER.map((id) => {
    const p = PERSONAS[id];
    const last = threads[id][threads[id].length - 1];
    const preview = last ? (last.side === 'out' ? `You: ${last.text}` : last.text) : p.preview;
    const time = last ? timeStr(last.ts) : '';
    return `
      <li class="chat-row" data-persona="${p.id}">
        ${avatarHTML(p)}
        <div class="chat-row__body">
          <div class="chat-row__line1">
            <span class="chat-row__name">${p.name}</span>
            <span class="chat-row__time">${time}</span>
          </div>
          <div class="chat-row__line2">
            <span class="chat-row__preview">${escapeHTML(preview)}</span>
          </div>
        </div>
      </li>`;
  }).join('');
  ul.querySelectorAll('[data-persona]').forEach((row) => {
    row.addEventListener('click', () => openThread(row.dataset.persona));
  });
}

function renderCallsList() {
  const ul = $('#callsList');
  ul.innerHTML = PERSONA_ORDER.map((id) => {
    const p = PERSONAS[id];
    return `
      <li class="chat-row">
        ${avatarHTML(p)}
        <div class="chat-row__body">
          <div class="chat-row__line1">
            <span class="chat-row__name">${p.name}</span>
            <span class="chat-row__time">tap to call</span>
          </div>
          <div class="chat-row__line2">
            <span class="chat-row__preview">${p.subtitle}</span>
          </div>
        </div>
        <button class="iconbtn iconbtn--green" data-call-persona="${p.id}" title="Call" aria-label="Call">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.4 2.1L8 9.7a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2.3z"/></svg>
        </button>
      </li>`;
  }).join('');
  ul.querySelectorAll('[data-call-persona]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      startCall(btn.dataset.callPersona);
    });
  });
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ---------- thread ---------- */

function openThread(personaId) {
  activePersonaId = personaId;
  const p = PERSONAS[personaId];
  threadName.textContent = p.name;
  threadAvatar.textContent = p.initials;
  threadAvatar.style.background = p.color;
  threadStatus.textContent = 'online';
  renderThread();
  show('thread');
  setTimeout(() => composerText.focus(), 50);
}

function renderThread() {
  threadEl.innerHTML = '';
  const day = document.createElement('div');
  day.className = 'day-chip';
  day.textContent = 'Today';
  threadEl.appendChild(day);

  const sys = document.createElement('div');
  sys.className = 'bubble bubble--sys';
  sys.textContent = 'Messages are end-to-end encrypted.';
  threadEl.appendChild(sys);

  threads[activePersonaId].forEach((m) => appendBubbleDOM(m));
  threadEl.scrollTop = threadEl.scrollHeight;
}

function appendBubbleDOM(msg) {
  if (msg.kind === 'toast') {
    const el = document.createElement('div');
    el.className = 'bubble bubble--toast';
    el.textContent = msg.text;
    threadEl.appendChild(el);
    return;
  }
  const el = document.createElement('div');
  el.className = `bubble bubble--${msg.side}`;
  el.textContent = msg.text;
  const meta = document.createElement('span');
  meta.className = 'bubble__meta';
  meta.textContent = timeStr(msg.ts);
  el.appendChild(meta);
  threadEl.appendChild(el);
}

function addBubble(personaId, text, side) {
  const msg = { side, text, ts: new Date() };
  threads[personaId].push(msg);
  if (personaId === activePersonaId && activeScreen === 'thread') {
    appendBubbleDOM(msg);
    threadEl.scrollTop = threadEl.scrollHeight;
  }
  renderChatsList();
}

function addToast(personaId, text) {
  const msg = { kind: 'toast', text, ts: new Date() };
  threads[personaId].push(msg);
  if (personaId === activePersonaId && activeScreen === 'thread') {
    appendBubbleDOM(msg);
    threadEl.scrollTop = threadEl.scrollHeight;
  }
}

/* ---------- sending ---------- */

let typingEl = null;
function showTyping() {
  if (typingEl || activeScreen !== 'thread') return;
  typingEl = document.createElement('div');
  typingEl.className = 'bubble bubble--in bubble--typing';
  typingEl.textContent = 'typing…';
  threadEl.appendChild(typingEl);
  threadEl.scrollTop = threadEl.scrollHeight;
  threadStatus.textContent = 'typing…';
}
function clearTyping() {
  if (typingEl) { typingEl.remove(); typingEl = null; }
  threadStatus.textContent = 'online';
}

async function sendToAgent(personaId, text) {
  const p = PERSONAS[personaId];
  showTyping();
  try {
    const res = await fetch('/api/demo/local-utterance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        caller_phone: '+13185160977',
        session_id: `user-${p.id}`,
        persona: { name: p.name, role: p.role },
      }),
    });
    const data = await res.json();
    clearTyping();
    if (data && data.text) {
      if (inCall && activeScreen === 'call' && activePersonaId === personaId) {
        callStatus.textContent = data.text;
      }
      addBubble(personaId, data.text, 'in');
    }
  } catch (err) {
    clearTyping();
    addBubble(personaId, 'Network error — could not send.', 'in');
  }
}

composer.addEventListener('submit', (e) => {
  e.preventDefault();
  if (!activePersonaId) return;
  const text = composerText.value.trim();
  if (!text) return;
  addBubble(activePersonaId, text, 'out');
  composerText.value = '';
  sendToAgent(activePersonaId, text);
});

callSay.addEventListener('submit', (e) => {
  e.preventDefault();
  if (!activePersonaId) return;
  const text = callSayText.value.trim();
  if (!text) return;
  callSayText.value = '';
  callStatus.textContent = `You: ${text}`;
  addBubble(activePersonaId, text, 'out');
  sendToAgent(activePersonaId, text);
});

/* ---------- call overlay ---------- */

function fmtElapsed(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function startCall(personaId) {
  activePersonaId = personaId;
  const p = PERSONAS[personaId];
  callName.textContent = p.name;
  callAvatar.textContent = p.initials;
  callAvatar.style.background = p.color;
  inCall = true;
  show('call');
  callStatus.textContent = 'Calling…';
  callTimer.hidden = true;
  callStartTs = null;
  if (callTimerHandle) clearInterval(callTimerHandle);

  setTimeout(() => {
    if (!inCall) return;
    callStatus.textContent = 'Connected';
    callTimer.hidden = false;
    callStartTs = Date.now();
    callTimerHandle = setInterval(() => {
      if (!callStartTs) return;
      callTimer.textContent = fmtElapsed(Date.now() - callStartTs);
    }, 500);
    setTimeout(() => callSayText.focus(), 100);
  }, 900);
}

function endCall() {
  inCall = false;
  if (callTimerHandle) { clearInterval(callTimerHandle); callTimerHandle = null; }
  callStartTs = null;
  show('chats');
}

/* ---------- SSE side-effects ---------- */

function subscribeEvents() {
  const es = new EventSource('/events');
  es.addEventListener('message', (ev) => {
    let payload; try { payload = JSON.parse(ev.data); } catch { return; }
    handleEvent(payload);
  });
}

function handleEvent({ type, data }) {
  if (!type || !data) return;
  switch (type) {
    case 'uber_rerouted':
      ['uber-david', 'uber-vivya'].forEach((id) => {
        addToast(id, `Route updated → ${data.to}${data.door ? ' · ' + data.door : ''} (${data.eta_minutes} min)`);
      });
      break;
    case 'walmart_substitution_proposed':
      addToast('walmart', `Substitution proposed: ${data.from || ''} → ${data.to || ''}`);
      break;
    case 'walmart_substitution_applied':
      addToast('walmart', 'Substitution applied');
      break;
    case 'call_ended':
      if (inCall) endCall();
      break;
    default: break;
  }
}

/* ---------- boot ---------- */

renderChatsList();
renderCallsList();
subscribeEvents();
show('chats');
