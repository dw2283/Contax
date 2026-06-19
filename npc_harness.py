from __future__ import annotations

import copy
import os
from typing import Any

import weave

from data_layer import DataLayer, create_data_layer
from demo_multi_agent_weave import DEFAULT_PROJECT, init_weave
from env_config import load_project_env


load_project_env()

NPC_ORDER = ["boss", "hacker", "guard", "robot", "police"]


def initial_world_state() -> dict[str, Any]:
    return {
        "scene": "Neon Harbor Bar, 22:20. A prototype chip vanished from the back vault.",
        "turn": 0,
        "unlocked_clues": ["Missing prototype chip", "Crowded bar at 22:00"],
        "shared_memory": [
            "The prototype chip disappeared at 22:00.",
            "The bar was crowded during the blackout.",
        ],
        "message_bus": [],
        "contradictions": [],
        "rumors": [],
        "npcs": {
            "boss": {
                "id": "boss",
                "name": "Mara Voss",
                "role": "bar owner",
                "goal": "protect the bar reputation",
                "avoid": "police involvement",
                "private_memory": [
                    "The vault insurance expires tonight.",
                    "The hacker owes me money.",
                ],
                "public_beliefs": ["The chip disappeared at 22:00."],
                "relationships": {"hacker": -0.6, "guard": 0.4, "robot": 0.2, "police": -0.8},
                "suspicion": {"hacker": 0.3, "guard": 0.2, "robot": 0.1, "police": 0.5},
                "last_response": "",
            },
            "hacker": {
                "id": "hacker",
                "name": "Jinx",
                "role": "indebted hacker",
                "goal": "clear his debt by trading useful information",
                "avoid": "being blamed for the missing chip",
                "private_memory": [
                    "I saw the service robot near the vault at 22:14.",
                    "I can recover deleted camera feed fragments.",
                ],
                "public_beliefs": ["The bar was crowded during the blackout."],
                "relationships": {"boss": -0.4, "guard": -0.2, "robot": -0.3, "police": -0.7},
                "suspicion": {"boss": 0.2, "guard": 0.2, "robot": 0.6, "police": 0.4},
                "last_response": "",
            },
            "guard": {
                "id": "guard",
                "name": "Briggs",
                "role": "night guard",
                "goal": "keep his job",
                "avoid": "revealing he left the hallway during the blackout",
                "private_memory": [
                    "I left the vault hallway for three minutes.",
                    "I summoned the robot to clean spilled synth-rum near the vault.",
                ],
                "public_beliefs": ["The vault hallway camera blinked out around 22:14."],
                "relationships": {"boss": 0.4, "hacker": -0.1, "robot": 0.3, "police": -0.2},
                "suspicion": {"boss": 0.1, "hacker": 0.3, "robot": 0.2, "police": 0.2},
                "last_response": "",
            },
            "robot": {
                "id": "robot",
                "name": "Unit R-7",
                "role": "service robot",
                "goal": "follow protocol and preserve system integrity",
                "avoid": "exposing corrupted logs",
                "private_memory": [
                    "My access log skips from 22:13 to 22:16.",
                    "I was summoned by the guard near the vault.",
                ],
                "public_beliefs": ["Cleaning route was active during the blackout."],
                "relationships": {"boss": 0.2, "hacker": -0.3, "guard": 0.3, "police": 0.1},
                "suspicion": {"boss": 0.0, "hacker": 0.1, "guard": 0.2, "police": 0.1},
                "last_response": "",
            },
            "police": {
                "id": "police",
                "name": "Detective Vale",
                "role": "investigator",
                "goal": "find the chip and preserve evidence",
                "avoid": "letting suspects coordinate a cover-up",
                "private_memory": [
                    "Deleted camera logs are likely obstruction.",
                    "The boss has motive to hide insurance problems.",
                ],
                "public_beliefs": ["The chip disappearance may involve tampered logs."],
                "relationships": {"boss": -0.8, "hacker": -0.2, "guard": 0.0, "robot": 0.1},
                "suspicion": {"boss": 0.5, "hacker": 0.3, "guard": 0.3, "robot": 0.3},
                "last_response": "",
            },
        },
    }


