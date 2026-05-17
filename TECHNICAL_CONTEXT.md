# Technical Instructions

This document tells the coding agent **how** to build the project. The story and product vision live in `CONTEXT.md` — read that first. This file is the build spec.

## Hard Constraints

These are not negotiable. Do not suggest alternatives, do not "upgrade" them, do not add tools that aren't listed.

- **8-hour hackathon.** Every decision optimizes for shipping a working demo, not for production quality, scalability, or code cleanliness.
- **Team of 2.** Keep the surface area small. No microservices, no fancy abstractions, no premature generalization.
- **One hero demo scenario** (see below). Everything else is a stretch goal.
- **No database.** JSON files on disk, loaded into in-memory Python dicts at startup, written back on change.
- **No build step for the frontend.** Plain HTML/CSS/JS, served as static files from Flask. No React, no Vite, no bundler, no TypeScript.
- **Monorepo.** Single repository, single directory tree. npm only enters the picture if a JS library is actually needed on the frontend (likely not).

## The Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python Flask | Team knows it, fast to ship |
| LLM | Google Gemini | Sponsor (DeepMind), good tool-calling |
| Voice + SMS | AgentPhone | Sponsor, primary target track |
| Real-time context lookup | Moss | Sponsor, secondary target track |
| Memory across calls | Supermemory | Sponsor, supporting if time permits |
| Frontend | HTML + CSS + vanilla JS | No build step, ships fast |
| Map | Leaflet + OpenStreetMap tiles | No API key, no billing |
| Routing (driving directions) | OSRM public demo server | No API key, returns polyline |
| Live frontend updates | Server-Sent Events (SSE) from Flask | One-way, simple, perfect for "agent acted, screen updates" |
| Persistence | JSON files in `data/` | No DB, no migrations |
| Public URL for webhooks | ngrok | Required for AgentPhone callbacks |
| API style | REST for most things, SSE for the live feed |

