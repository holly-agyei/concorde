import json
import os
import sys

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import config  # noqa: F401
from agent.brain import reset_session, respond
from events import encode_sse, push_event, subscribe, unsubscribe
from integrations.agentphone import verify_webhook
from mocks import uber, walmart


app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/user")
def user_page():
    return send_from_directory("static", "user.html")


@app.get("/rider")
def rider_page():
    return send_from_directory("static", "rider.html")


@app.get("/driver")
def driver_page():
    return send_from_directory("static", "driver.html")


@app.get("/events")
def events():
    subscriber = subscribe()

    def stream():
        try:
            while True:
                yield encode_sse(subscriber.get())
        finally:
            unsubscribe(subscriber)

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


@app.get("/api/state")
def api_state():
    return jsonify(current_state())


@app.post("/api/demo/reset")
def api_reset():
    uber.reset()
    walmart.reset()
    push_event("demo_reset", {"message": "Demo state reset"})
    return jsonify(current_state())


@app.post("/api/demo/uber/reroute")
def api_uber_reroute():
    payload = request.get_json(silent=True) or {}
    destination = payload.get("destination", "SFO Terminal 3")
    result = uber.reroute_driver(destination)
    push_event(
        "uber_rerouted",
        {
            "from": result["previous"]["label"],
            "to": result["destination"]["label"],
            "door": result["destination"].get("door"),
            "eta_minutes": result["eta_minutes"],
            "distance_miles": result["distance_miles"],
        },
    )
    return jsonify(current_state())


@app.post("/api/demo/walmart/substitution")
def api_walmart_substitution():
    payload = request.get_json(silent=True) or {}
    if payload.get("apply"):
        result = walmart.apply_pending_substitution()
        push_event("walmart_substitution_applied", result)
    else:
        result = walmart.propose_substitution("cereal", payload.get("substitute"))
        push_event("walmart_substitution_proposed", result["pending"])
    return jsonify(current_state())


@app.post("/webhook/agentphone")
def agentphone_webhook():
    raw_body = request.get_data(as_text=True)
    verification = verify_webhook(
        raw_body,
        request.headers.get("X-Webhook-Signature"),
        request.headers.get("X-Webhook-Timestamp"),
        os.getenv("AGENT_PHONE_WEBHOOK_SECRET"),
    )
    if not verification["ok"]:
        return jsonify({"error": verification["reason"]}), 401

    try:
        payload = json.loads(raw_body or "{}")
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON"}), 400

    event = payload.get("event")
    channel = payload.get("channel")
    data = payload.get("data") or {}
    caller_phone = data.get("from") or data.get("fromNumber") or "+13185160977"
    session_id = data.get("callId") or data.get("conversationId") or payload.get("timestamp") or "local"

    if event == "agent.call_ended":
        reset_session(session_id)
        push_event("call_ended", {"session_id": session_id, "summary": data.get("summary")})
        return jsonify({"status": "ok"})

    if event != "agent.message":
        return jsonify({"status": "ignored"})

    if channel == "voice":
        transcript = data.get("transcript") or ""
        push_event("incoming_call", {"from": caller_phone, "session_id": session_id})
        return _voice_stream(session_id, caller_phone, transcript)

    if channel in {"sms", "mms", "imessage"}:
        message = data.get("message") or ""
        push_event("incoming_message", {"from": caller_phone, "text": message, "channel": channel})
        final = respond(session_id, caller_phone, message)
        return jsonify({"status": "ok", "text": final})

    return jsonify({"status": "ok"})


@app.post("/api/demo/passenger-event")
def api_passenger_event():
    payload = request.get_json(silent=True) or {}
    kind = payload.get("kind")
    persona = payload.get("persona")
    if persona not in {"uber-david", "uber-vivya"}:
        return jsonify({"ok": False, "reason": "unknown persona"}), 400
    if kind == "message":
        push_event("passenger_message", {
            "persona": persona,
            "text": payload.get("text", ""),
            "channel": payload.get("channel", "sms"),
            "from_name": payload.get("from_name", "Alex"),
        })
    elif kind in {"call_start", "call_end"}:
        push_event("passenger_call", {
            "persona": persona,
            "kind": kind,
            "from_name": payload.get("from_name", "Alex"),
        })
    else:
        return jsonify({"ok": False, "reason": "unknown kind"}), 400
    return jsonify({"ok": True})


@app.post("/api/demo/local-utterance")
def local_utterance():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    caller = payload.get("caller_phone", "+13185160977")
    session_id = payload.get("session_id") or "local-demo"
    persona = payload.get("persona")
    final = respond(session_id, caller, text, persona=persona)
    return jsonify({"text": final, "state": current_state()})


def _voice_stream(session_id, caller_phone, transcript):
    def generate():
        yield json.dumps({"text": "Let me check that for you.", "interim": True}) + "\n"
        final = respond(session_id, caller_phone, transcript)
        yield json.dumps({"text": final}) + "\n"

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


def current_state():
    return {
        "uber": uber.get_state(),
        "walmart": walmart.get_state(),
        "config": {
            "agentphone_number": os.getenv("AGENT_PHONE_PUBLIC_NUMBER", "+18154738613"),
            "walmart_mode": os.getenv("WALMART_MODE", "mock"),
            "gemini_enabled": bool(os.getenv("GEMINI_API_KEY")),
            "moss_enabled": bool(os.getenv("MOSS_PROJECT_ID") and os.getenv("MOSS_PROJECT_KEY")),
            "browser_use_enabled": bool(os.getenv("BROWSER_USE_API_KEY")),
        },
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    push_event("server_started", {"port": port})
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