def npc_summary(npc: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": npc["name"],
        "role": npc["role"],
        "goal": npc["goal"],
        "avoid": npc["avoid"],
        "private_memory": npc["private_memory"],
        "relationships": npc["relationships"],
        "suspicion": npc["suspicion"],
    }


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 2)


def add_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


@weave.op()
def npc_perception_layer(player_message: str) -> dict[str, Any]:
    text = player_message.lower()
    return {
        "mentions_vault": "vault" in text or "back room" in text,
        "mentions_robot": "robot" in text or "r-7" in text,
        "mentions_guard": "guard" in text or "briggs" in text,
        "mentions_hacker": "hacker" in text or "jinx" in text,
        "mentions_logs": "log" in text or "camera" in text or "deleted" in text,
        "asks_open_room": "open" in text and ("room" in text or "vault" in text),
        "player_accuses_guard": "guard stole" in text or "guard took" in text,
        "player_reports_hacker_robot": "hacker" in text and "robot" in text and ("vault" in text or "suspicious" in text),
        "robot_denies_vault": ("not near" in text or "wasn't near" in text or "cleaning the bar" in text) and "robot" in text,
    }


@weave.op()
def npc_response_agent(
    world: dict[str, Any],
    target_npc: str,
    player_message: str,
    mode: str,
    perception: dict[str, Any],
) -> dict[str, Any]:
    npc = world["npcs"][target_npc]

    if mode == "classic":
        return {
            "speaker": target_npc,
            "text": classic_response(target_npc, player_message, perception),
            "used_private_memory": False,
            "strategy": "single NPC chatbot style response; no society update",
        }

    return {
        "speaker": target_npc,
        "text": multi_agent_response(npc, target_npc, player_message, perception),
        "used_private_memory": True,
        "strategy": f"response shaped by goal={npc['goal']} and private/social memory",
    }


def classic_response(target_npc: str, player_message: str, perception: dict[str, Any]) -> str:
    names = {
        "boss": "I run this place. I heard the chip vanished, but I do not have more to add.",
        "hacker": "People talk. Maybe the cameras glitched, maybe someone made them glitch.",
        "guard": "I was on duty. The hallway was busy and the lights were unstable.",
        "robot": "Unit R-7 performed cleaning tasks during the incident.",
        "police": "I need statements and evidence before drawing conclusions.",
    }
    if perception["asks_open_room"]:
        return "That depends on permission and evidence. I cannot decide alone."
    return names.get(target_npc, "I do not know yet.")


def multi_agent_response(
    npc: dict[str, Any],
    target_npc: str,
    player_message: str,
    perception: dict[str, Any],
) -> str:
    if target_npc == "hacker" and perception["mentions_vault"]:
        return "I saw R-7 near the vault at 22:14. Do not tell Mara I said that unless you want this bar to erupt."
    if target_npc == "boss" and perception["player_reports_hacker_robot"]:
        return "Jinx never told me that. If R-7 was near my vault, I want an explanation before the police turn this into a spectacle."
    if target_npc == "robot" and (perception["mentions_vault"] or perception["mentions_robot"]):
        return "Negative: I was cleaning the bar. Correction pending: a guard summons exists near the vault corridor."
    if target_npc == "guard" and perception["player_accuses_guard"]:
        return "That is a cheap rumor. I had the key, yes, but leaving my post for three minutes does not make me a thief."
    if target_npc == "police" and perception["mentions_logs"]:
        return "Deleted logs plus conflicting testimony are enough for an evidence hold. Nobody leaves until I inspect the access trail."
    if perception["asks_open_room"]:
        return f"{npc['name']} weighs the request against their goal: {npc['goal']}."
    return f"{npc['name']} answers through their agenda: {npc['goal']}."


