# Project Context

## The One-Line Pitch

We're building an AI agent that picks up the phone (or texts) on behalf of companies and their delivery/service workers — but unlike today's customer service bots, this agent has **real context** about the customer, the order, the worker, and the company's systems, and can **actually act** on those systems in real time during the call.

## Why This Matters

Every day, millions of people get stuck in a frustrating gap:

- They call a company, sit on hold for 20 minutes, just to do something that takes 30 seconds (like upgrading a flight from economy to first class).
- They call or text a delivery driver who can't pick up because they're driving — and now the customer is stuck, the driver is stuck, and the company loses money.
- They reach a "customer service AI" that has no real context — it doesn't know what they bought, where they are, or what they actually need, so it just routes them to a human queue.

The pain is always the same: **the person on the other end of the line — human or AI — doesn't have the context or the power to fix the problem.** So nothing gets resolved quickly.

We're fixing that.

## What We're Building

A voice/SMS agent that:

1. **Picks up calls and texts** that humans (drivers, support agents, busy people) can't or won't.
2. **Has full context** about the situation — who the customer is, what they ordered, where the driver is, what the company's inventory looks like, what the customer usually buys, the company's policies, etc.
3. **Can take real action** on the relevant platforms — reroute a driver's GPS, change a delivery address, swap an item in an order, process a refund, upgrade a flight, update a reservation, etc.
4. **Brings the human into the loop only when needed** — and when it does, it can do things like add the driver into a group call, hand off cleanly, take over again when the driver goes silent (e.g., parking, talking to police, handling traffic), and hand back when the driver returns.

The key shift: today's AI customer service is a glorified phone tree that eventually transfers you to a human. **Our agent doesn't transfer — it acts.**

## Stories That Explain the Idea

These are the real situations the agent is built to handle. The coding agent should keep these in mind as the north star — every feature should make one of these scenarios work.

### Story 1: The Delta Upgrade

A customer calls Delta Airlines because they want to upgrade from economy to first class on a flight tomorrow. It's a 2-minute task. But Delta has no human agent free and the hold time is 45 minutes.

Today: the customer waits, gives up, or pays more on the app.

With our agent: the agent picks up immediately. It already knows who's calling (from the phone number), pulls up their booking, checks first-class availability, quotes the upgrade price, takes payment, and confirms the new seat. The whole call takes 90 seconds. No human needed.

### Story 2: The Wrong Terminal at SFO

A customer books an Uber to SFO Terminal C. They get confused and walk to Terminal D. They call the driver to redirect. The driver is driving and can't pick up. They text — no response. Now the customer has to sprint to Terminal C before the driver cancels and they lose the fare.

With our agent: the customer calls the driver. The driver doesn't pick up, so the call rolls over to the agent. The customer says "I'm at Terminal D, not C." The agent confirms the change with the customer, updates the driver's destination in the Uber driver app (or the driver's GPS / Google Maps), and lets the driver know via a quick in-app notification. The driver arrives at the right place. No one loses money. No one's stressed.

### Story 3: The Walmart Substitution

A customer placed a Walmart grocery order. Before the delivery driver shows up, they realize the cereal they ordered (Cereal A) is going to be out of stock and they want a substitution.

Today: they call Walmart customer support. They sit through prompts. They identify themselves. They identify the order. The AI bot has no idea what they bought or what's actually available. Eventually it transfers them to a human, who also has to look everything up from scratch.

With our agent: the customer calls. The agent already knows it's them, already has their order open, already knows their purchase history. The customer says "I need to swap the cereal." The agent checks Walmart's live inventory at the fulfillment center, sees that Cereal B (which the customer also regularly buys) is in stock, and proactively offers it: "Cereal B is available, and I know you buy it often — want me to swap to that?" Done in 20 seconds.

### Story 4: The Building Switcheroo

A customer ordered Walmart delivery to Salesforce Tower 1. They walked over to Salesforce Tower 2 for a meeting. The Walmart app doesn't let them change the delivery address mid-route. They need to tell the driver. The driver is driving and won't pick up.

With our agent: the customer calls the driver's number. The driver doesn't pick up, so the agent does. The customer says "I'm in Tower 2, not Tower 1." The agent confirms it's a minor reroute (the buildings are 200 feet apart), updates the driver's GPS destination directly in the driver app, and sends the driver a heads-up. Driver shows up at the right tower. No confusion, no missed delivery.

