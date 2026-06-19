from __future__ import annotations

import unittest

from npc_harness import initial_world_state, run_npc_harness_step


class NPCHarnessTest(unittest.TestCase):
    def test_multi_agent_reveals_private_memory_and_triggers_message(self) -> None:
        world = initial_world_state()
        before = world["npcs"]["boss"]["suspicion"]["robot"]

        result = run_npc_harness_step(
            world=world,
            target_npc="hacker",
            player_message="Did you see anything near the vault?",
            mode="multi_agent",
            weave_mode="disabled",
            redis_mode="fake",
        )

        step = result["step"]
        self.assertIn("Hacker claims Robot was near the vault at 22:14.", step["world"]["shared_memory"])
        self.assertGreater(step["world"]["npcs"]["boss"]["suspicion"]["robot"], before)
        self.assertEqual(step["orchestrator_update"]["messages"][0]["from"], "boss")
        self.assertEqual(step["orchestrator_update"]["messages"][0]["to"], "robot")
        self.assertEqual(len(result["redis_events"]), 3)

    def test_classic_mode_does_not_propagate_between_npcs(self) -> None:
        world = initial_world_state()

        result = run_npc_harness_step(
            world=world,
            target_npc="hacker",
            player_message="Did you see anything near the vault?",
            mode="classic",
            weave_mode="disabled",
            redis_mode="fake",
        )

        step = result["step"]
        self.assertEqual(step["orchestrator_update"]["messages"], [])
        self.assertEqual(step["world"]["message_bus"], [])
        self.assertEqual(len(step["world"]["shared_memory"]), len(world["shared_memory"]))


if __name__ == "__main__":
    unittest.main()