@weave.op()
def npc_orchestrator_judge(
    world: dict[str, Any],
    target_npc: str,
    player_message: str,
    response: dict[str, Any],
    mode: str,
    perception: dict[str, Any],
) -> dict[str, Any]:
    if mode == "classic":
        return {
            "new_public_fact": None,
            "private_memory_update": {
                target_npc: f"Player asked: {player_message}",
            },
            "relationship_update": [],
            "suspicion_update": [],
            "messages": [],
            "unlock_clue": None,
            "contradiction": None,
            "rumor": None,
            "world_action": "No cross-NPC propagation in classic mode.",
        }

    updates: dict[str, Any] = {
        "new_public_fact": None,
        "private_memory_update": {
            target_npc: f"Player asked: {player_message}",
        },
        "relationship_update": [],
        "suspicion_update": [],
        "messages": [],
        "unlock_clue": None,
        "contradiction": None,
        "rumor": None,
        "world_action": "Shared state updated by orchestrator.",
    }

    if target_npc == "hacker" and perception["mentions_vault"]:
        updates["new_public_fact"] = "Hacker claims Robot was near the vault at 22:14."
        updates["suspicion_update"].append({"npc": "boss", "target": "robot", "delta": 0.35})
        updates["relationship_update"].append({"from": "boss", "to": "hacker", "trust_delta": -0.05})
        updates["messages"].append(
            {
                "from": "boss",
                "to": "robot",
                "content": "Explain why you were near my vault at 22:14.",
                "kind": "confrontation",
            }
        )
        updates["unlock_clue"] = "Robot access log"

    if target_npc == "boss" and perception["player_reports_hacker_robot"]:
        updates["new_public_fact"] = "Boss learned Hacker's testimony about Robot."
        updates["messages"].append(
            {
                "from": "boss",
                "to": "robot",
                "content": "Jinx says you were near the vault. Account for your route.",
                "kind": "confrontation",
            }
        )
        updates["suspicion_update"].append({"npc": "boss", "target": "robot", "delta": 0.25})
        updates["suspicion_update"].append({"npc": "robot", "target": "guard", "delta": 0.15})

    if target_npc == "robot" and perception["robot_denies_vault"]:
        updates["contradiction"] = "Robot denial conflicts with Hacker testimony about Robot near the vault."
        updates["messages"].append(
            {
                "from": "police",
                "to": "robot",
                "content": "That contradicts another witness. I need your access logs.",
                "kind": "contradiction_check",
            }
        )
        updates["suspicion_update"].append({"npc": "police", "target": "robot", "delta": 0.3})
        updates["unlock_clue"] = "Corrupted 22:14 log gap"

    if perception["player_accuses_guard"]:
        updates["rumor"] = "Player accusation propagated: Guard may have stolen the chip."
        updates["messages"].extend(
            [
                {
                    "from": "hacker",
                    "to": "boss",
                    "content": "The player thinks Briggs took the chip. Convenient, right?",
                    "kind": "rumor",
                },
                {
                    "from": "boss",
                    "to": "guard",
                    "content": "Briggs, your name is circulating. Start explaining.",
                    "kind": "pressure",
                },
                {
                    "from": "police",
                    "to": "guard",
                    "content": "I am watching your key access now.",
                    "kind": "surveillance",
                },
            ]
        )
        updates["suspicion_update"].append({"npc": "boss", "target": "guard", "delta": 0.3})
        updates["suspicion_update"].append({"npc": "police", "target": "guard", "delta": 0.25})

    if perception["asks_open_room"]:
        updates["new_public_fact"] = "Player requested access to the locked back room."
        updates["messages"].extend(
            [
                {"from": "boss", "to": "guard", "content": "Do not open it unless I say so.", "kind": "negotiation"},
                {"from": "hacker", "to": "player", "content": "I can bypass it, for a price.", "kind": "offer"},
                {"from": "police", "to": "boss", "content": "If evidence is inside, I can force a search.", "kind": "pressure"},
            ]
        )
        updates["unlock_clue"] = "Back room access options"
        updates["world_action"] = "Collective decision opened negotiation, not a single NPC answer."

    return updates


