import json
import unittest

from app import app
from mocks import uber, walmart


class ConcordeSmokeTest(unittest.TestCase):
    def setUp(self):
        uber.reset()
        walmart.reset()
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


if __name__ == "__main__":
    unittest.main()
