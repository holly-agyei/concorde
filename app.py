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
from agent.doordash_browser_agent import (
    get_doordash_session,
    handle_doordash_text,
    is_doordash_message,
    reset_doordash_session,
)
from agent.walmart_browser_agent import (
    get_walmart_session,
    handle_walmart_text,
    is_walmart_message,
    reset_walmart_session,
)
from events import encode_sse, push_event, subscribe, unsubscribe
from integrations.agentphone import verify_webhook
from mocks import uber, walmart


app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.get("/")
def index():
    return jsonify(
        {
            "service": "concorde",
            "mode": "server-side",
            "primary_flow": "Text -> service browser agent -> guarded live site action",
            "endpoints": {
                "walmart_text": "POST /api/walmart/text",
                "doordash_text": "POST /api/doordash/text",
                "agent_chat": "POST /api/agent/chat",
                "walmart_session": "GET /api/walmart/session/<session_id>",
                "doordash_session": "GET /api/doordash/session/<session_id>",
                "agentphone": "POST /webhook/agentphone",
                "state": "GET /api/state",
            },
        }
    )


@app.get("/demo")
def demo_index():
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


@app.post("/api/walmart/text")
def api_walmart_text():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message") or payload.get("text") or ""
    session_id = payload.get("session_id") or payload.get("conversationId") or "walmart-local"
    caller = payload.get("caller_phone") or payload.get("from") or "+13185160977"
    result = handle_walmart_text(session_id, caller, message, source="api")
    return jsonify(result)


@app.get("/api/walmart/session/<session_id>")
def api_walmart_session(session_id):
    return jsonify({"session_id": session_id, "session": get_walmart_session(session_id)})


@app.post("/api/walmart/session/<session_id>/reset")
def api_walmart_session_reset(session_id):
    reset_walmart_session(session_id)
    push_event("walmart_text_session_reset", {"session_id": session_id})
    return jsonify({"status": "ok", "session_id": session_id})


@app.post("/api/doordash/text")
def api_doordash_text():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message") or payload.get("text") or ""
    session_id = payload.get("session_id") or payload.get("conversationId") or "doordash-local"
    caller = payload.get("caller_phone") or payload.get("from") or "+13185160977"
    result = handle_doordash_text(session_id, caller, message, source="api")
    return jsonify(result)


@app.get("/api/doordash/session/<session_id>")
def api_doordash_session(session_id):
    return jsonify({"session_id": session_id, "session": get_doordash_session(session_id)})


@app.post("/api/doordash/session/<session_id>/reset")
def api_doordash_session_reset(session_id):
    reset_doordash_session(session_id)
    push_event("doordash_text_session_reset", {"session_id": session_id})
    return jsonify({"status": "ok", "session_id": session_id})


@app.post("/api/agent/chat")
def api_agent_chat():
    payload = request.get_json(silent=True) or {}
    return jsonify(_handle_agent_chat(payload, source="user-ui"))


@app.post("/webhook/agentphone")
def agentphone_webhook():
    raw_body = request.get_data(as_text=True)
    secret = os.getenv("AGENT_PHONE_WEBHOOK_SECRET")
    skip_verify = config.truthy("AGENT_PHONE_SKIP_VERIFY")
    if skip_verify:
        # Dev-only escape hatch: bypass signature check so local curl/test scripts work
        # without a real AgentPhone signature. Never enable in production.
        pass
    else:
        verification = verify_webhook(
            raw_body,
            request.headers.get("X-Webhook-Signature"),
            request.headers.get("X-Webhook-Timestamp"),
            secret,
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
        message = data.get("message") or data.get("text") or data.get("body") or ""
        push_event("incoming_message", {"from": caller_phone, "text": message, "channel": channel})
        routed = _route_user_message(session_id, caller_phone, message, source=channel)
        if routed["route"] == "doordash":
            return jsonify({"status": "ok", "text": routed["text"], "doordash": routed["doordash"]})
        if routed["route"] == "walmart":
            return jsonify({"status": "ok", "text": routed["text"], "walmart": routed["walmart"]})
        return jsonify({"status": "ok", "text": routed["text"]})

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
    return jsonify(_handle_agent_chat(payload, source="local-demo"))


def _voice_stream(session_id, caller_phone, transcript):
    def generate():
        yield json.dumps({"text": "One moment, let me check.", "interim": True}) + "\n"
        routed = _route_user_message(session_id, caller_phone, transcript, source="voice")
        yield json.dumps({"text": routed["text"]}) + "\n"

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


def _route_user_message(session_id, caller_phone, text, source="api", persona=None):
    """Shared router for SMS, voice, and the user-UI chat.

    Returns {"text": str, "route": "doordash"|"walmart"|"brain", ...extras}.
    """
    persona = persona if isinstance(persona, dict) else {}
    role = persona.get("role", "")
    persona_id = persona.get("id", "")

    if role == "doordash_cs" or persona_id == "doordash":
        result = handle_doordash_text(session_id, caller_phone, text, source=source)
        return {"text": result["reply"], "route": "doordash", "doordash": result}

    if role == "walmart_cs" or persona_id == "walmart":
        result = handle_walmart_text(session_id, caller_phone, text, source=source)
        return {"text": result["reply"], "route": "walmart", "walmart": result}

    if is_doordash_message(text):
        result = handle_doordash_text(session_id, caller_phone, text, source=source)
        return {"text": result["reply"], "route": "doordash", "doordash": result}

    if is_walmart_message(text):
        result = handle_walmart_text(session_id, caller_phone, text, source=source)
        return {"text": result["reply"], "route": "walmart", "walmart": result}

    final = respond(session_id, caller_phone, text, persona=persona)
    return {"text": final, "route": "brain"}


def _handle_agent_chat(payload, source="api"):
    text = payload.get("message") or payload.get("text") or ""
    caller = payload.get("caller_phone") or payload.get("from") or "+13185160977"
    session_id = payload.get("session_id") or payload.get("conversationId") or "local-demo"
    persona = payload.get("persona") if isinstance(payload.get("persona"), dict) else {}

    routed = _route_user_message(session_id, caller, text, source=source, persona=persona)
    routed["state"] = current_state()
    return routed


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
            "browser_use_dry_run": config.truthy("BROWSER_USE_DRY_RUN"),
            "doordash_profile_id": os.getenv("DOORDASH_BROWSER_PROFILE_ID", "Default"),
            "doordash_checkout_enabled": False,
        },
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    push_event("server_started", {"port": port})
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
