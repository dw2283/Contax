from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import _public_redis_status, _redact_monitor_payload, app


class ApiServerTest(unittest.TestCase):
    def test_monitor_payload_redacts_redis_endpoints(self) -> None:
        payload = {
            "runs": {
                "ingest": {
                    "spans": [
                        {
                            "summary": "108 saved · redis:redis://default:***@example.redis.io:15114",
                        }
                    ]
                }
            }
        }

        redacted = _redact_monitor_payload(payload)

        self.assertEqual(_public_redis_status("redis:redis://default:***@example.redis.io:15114"), "redis:connected")
        self.assertEqual(redacted["runs"]["ingest"]["spans"][0]["summary"], "108 saved · redis:connected")
        self.assertNotIn("example.redis.io", str(redacted))
        self.assertNotIn("15114", str(redacted))

    def test_create_run_endpoint(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"WEAVE_MODE": "disabled", "REDIS_MODE": "fake"}):
            response = client.post(
                "/api/runs",
                json={"goal": "Build a CopilotKit mission control demo"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["weave_mode"], "disabled")
        self.assertEqual(data["data_layer_status"], "fakeredis")
        self.assertTrue(data["result"]["judgment"]["pass"])
        self.assertEqual(len(data["redis"]["events"]), 7)

    def test_npc_step_endpoint(self) -> None:
        client = TestClient(app)
        session = client.get("/api/npc/session")
        self.assertEqual(session.status_code, 200)
        world = session.json()["world"]

        response = client.post(
            "/api/npc/step",
            json={
                "world": world,
                "target_npc": "hacker",
                "player_message": "Did you see anything near the vault?",
                "mode": "multi_agent",
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["step"]["mode"], "multi_agent")
        self.assertEqual(data["step"]["orchestrator_update"]["messages"][0]["from"], "boss")
        self.assertEqual(data["step"]["orchestrator_update"]["messages"][0]["to"], "robot")


if __name__ == "__main__":
    unittest.main()
