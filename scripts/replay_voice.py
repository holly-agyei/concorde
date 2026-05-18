#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app


payload = {
    "event": "agent.message",
    "channel": "voice",
    "timestamp": "2026-05-17T14:30:00Z",
    "agentId": "cmpa6fsnp085rjz008rwxt9g6",
    "data": {
        "callId": "local_call_001",
        "numberId": "cmpa6fver0869jz00zapzbujw",
        "from": "+13185160977",
        "to": "+18154738613",
        "transcript": "I'm at Terminal 3, not Terminal 2.",
        "direction": "inbound",
    },
}


with app.test_client() as client:
    response = client.post(
        "/webhook/agentphone",
        data=json.dumps(payload),
        content_type="application/json",
    )
    print(response.status_code)
    print(response.headers.get("content-type"))
    print(response.get_data(as_text=True))
