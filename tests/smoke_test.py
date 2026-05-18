import json
import os
import unittest
from pathlib import Path

from app import app
from agent.doordash_browser_agent import reset_doordash_session
from agent.walmart_browser_agent import reset_walmart_session
from mocks import uber, walmart


class ConcordeSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls._fixture_paths = [
            root / "data" / "drivers.json",
            root / "data" / "rides.json",
            root / "data" / "walmart_order.json",
        ]
        cls._fixture_contents = {path: path.read_text(encoding="utf-8") for path in cls._fixture_paths}

    @classmethod
    def tearDownClass(cls):
        for path, content in cls._fixture_contents.items():
            path.write_text(content, encoding="utf-8")

    def setUp(self):
        os.environ["CONCORDE_OFFLINE_TESTS"] = "1"
        uber.reset()
        walmart.reset()
        reset_doordash_session("test-doordash")
        reset_walmart_session("test-walmart")
        self.client = app.test_client()

    def test_state_endpoint_returns_demo_state(self):
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("uber", body)
        self.assertIn("walmart", body)

    def test_uber_reroute_endpoint_updates_destination(self):
        response = self.client.post("/api/demo/uber/reroute", json={"destination": "SFO Terminal D"})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        driver = body["uber"]["drivers"]["driver_001"]
        self.assertEqual(driver["destination"]["label"], "SFO Terminal D")

    def test_walmart_substitution_can_be_proposed_and_applied(self):
        proposed = self.client.post("/api/demo/walmart/substitution", json={"substitute": "Cinnamon Oat Squares"})
        self.assertEqual(proposed.status_code, 200)
        applied = self.client.post("/api/demo/walmart/substitution", json={"apply": True})
        body = applied.get_json()
        cereal = body["walmart"]["order_1042"]["items"][0]
        self.assertEqual(cereal["substitution"], "Cinnamon Oat Squares")

    def test_agentphone_voice_returns_ndjson(self):
        payload = {
            "event": "agent.message",
            "channel": "voice",
            "timestamp": "2026-05-17T14:30:00Z",
            "agentId": "cmpa6fsnp085rjz008rwxt9g6",
            "data": {
                "callId": "test_call",
                "from": "+13185160977",
                "to": "+18154738613",
                "transcript": "I'm at Terminal D, not Terminal C.",
                "direction": "inbound",
            },
        }
        response = self.client.post(
            "/webhook/agentphone",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["Content-Type"])
        lines = [json.loads(line) for line in response.get_data(as_text=True).strip().splitlines()]
        self.assertTrue(lines[0]["interim"])
        self.assertIn("text", lines[-1])

    def test_walmart_text_endpoint_builds_browser_use_task(self):
        response = self.client.post(
            "/api/walmart/text",
            json={
                "session_id": "test-walmart",
                "caller_phone": "+13185160977",
                "message": "Open my Walmart order and change the cereal substitute to Cinnamon Oat Squares.",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("reply", body)
        self.assertEqual(body["browser_use"]["status"], "dry_run")
        self.assertIn("Walmart.com", body["browser_use"]["task"])

    def test_agentphone_sms_walmart_routes_to_browser_use_agent(self):
        payload = {
            "event": "agent.message",
            "channel": "sms",
            "timestamp": "2026-05-17T14:30:00Z",
            "data": {
                "conversationId": "test-walmart",
                "from": "+13185160977",
                "message": "I want to change my Walmart order substitution.",
            },
        }
        response = self.client.post(
            "/webhook/agentphone",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["walmart"]["browser_use"]["status"], "dry_run")

    def test_doordash_text_endpoint_builds_visible_browser_task(self):
        response = self.client.post(
            "/api/doordash/text",
            json={
                "session_id": "test-doordash",
                "caller_phone": "+13185160977",
                "message": "Open DoorDash and add pizza to cart but do not buy anything.",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("reply", body)
        self.assertEqual(body["doordash_browser"]["status"], "dry_run")
        self.assertIn("DoorDash", body["doordash_browser"]["task"])

    def test_user_chat_doordash_persona_routes_to_dynamic_browser_plan(self):
        response = self.client.post(
            "/api/agent/chat",
            json={
                "session_id": "user-doordash",
                "caller_phone": "+13185160977",
                "text": "Replace the pizza in my cart with sushi, but do not buy anything.",
                "persona": {"id": "doordash", "name": "DoorDash Support", "role": "doordash_cs"},
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["route"], "doordash")
        self.assertEqual(body["doordash"]["doordash_browser"]["status"], "dry_run")
        self.assertEqual(body["doordash"]["run"]["plan"]["action"], "replace")
        self.assertEqual(body["doordash"]["run"]["plan"]["remove_query"], "pizza")
        self.assertEqual(body["doordash"]["run"]["plan"]["search_term"], "sushi")


if __name__ == "__main__":
    unittest.main()