**Do not introduce:** PostgreSQL, Redis, Docker, Kubernetes, Celery, RabbitMQ, WebSockets, Socket.IO, React, Vue, Svelte, Tailwind, TypeScript, Vite, Webpack, ORMs, auth libraries, testing frameworks (we'll test by demoing).

## The Hero Demo Scenario

**The Wrong Terminal at SFO.**

A customer (us, on a real phone) calls their Uber driver. The driver doesn't pick up. The call rolls to our agent. The customer says "I'm at Terminal D, not Terminal C." The agent confirms, updates the driver's destination, and the map on the projector visibly reroutes the driver from Terminal C to Terminal D in real time.

Everything in the codebase should make this scenario work flawlessly first. Other scenarios (Walmart substitution, Delta upgrade, group call) are stretch goals — do not build them until the hero is bulletproof.

## Project Structure

```
/
├── app.py                     # Flask entry point, routes, SSE endpoint
├── agent/
│   ├── __init__.py
│   ├── brain.py               # Gemini calls, system prompt, tool routing
│   ├── tools.py               # The functions the agent can call (reroute, lookup, etc.)
│   └── prompts.py             # System prompt(s) for the agent
├── integrations/
│   ├── agentphone.py          # AgentPhone webhook handling and outbound actions
│   ├── moss.py                # Moss semantic search wrapper
│   └── supermemory.py         # Supermemory wrapper (stretch)
├── mocks/
│   ├── uber.py                # Fake Uber: drivers, rides, locations, reroute action
│   ├── walmart.py             # Fake Walmart: orders, inventory, substitutions (stretch)
│   └── delta.py               # Fake Delta: bookings, upgrade action (stretch)
├── data/
│   ├── drivers.json           # Driver state (id, name, current_location, destination)
│   ├── rides.json             # Active rides (id, customer_phone, driver_id, destination)
│   ├── customers.json         # Customer profiles (phone, name, history)
│   ├── orders.json            # Walmart orders (stretch)
│   └── inventory.json         # Walmart inventory (stretch)
├── static/
│   ├── index.html             # The demo screen — map + live event log
│   ├── style.css
│   └── app.js                 # Leaflet map, SSE listener, marker/route updates
├── requirements.txt
├── .env.example               # GEMINI_API_KEY, AGENTPHONE_KEY, MOSS_KEY, etc.
├── README.md
└── CONTEXT.md                 # Product story (already written)
```

Keep it flat. Do not create deeper nesting "for organization."

## Data Models (JSON Shapes)

Keep these minimal. Add fields only when a feature actually needs them.

**`data/drivers.json`**
```json
{
  "driver_001": {
    "id": "driver_001",
    "name": "Marcus",
    "phone": "+1555...",
    "current_location": { "lat": 37.6213, "lng": -122.3790 },
    "destination": { "lat": 37.6190, "lng": -122.3830, "label": "SFO Terminal C" },
    "status": "en_route"
  }
}
```

**`data/rides.json`**
```json
{
  "ride_001": {
    "id": "ride_001",
    "customer_phone": "+1555...",
    "driver_id": "driver_001",
    "pickup": { "lat": 37.7749, "lng": -122.4194, "label": "Downtown SF" },
    "destination": { "lat": 37.6190, "lng": -122.3830, "label": "SFO Terminal C" },
    "status": "in_progress"
  }
}
```

**`data/customers.json`**
```json
{
  "+1555...": {
    "phone": "+1555...",
    "name": "Alex",
    "active_ride_id": "ride_001",
    "preferences": { "home_airport": "SFO" },
    "history": []
  }
}
```

## In-Memory State Pattern

```python
# At app startup
import json
with open("data/drivers.json") as f:
    DRIVERS = json.load(f)

# On change
def save_drivers():
    with open("data/drivers.json", "w") as f:
        json.dump(DRIVERS, f, indent=2)
```

That's the entire persistence layer. No ORM, no schema, no migrations.

## The Agent Brain (`agent/brain.py`)

The agent is a single Gemini call with tool/function-calling enabled. Each user utterance from AgentPhone becomes one turn. Conversation history is kept in memory keyed by the call ID, dropped when the call ends.

The system prompt should:
- Establish the agent's role (calm, fast, competent customer-service voice — see `CONTEXT.md`).
- Identify which company/worker the agent is representing for this call.
- List the tools available.
- Forbid making things up; if the agent doesn't have context, it should look it up via a tool, not guess.

The agent's tools (defined in `agent/tools.py`):

1. **`lookup_ride(customer_phone)`** — returns the active ride for this caller, or null.
2. **`lookup_driver(driver_id)`** — returns driver info including current location and destination.
3. **`reroute_driver(driver_id, new_destination_label)`** — resolves the label (e.g., "SFO Terminal D") to coordinates, updates the driver's destination, triggers an SSE event so the frontend redraws the route. **This is the core action of the hero demo.**
4. **`semantic_lookup(query)`** — calls Moss to pull relevant context (customer preferences, recent issues, FAQ-style company info). Use this to demonstrate the Moss integration visibly.
5. **`remember(key, value)`** and **`recall(key)`** — Supermemory wrappers (stretch).

Resolving destination labels to coordinates: hardcode a small dict of known places (SFO Terminal C, Terminal D, Salesforce Tower 1, etc.) inside `mocks/uber.py`. Do not call a geocoding API.

## AgentPhone Integration

**Before writing any other code, do this:**

1. Read AgentPhone's docs. Confirm:
   - How inbound calls are routed to a webhook.
   - How the agent's voice replies are sent back (does AgentPhone do TTS, or do we?).
   - Whether AgentPhone provides STT (speech-to-text) or we need to handle audio ourselves.
   - How to make outbound SMS (for the "heads-up to driver" step).
   - Whether conference calls and silence detection are supported (for the stretch group-call demo).

2. Get a test number and confirm a real phone call reaches a Flask endpoint via ngrok.

Do this validation in the first hour. If AgentPhone doesn't support something the demo needs, we need to know now.

The integration pattern:
- Inbound call hits `/webhook/agentphone/inbound` (POST).
- AgentPhone streams the caller's speech to us, or sends transcribed text — depends on their API. Handle whichever it is.
- We pass the utterance + conversation history to `agent.brain.respond()`.
- The agent returns a reply text (and may have called tools that mutated state).
- We hand the reply back to AgentPhone for TTS playback.
- After every tool call that changes visible state, emit an SSE event so the projector screen updates.

## Moss Integration

Moss is real-time semantic search built for voice agents. Use it as the `semantic_lookup` tool. For the hero demo, seed Moss with:
- A list of SFO terminals and what airlines they serve.
- Common FAQ-style facts ("Uber drivers can't legally answer calls while driving," "Wait time at SFO is X," etc.).
- The customer's preference data.

When the agent calls `semantic_lookup`, log it to the SSE event stream so the projector shows "Agent is looking up context via Moss…" — judges should *see* Moss being used.

## Supermemory Integration (stretch)

Only after the hero demo works end-to-end. Use it to remember:
- Past calls from this phone number.
- Past reroutes / past issues.

On a second demo call, the agent can say "last time you were at Terminal D too — should I send you there again?" That's the Supermemory wow moment. Don't build it until the hero is locked.

## The Frontend

A single page. Half the screen is a Leaflet map. The other half is a live event log (a styled `<div>` that prepends new events as they arrive via SSE).

**Map behavior:**
- Centered on SFO area at startup.
- A driver marker (car icon or just a colored dot) at the driver's current location.
- A destination marker at the driver's destination.
- A polyline route between them, fetched from OSRM:
  `https://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=full&geometries=geojson`
- When an SSE event of type `reroute` arrives, update the destination marker, re-fetch the OSRM route, redraw the polyline. The visible change is the whole demo.

**Event log behavior:**
- Listens to `/events` (the SSE endpoint).
- Each event renders as a one-line entry with a timestamp, an icon for the event type, and a short message. Examples:
  - 🔔 Incoming call from +1 (555) 123-4567
  - 🧠 Agent looked up ride via Moss
  - 📍 Agent rerouted driver: Terminal C → Terminal D
  - 💬 Agent sent SMS to driver

This log is what tells the judges in the audience what's happening behind the voice call.

## SSE Endpoint

```python
from flask import Response, stream_with_context
import queue

event_queue = queue.Queue()

def push_event(event_type, data):
    event_queue.put({"type": event_type, "data": data})

@app.route("/events")
def events():
    def stream():
        while True:
            event = event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
    return Response(stream_with_context(stream()), mimetype="text/event-stream")
```

Every tool that mutates visible state calls `push_event(...)`. The frontend's `EventSource("/events")` handler updates the map and log.

For a 2-person hackathon team, this is enough. Do not introduce a pub/sub system.

## Environment Variables

**The coding agent will not be given the actual `.env` file or any real API keys.** Instead, the repo contains a committed `.env.example` file that documents which variables are needed and the shape they take. The humans will create the real `.env` locally from this template before running the app.

`.env.example` (committed to the repo):
```
# Google Gemini — get from https://aistudio.google.com/apikey
GEMINI_API_KEY=your_gemini_key_here

# AgentPhone — get from the AgentPhone dashboard
AGENTPHONE_API_KEY=your_agentphone_key_here
AGENTPHONE_NUMBER=+15555555555

# Moss — real-time semantic search
MOSS_API_KEY=your_moss_key_here

# Supermemory (stretch goal — only needed if we build cross-call memory)
SUPERMEMORY_API_KEY=your_supermemory_key_here

# ngrok public URL the AgentPhone webhook should hit
# Set this after starting ngrok each session
NGROK_URL=https://your-subdomain.ngrok.io
```

Rules for the coding agent:

- **Read variable names only from `.env.example`.** Do not invent new env var names. If a feature needs a new secret, add it to `.env.example` with a placeholder value and a comment explaining what it is and where to get it.
- **Never hardcode keys or write real values into `.env.example`.** Placeholders only.
- **Load env vars with `python-dotenv`** at the top of `app.py`:
  ```python
  from dotenv import load_dotenv
  load_dotenv()
  GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
  ```
- **Fail fast on missing vars.** If a required env var is missing at startup, raise immediately with a clear message naming the missing variable. Do not let the app boot with `None` keys and fail mysteriously mid-call.
- **`.env` must be in `.gitignore` from commit one.** `.env.example` is committed; `.env` is not.
- **Do not log env var values, ever**, even in debug output.

## Pre-Hackathon Setup (do this BEFORE the clock starts)

1. Install Python 3.11+, Node (in case), ngrok, Flask, `google-generativeai`, `python-dotenv`, `requests`.
2. Get API keys for: Gemini, AgentPhone, Moss, Supermemory.
3. Confirm ngrok is authenticated.
4. Create a "hello world" Flask app, expose it via ngrok, confirm AgentPhone can hit it with a test call.
5. Confirm a basic Gemini call works from Python.
6. Confirm Leaflet renders a map with a marker in a plain HTML page.

If any of these don't work before hour 0, fix them before starting on real features.

## Hour-by-Hour Build Order

Suggested sequence. Person A = backend/agent. Person B = frontend/integrations.

- **Hour 0–1:** Pre-flight checks above. Repo scaffolded. Mock data files written. Both people confirm their dev environment works end-to-end (call hits Flask, Gemini responds, map renders).
- **Hour 1–2:** A: AgentPhone webhook → Gemini → reply text → AgentPhone TTS works for a dumb echo agent. B: Map + driver marker + destination marker + OSRM route renders correctly.
- **Hour 2–4:** A: Tools wired up — `lookup_ride`, `lookup_driver`, `reroute_driver` work and mutate state. B: SSE endpoint working. Frontend listens. Map reroutes when an event arrives.
- **Hour 4–5:** End-to-end test of the hero demo. Real call → agent answers → "I'm at Terminal D" → map reroutes live. Fix anything broken here. **This is the demo. Nothing else matters until this works.**
- **Hour 5–6:** Moss integration. `semantic_lookup` tool. Visible in event log. Polish the agent's voice/personality via prompt tuning.
- **Hour 6–7:** Stretch: Supermemory for cross-call memory, OR Walmart substitution scenario, OR group-call attempt.
- **Hour 7–8:** Demo rehearsal. Run the hero scenario 5 times end-to-end. Fix the flaky parts. Write the 60-second pitch. **Stop adding features.**

## Failure Modes to Avoid

- **Spending hour 6 debugging an integration that should've been validated in hour 1.** Especially AgentPhone. Validate first, build second.
- **Building all five scenarios shallowly.** Hero deep, others stretch.
- **Overengineering the agent.** It's one Gemini call with tool use. No agent framework. No LangChain. No CrewAI.
- **Losing the demo to a flaky API mid-stage.** Have a backup: a button on the frontend that manually triggers a `reroute` SSE event, so if the live voice call dies during the demo, we can still show the visual moment.
- **Pretty code over working code.** Refactor never. Ship.

## What "Done" Looks Like

A judge walks up. We dial a phone number on a real phone. The agent picks up. We say "I'm at the wrong terminal — I'm at Terminal D, not C." On the projector behind us, the event log fills in ("Agent looked up ride," "Agent rerouted driver"), and the route line on the map visibly redraws from Terminal C to Terminal D. The agent says "Got it, your driver is now heading to Terminal D, see you in 6 minutes." We hang up. Total elapsed: 45 seconds.

That's the bar. Build to it.