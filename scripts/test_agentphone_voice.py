#!/usr/bin/env python3
"""Simulate an AgentPhone voice webhook hitting /webhook/agentphone.

This does NOT touch any phone network. It posts a fake `agent.message` event
with `channel="voice"` and a DoorDash-flavored transcript, then prints the
streamed ndjson lines so we can confirm the voice path routes through the
DoorDash browser agent (not just the generic brain).

Usage:
    python3 scripts/test_agentphone_voice.py
    python3 scripts/test_agentphone_voice.py "your custom transcript here"

If the server is running on http://localhost:5000 we hit it over HTTP. Otherwise
we fall back to Flask's in-process test client so the script still works in CI.
"""
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Force the dev-mode skip so we don't have to forge a real HMAC signature.
os.environ.setdefault("AGENT_PHONE_SKIP_VERIFY", "1")


def build_payload(transcript: str) -> dict:
    return {
        "event": "agent.message",
        "channel": "voice",
        "timestamp": "2026-05-17T14:30:00Z",
        "agentId": "cmpa6fsnp085rjz008rwxt9g6",
        "data": {
            "callId": "voice_test_001",
            "numberId": "cmpa6fver0869jz00zapzbujw",
            "from": "+13185160977",
            "to": "+18154738613",
            "transcript": transcript,
            "direction": "inbound",
        },
    }


def post_via_http(payload: dict) -> bool:
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            "http://localhost:5000/webhook/agentphone",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"HTTP {resp.status} {resp.headers.get('Content-Type')}")
            print("--- streamed ndjson lines ---")
            for raw_line in resp:
                line = raw_line.decode("utf-8").rstrip("\n")
                if line:
                    print(line)
            print("--- end ---")
        return True
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
        print(f"[info] HTTP post failed ({exc!r}); falling back to in-process test client.")
        return False


def post_via_test_client(payload: dict) -> None:
    from app import app

    with app.test_client() as client:
        response = client.post(
            "/webhook/agentphone",
            data=json.dumps(payload),
            content_type="application/json",
        )
        print(f"TEST {response.status_code} {response.headers.get('Content-Type')}")
        print("--- streamed ndjson lines ---")
        body = response.get_data(as_text=True)
        for line in body.splitlines():
            if line.strip():
                print(line)
        print("--- end ---")


def main() -> int:
    transcript = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Hey can you change my doordash cart to pizza"
    )
    print(f"Simulated voice transcript: {transcript!r}")
    payload = build_payload(transcript)
    if not post_via_http(payload):
        post_via_test_client(payload)
    print(
        "\nCheck above: if you see DoorDash-flavored reply text and the server "
        "logs show doordash_browser activity, the voice path is routing correctly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
