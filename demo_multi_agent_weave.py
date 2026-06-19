from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import weave

from data_layer import DataLayer, create_data_layer
from env_config import load_project_env


load_project_env()

DEFAULT_PROJECT = "weavehacks-multi-agent-demo"
DATA_LAYER: DataLayer | None = None
AGENT_ORDER = ["planner", "researcher", "builder", "critic", "judge"]


def has_wandb_auth() -> bool:
    """Best-effort check that avoids triggering an interactive login prompt."""
    if os.environ.get("WANDB_API_KEY"):
        return True

    netrc_path = Path.home() / ".netrc"
    try:
        return netrc_path.exists() and "api.wandb.ai" in netrc_path.read_text()
    except OSError:
        return False


def init_weave(project: str, mode: str) -> str:
    should_trace_online = mode == "online" or (mode == "auto" and has_wandb_auth())

    if should_trace_online:
        try:
            weave.init(project)
            return "online"
        except Exception as exc:
            if mode == "online":
                raise RuntimeError(
                    "Could not initialize Weave online tracing. Run `wandb login` "
                    "or set WANDB_API_KEY, then retry."
                ) from exc
            print(f"Weave online init failed in auto mode; falling back to disabled: {exc}")

    weave.init(project, settings={"disabled": True})
    return "disabled"


@weave.op()
def persist_agent_output(run_id: str, agent: str, output: dict[str, Any]) -> dict[str, Any]:
    if DATA_LAYER is None or DATA_LAYER.status == "off":
        return {"enabled": False, "agent": agent}

    state_key = DATA_LAYER.save_agent_output(run_id, agent, output)
    event_id = DATA_LAYER.append_event(
        run_id,
        agent,
        {
            "type": "agent_completed",
            "output": output,
        },
    )
    return {
        "enabled": True,
        "agent": agent,
        "state_key": state_key,
        "event_id": event_id,
    }


@weave.op()
def persist_run_completion(
    run_id: str,
    passed: bool,
    judgment: dict[str, Any],
) -> dict[str, Any]:
    if DATA_LAYER is None or DATA_LAYER.status == "off":
        return {"enabled": False, "run_id": run_id}

    status = "passed" if passed else "failed"
    DATA_LAYER.finish_run(run_id, status, judgment)
    return {
        "enabled": True,
        "run_id": run_id,
        "status": status,
    }


@weave.op()
def planner_agent(goal: str) -> dict[str, Any]:
    lower_goal = goal.lower()
    risk_keywords = ["deploy", "payment", "api key", "production", "user data"]
    risk_flags = [keyword for keyword in risk_keywords if keyword in lower_goal]

    return {
        "agent": "planner",
        "goal": goal,
        "plan": [
            "Map the multi-agent workflow into traceable operations.",
            "Capture each agent's inputs, outputs, and decision notes.",
            "Run a critic pass that checks for missing context or risky actions.",
            "Return a compact final artifact with a measurable quality score.",
        ],
        "risk_flags": risk_flags,
    }


@weave.op()
def researcher_agent(goal: str, plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": "researcher",
        "facts": [
            "Weave traces decorated Python functions as ops.",
            "Nested op calls form a call tree for multi-agent debugging.",
            "The demo avoids real LLM calls so it can run without provider keys.",
        ],
        "questions_to_answer_before_real_integration": [
            "Which functions represent individual agents?",
            "Which fields contain sensitive data that should be redacted?",
            "Which metrics decide whether an agent response is good enough?",
        ],
        "plan_step_count": len(plan["plan"]),
        "goal_terms": sorted(set(goal.lower().replace(",", " ").split())),
    }


