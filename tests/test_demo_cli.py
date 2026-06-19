from __future__ import annotations

import subprocess
import sys
import unittest


class DemoCliTest(unittest.TestCase):
    def test_demo_runs_with_fake_redis_and_disabled_weave(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "demo_multi_agent_weave.py",
                "--mode",
                "disabled",
                "--redis-mode",
                "fake",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("Weave mode: disabled", completed.stdout)
        self.assertIn("Data layer: fakeredis", completed.stdout)
        self.assertIn('"pass": true', completed.stdout)
        self.assertIn('"state_key"', completed.stdout)

    def test_demo_runs_with_redis_layer_off(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "demo_multi_agent_weave.py",
                "--mode",
                "disabled",
                "--redis-mode",
                "off",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("Data layer: off", completed.stdout)
        self.assertIn('"enabled": false', completed.stdout)


if __name__ == "__main__":
    unittest.main()