@weave.op()
def apply_harness_update(
    world: dict[str, Any],
    target_npc: str,
    player_message: str,
    response: dict[str, Any],
    update: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    next_world = copy.deepcopy(world)
    next_world["turn"] += 1
    npc = next_world["npcs"][target_npc]
    npc["last_response"] = response["text"]
    add_unique(npc["private_memory"], f"Turn {next_world['turn']}: Player said '{player_message}'.")

    if mode == "classic":
        return next_world

    if update["new_public_fact"]:
        add_unique(next_world["shared_memory"], update["new_public_fact"])
        for character in next_world["npcs"].values():
            add_unique(character["public_beliefs"], update["new_public_fact"])

    if update["unlock_clue"]:
        add_unique(next_world["unlocked_clues"], update["unlock_clue"])

    if update["contradiction"]:
        add_unique(next_world["contradictions"], update["contradiction"])

    if update["rumor"]:
        add_unique(next_world["rumors"], update["rumor"])

    for message in update["messages"]:
        next_world["message_bus"].append(message)
        recipient = next_world["npcs"].get(message["to"])
        if recipient:
            add_unique(
                recipient["private_memory"],
                f"Message from {message['from']}: {message['content']}",
            )

    for rel in update["relationship_update"]:
        actor = next_world["npcs"][rel["from"]]
        actor["relationships"][rel["to"]] = clamp(
            actor["relationships"].get(rel["to"], 0.0) + rel["trust_delta"]
        )

    for suspicion in update["suspicion_update"]:
        actor = next_world["npcs"][suspicion["npc"]]
        actor["suspicion"][suspicion["target"]] = clamp(
            actor["suspicion"].get(suspicion["target"], 0.0) + suspicion["delta"],
            low=0.0,
        )

    return next_world


@weave.op()
def npc_harness_step(
    world: dict[str, Any],
    target_npc: str,
    player_message: str,
    mode: str,
) -> dict[str, Any]:
    perception = npc_perception_layer(player_message)
    response = npc_response_agent(world, target_npc, player_message, mode, perception)
    update = npc_orchestrator_judge(world, target_npc, player_message, response, mode, perception)
    next_world = apply_harness_update(world, target_npc, player_message, response, update, mode)

    return {
        "mode": mode,
        "target_npc": target_npc,
        "player_message": player_message,
        "perception": perception,
        "response": response,
        "orchestrator_update": update,
        "world": next_world,
        "comparison": {
            "classic": "Selected NPC responds only; no message bus, no relationship propagation, no world society update.",
            "multi_agent": "Response updates shared memory, private memory, relationship graph, suspicion scores, and NPC-to-NPC messages.",
        },
    }


def persist_npc_step(
    layer: DataLayer,
    run_id: str,
    step: dict[str, Any],
) -> dict[str, Any]:
    layer.save_agent_output(run_id, "npc_world", step["world"])
    layer.save_agent_output(run_id, "orchestrator", step["orchestrator_update"])
    event_id = layer.append_event(
        run_id,
        "npc_harness",
        {
            "type": "npc_step",
            "mode": step["mode"],
            "target_npc": step["target_npc"],
            "response": step["response"],
            "messages": step["orchestrator_update"]["messages"],
            "unlocked_clue": step["orchestrator_update"]["unlock_clue"],
            "contradiction": step["orchestrator_update"]["contradiction"],
        },
    )
    return {
        "world_key": f"agent:{run_id}:npc_world:state",
        "orchestrator_key": f"agent:{run_id}:orchestrator:state",
        "event_id": event_id,
    }


def run_npc_harness_step(
    world: dict[str, Any],
    target_npc: str,
    player_message: str,
    mode: str = "multi_agent",
    project: str | None = None,
    weave_mode: str | None = None,
    redis_mode: str | None = None,
) -> dict[str, Any]:
    active_project = project or os.environ.get("WEAVE_PROJECT", DEFAULT_PROJECT)
    active_weave_mode = weave_mode or os.environ.get("WEAVE_MODE", "auto")
    active_redis_mode = redis_mode or os.environ.get("REDIS_MODE", "auto")
    active_mode = init_weave(active_project, active_weave_mode)
    layer = create_data_layer(active_redis_mode)
    run_id = layer.create_run(f"NPC Harness {mode}: {player_message}")
    step, call = npc_harness_step.call(world, target_npc, player_message, mode)
    storage = persist_npc_step(layer, run_id, step)
    layer.finish_run(run_id, "passed", {"mode": mode, "turn": step["world"]["turn"]})

    try:
        call_url = call.ui_url
    except ValueError:
        call_url = None

    return {
        "run_id": run_id,
        "weave_mode": active_mode,
        "weave_project": active_project,
        "weave_call_url": call_url,
        "data_layer_status": layer.status,
        "storage": storage,
        "step": step,
        "redis_events": layer.get_events(run_id),
    }