@weave.op()
def builder_agent(
    goal: str,
    plan: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    tracked_agents = [
        "planner_agent",
        "researcher_agent",
        "builder_agent",
        "critic_agent",
        "judge_agent",
    ]

    return {
        "agent": "builder",
        "implementation_brief": {
            "goal": goal,
            "tracked_agents": tracked_agents,
            "trace_root": "multi_agent_orchestrator",
            "expected_weave_view": "one parent call with nested child calls per agent",
        },
        "handoff_notes": [
            "Wrap each real agent function with @weave.op().",
            "Keep agent outputs structured so Weave tables are easy to scan.",
            "Add a judge or scorer op for repeatable quality checks.",
        ],
        "evidence_used": research["facts"],
        "risk_flags": plan["risk_flags"],
    }


@weave.op()
def critic_agent(draft: dict[str, Any]) -> dict[str, Any]:
    brief = draft["implementation_brief"]
    tracked_agents = brief["tracked_agents"]

    findings = []
    if len(tracked_agents) < 3:
        findings.append("Trace is too shallow for a meaningful multi-agent demo.")
    if "judge_agent" not in tracked_agents:
        findings.append("No judge/scorer agent is present.")
    if draft["risk_flags"]:
        findings.append("Goal contains risk-sensitive terms; add redaction checks.")

    return {
        "agent": "critic",
        "approved": not findings,
        "findings": findings,
        "recommended_next_step": (
            "Plug in the real project agents and keep this trace shape."
            if not findings
            else "Address critic findings before running this against real users."
        ),
    }


@weave.op()
def judge_agent(draft: dict[str, Any], critique: dict[str, Any]) -> dict[str, Any]:
    score = 1.0
    if critique["findings"]:
        score -= min(0.6, 0.2 * len(critique["findings"]))
    if not draft["handoff_notes"]:
        score -= 0.2
    if not draft["evidence_used"]:
        score -= 0.2

    return {
        "agent": "judge",
        "score": round(max(score, 0.0), 2),
        "pass": score >= 0.8,
        "rubric": {
            "trace_depth": "at least five nested agent ops",
            "observability": "structured inputs and outputs",
            "safety": "critic reports risk-sensitive terms",
        },
    }


@weave.op()
def multi_agent_orchestrator(
    goal: str,
    run_id: str,
    data_layer_status: str,
) -> dict[str, Any]:
    plan = planner_agent(goal)
    plan_persist = persist_agent_output(run_id, "planner", plan)

    research = researcher_agent(goal, plan)
    research_persist = persist_agent_output(run_id, "researcher", research)

    draft = builder_agent(goal, plan, research)
    draft_persist = persist_agent_output(run_id, "builder", draft)

    critique = critic_agent(draft)
    critique_persist = persist_agent_output(run_id, "critic", critique)

    judgment = judge_agent(draft, critique)
    judgment_persist = persist_agent_output(run_id, "judge", judgment)
    completion_persist = persist_run_completion(run_id, judgment["pass"], judgment)

    return {
        "run_id": run_id,
        "goal": goal,
        "data_layer_status": data_layer_status,
        "plan": plan,
        "research": research,
        "draft": draft,
        "critique": critique,
        "judgment": judgment,
        "storage": {
            "planner": plan_persist,
            "researcher": research_persist,
            "builder": draft_persist,
            "critic": critique_persist,
            "judge": judgment_persist,
            "completion": completion_persist,
        },
    }


def run_multi_agent(
    goal: str,
    project: str | None = None,
    weave_mode: str | None = None,
    redis_mode: str | None = None,
    redis_url: str | None = None,
) -> dict[str, Any]:
    global DATA_LAYER

    active_project = project or os.environ.get("WEAVE_PROJECT", DEFAULT_PROJECT)
    active_weave_mode = weave_mode or os.environ.get("WEAVE_MODE", "auto")
    active_redis_mode = redis_mode or os.environ.get("REDIS_MODE", "auto")

    active_mode = init_weave(active_project, active_weave_mode)
    DATA_LAYER = create_data_layer(active_redis_mode, redis_url)
    run_id = DATA_LAYER.create_run(goal)
    result, call = multi_agent_orchestrator.call(goal, run_id, DATA_LAYER.status)
    try:
        call_url = call.ui_url
    except ValueError:
        call_url = None

    return {
        "weave_mode": active_mode,
        "weave_project": active_project,
        "weave_call_url": call_url,
        "data_layer_status": DATA_LAYER.status,
        "run_id": run_id,
        "result": result,
        "redis": {
            "meta": DATA_LAYER.get_run_meta(run_id),
            "events": DATA_LAYER.get_events(run_id),
            "agent_outputs": {
                agent: DATA_LAYER.get_agent_output(run_id, agent)
                for agent in AGENT_ORDER
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Weave-instrumented multi-agent demo.")
    parser.add_argument(
        "--goal",
        default="Use Weave to observe and evaluate a multi-agent hackathon demo.",
        help="Goal passed to the demo agent graph.",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("WEAVE_PROJECT", DEFAULT_PROJECT),
        help="W&B project path, e.g. entity/project. Defaults to a local demo name.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "online", "disabled"],
        default=os.environ.get("WEAVE_MODE", "auto"),
        help="auto traces online only when W&B auth is already configured.",
    )
    parser.add_argument(
        "--redis-mode",
        choices=["auto", "real", "fake", "off"],
        default=os.environ.get("REDIS_MODE", "auto"),
        help="auto uses real Redis when available, otherwise fakeredis.",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL"),
        help="Redis connection URL. Defaults to redis://localhost:6379/0.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run = run_multi_agent(
        goal=args.goal,
        project=args.project,
        weave_mode=args.mode,
        redis_mode=args.redis_mode,
        redis_url=args.redis_url,
    )
    result = run["result"]

    print(f"Weave mode: {run['weave_mode']}")
    print(f"Weave project: {run['weave_project']}")
    print(f"Data layer: {run['data_layer_status']}")
    print(f"Run id: {run['run_id']}")
    if run["weave_call_url"]:
        print(f"Weave call: {run['weave_call_url']}")
    print(json.dumps(result["judgment"], indent=2))
    print("\nFinal handoff:")
    print(json.dumps(result["draft"]["implementation_brief"], indent=2))
    print("\nPersisted storage keys:")
    print(json.dumps(result["storage"], indent=2))

    if run["weave_mode"] == "disabled":
        print(
            "\nTracing upload is disabled. Run `wandb login` and rerun with "
            "`--mode online --project YOUR_ENTITY/weavehacks-demo` to view traces in Weave."
        )


if __name__ == "__main__":
    main()
