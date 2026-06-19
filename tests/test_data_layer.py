from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from data_layer import create_data_layer, mask_redis_url


class RedisDataLayerTest(unittest.TestCase):
    def test_mask_redis_url_hides_password_and_endpoint(self) -> None:
        masked = mask_redis_url("redis://default:secret@example.redis.io:15114/0")

        self.assertEqual(masked, "redis://default:***@redacted/0")
        self.assertNotIn("secret", masked)
        self.assertNotIn("example.redis.io", masked)
        self.assertNotIn("15114", masked)

    def test_real_layer_status_does_not_include_endpoint(self) -> None:
        client = Mock()
        client.ping.return_value = True

        with patch("data_layer.redis.Redis.from_url", return_value=client):
            layer = create_data_layer(
                "real",
                redis_url="redis://default:secret@example.redis.io:15114/0",
            )

        self.assertEqual(layer.status, "redis:connected")
        self.assertNotIn("example.redis.io", layer.status)
        self.assertNotIn("15114", layer.status)

    def test_fake_layer_persists_outputs_and_events(self) -> None:
        layer = create_data_layer("fake")
        run_id = layer.create_run("debug a multi-agent workflow")

        state_key = layer.save_agent_output(run_id, "planner", {"plan": ["step one"]})
        event_id = layer.append_event(
            run_id,
            "planner",
            {"type": "agent_completed", "ok": True},
        )
        layer.finish_run(run_id, "passed", {"score": 1.0, "pass": True})

        self.assertIn(f"agent:{run_id}:planner:state", state_key)
        self.assertTrue(event_id)
        self.assertEqual(layer.get_agent_output(run_id, "planner"), {"plan": ["step one"]})

        events = layer.get_events(run_id)
        self.assertEqual(events[0]["payload"]["type"], "run_started")
        self.assertEqual(events[1]["agent"], "planner")
        self.assertEqual(events[-1]["payload"]["type"], "run_finished")


if __name__ == "__main__":
    unittest.main()