### Story 5: The Group Call Handoff

A customer calls their Uber driver about a complicated change — they need to make a quick stop to pick up a friend along the way, and they want to negotiate the extra fare.

The driver can't pick up while driving, so the agent picks up. The agent handles the easy parts: confirming the stop, quoting the extra fare, getting customer agreement. But the customer wants to ask the driver directly about timing.

The agent loops the driver in — a group call. The driver answers (it's safer now, they've pulled over). The three of them — customer, driver, agent — talk it through. Mid-call, a cop pulls up behind the driver. The driver goes silent. The customer keeps asking questions. The agent seamlessly takes over: "The driver had to step away for a moment, but I can answer that — yes, the new ETA is 4:15." When the driver is free again, they rejoin and the agent steps back.

This is the moment that shows the agent isn't a phone tree — it's a colleague on the call.

## The Core Insight

Today's customer service AI is **stateless and powerless**. It doesn't know who you are, what you bought, or where the driver is. And even if it did, it can't actually *do* anything — it just routes you to a human.

Our agent is **stateful and powerful**:

- **Stateful**: it has live context on the customer, the order, the worker, the company's systems, and the history between all of them.
- **Powerful**: it can take real actions on enterprise platforms (rerouting drivers, swapping items, processing payments, updating bookings) — not just *read* information, but *change* it.

This is the difference between "AI that talks to you" and "AI that handles it."

## Who the Agent Represents

Importantly, the agent can sit on either side of the call:

- **Company-side agent**: picks up when you call Delta, Walmart, Uber, etc. Knows you, your orders, the company's systems.
- **Worker-side agent**: picks up when the driver/contractor can't (driving, busy, hands full). Knows the driver's route, the customer's situation, the order details.

In some scenarios both exist and they negotiate with each other or with humans. The mental model is: every party in a transaction can have an agent answering their phone, and those agents have real context and real power.

## What Makes This Different From Existing Customer Service AI

| Existing AI customer service | Our agent |
|---|---|
| Phone tree with NLP on top | Real conversation with context |
| No knowledge of your specific order/situation | Full live context on customer, order, worker, inventory |
| Can only read info to you | Can take action — change addresses, swap items, reroute GPS, process payments |
| Always transfers to human eventually | Resolves most things itself; loops humans in only when truly needed |
| Stateless between calls | Remembers history; gets smarter every interaction |
| One-on-one only | Can run group calls, hand off mid-call, take over when humans go silent |

## What We Need to Build for the Demo

For the hackathon demo, we don't need to integrate with the real Walmart, Uber, or Delta. We'll mock those merchant/dispatcher systems ourselves so we can fully control the data and the flow. What needs to be real:

- A real phone number people can call/text.
- A real voice agent with low-latency conversation.
- Real-time access to (mocked) order/driver/inventory data while the call is happening.
- Real actions taken on (mocked) backend systems during the call — e.g., the driver's "GPS" actually updates on a visible map, the "inventory" actually changes, the "booking" actually shows the upgrade.
- A group-call moment where a human joins, the agent and human share the call, and the agent takes over when the human goes quiet.

The demo we want to put on stage: a live phone call (or two), real visible state changes on a screen behind us as the agent acts, and one moment where everyone in the room says "wait, the agent just did that mid-call?"

## Tone and Personality of the Agent

The agent should feel like the best customer service rep you've ever talked to — calm, fast, competent, and already up to speed on your situation. Not chirpy, not robotic, not over-apologetic. Confident and direct. The kind of voice that makes you trust that the problem is being handled.

## What We Are NOT Building

- We are not building a general-purpose Jarvis or personal assistant.
- We are not building a chatbot widget on a website.
- We are not building a transcription or call-summary tool.
- We are not replacing humans for the hard, emotional, or nuanced calls. We're handling the 80% of calls that are simple, contextual, and action-oriented — the ones that today get stuck in hold queues or unanswered driver lines.

## The North Star

If, by the end of the build, someone can call a phone number, talk naturally, and watch real things change on a screen — an Uber rerouting, a Walmart order updating, a Delta seat getting upgraded — without ever talking to a human, **and** we can demo the moment where a human driver gets looped in and the agent gracefully shares the call with them, we've nailed it.