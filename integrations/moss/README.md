# Moss Setup for Concorde

This file is for coding agents working on the YC hackathon demo. Moss is the fast semantic context layer for the voice/SMS agent. Do not use it as the source of truth for live ride state; use it to retrieve contextual facts that make the agent feel informed during the call.

## Why We Use Moss

Concorde's hero demo is "Wrong Terminal at SFO": a caller reaches the agent because their driver cannot answer, says they are at Terminal D instead of Terminal C, and the agent updates the mock driver destination while the map reroutes live.

Moss should support this moment by retrieving relevant context quickly:

- SFO terminal aliases and pickup notes.
- Company/driver policy: drivers should not answer calls while driving.
- Minor reroute policy: Terminal C to Terminal D is close enough to confirm and update.
- Customer context summaries, such as prior terminal confusion or pickup preferences.

The visible product moment should be:

1. Agent looks up the active ride from mock Uber JSON.
2. Agent calls `semantic_lookup(...)`, backed by Moss.
3. The SSE event log shows "Moss: retrieved SFO terminal context".
4. Agent calls `reroute_driver(...)`, backed by mock Uber JSON.
5. The map route changes from Terminal C to Terminal D.

## Required Environment

Moss docs use these names:

```bash
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_project_key
MOSS_INDEX_NAME=concorde-demo
```

If a local `.env` currently has `moss_api_key`, treat that value as the Moss project id only if it came from the Project ID field in the Moss portal. Rename it to `MOSS_PROJECT_ID` so SDK/CLI examples work unchanged.

Never commit real Moss credentials. `.env` is ignored; `.env.example` contains placeholders only.

## Install Options

For the planned Flask app:

```bash
pip install moss
```

For quick terminal setup and debugging:

```bash
pip install moss-cli
```

The Moss CLI resolves credentials in this order: flags, `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`, then profiles created by `moss init`.

## Demo Index

Use one small index for the hackathon:

```bash
export MOSS_INDEX_NAME=concorde-demo
```

Seed it with concise documents. Moss documents need an `id`, `text`, and optional `metadata`.

Recommended seed corpus:

```json
[
  {
    "id": "sfo-terminal-c",
    "text": "SFO Terminal C is a domestic terminal pickup area. In this demo, the customer's original pickup is SFO Terminal C.",
    "metadata": { "category": "airport", "place": "SFO", "terminal": "C" }
  },
  {
    "id": "sfo-terminal-d",
    "text": "SFO Terminal D is close to Terminal C. A Terminal C to Terminal D pickup correction is a minor airport reroute.",
    "metadata": { "category": "airport", "place": "SFO", "terminal": "D" }
  },
  {
    "id": "driver-safety-policy",
    "text": "Drivers should not answer phone calls while driving. The agent may handle simple destination corrections and notify the driver.",
    "metadata": { "category": "policy", "topic": "driver_safety" }
  },
  {
    "id": "minor-reroute-policy",
    "text": "For minor pickup corrections at the same venue, confirm the new destination with the caller, update the driver route, and send a short driver notification.",
    "metadata": { "category": "policy", "topic": "reroute" }
  },
  {
    "id": "customer-terminal-context",
    "text": "The demo customer is at SFO and may confuse Terminal C and Terminal D. Prefer concise confirmation before rerouting.",
    "metadata": { "category": "customer_context", "topic": "airport_pickup" }
  }
]
```

Create the index with CLI:

```bash
moss index create concorde-demo -f data/moss_seed.json --model moss-minilm --wait
```

Query it:

```bash
moss query concorde-demo "caller is at Terminal D instead of Terminal C at SFO" --top-k 3 --alpha 0.6 --json
```

Use `moss-minilm` for the demo because the priority is low latency. Use `moss-mediumlm` only if retrieval quality is poor.

## Python Integration Shape

Create `integrations/moss.py` in the Flask app:

```python
import os
from moss import MossClient, QueryOptions

MOSS_PROJECT_ID = os.environ["MOSS_PROJECT_ID"]
MOSS_PROJECT_KEY = os.environ["MOSS_PROJECT_KEY"]
MOSS_INDEX_NAME = os.getenv("MOSS_INDEX_NAME", "concorde-demo")

client = MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY)
_loaded = False

async def load_moss():
    global _loaded
    if not _loaded:
        await client.load_index(MOSS_INDEX_NAME)
        _loaded = True

async def semantic_lookup(query, top_k=3, alpha=0.6):
    await load_moss()
    results = await client.query(
        MOSS_INDEX_NAME,
        query,
        QueryOptions(top_k=top_k, alpha=alpha),
    )
    return [
        {
            "id": doc.id,
            "text": doc.text,
            "score": doc.score,
            "metadata": getattr(doc, "metadata", {}) or {},
        }
        for doc in results.docs
    ]
```

Tool wrapper in `agent/tools.py`:

```python
async def semantic_lookup(query):
    push_event("moss_lookup_started", {"query": query})
    docs = await moss.semantic_lookup(query)
    push_event("moss_lookup_finished", {
        "query": query,
        "top_doc": docs[0]["id"] if docs else None,
        "count": len(docs),
    })
    return docs
```

If Moss fails during demo, catch the error, push an SSE warning, and continue with deterministic mock Uber rerouting. Moss should enhance the demo, not become a single point of failure.

## Agent Prompt Guidance

Tell the agent:

- Use `lookup_ride` for live ride state.
- Use `semantic_lookup` when the caller mentions ambiguous place names, airport terminals, policies, preferences, or "can you do this?" questions.
- Do not invent facts when Moss has no result.
- Keep spoken responses short; Moss results are internal context, not a paragraph to read aloud.

Example internal query:

```text
SFO Terminal D instead of Terminal C pickup correction; should the agent reroute the driver?
```

Example spoken response after tools complete:

```text
Got it. I updated your driver to Terminal D and sent them a heads-up. They should meet you there in about six minutes.
```

## Docs Used

- https://docs.moss.dev/docs
- https://docs.moss.dev/docs/start/quickstart.md
- https://docs.moss.dev/docs/integrate/authentication.md
- https://docs.moss.dev/docs/integrate/indexing-data.md
- https://docs.moss.dev/docs/integrate/retrieval.md
- https://docs.moss.dev/docs/integrations/moss-cli.md
