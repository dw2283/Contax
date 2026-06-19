from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import redis

from env_config import load_project_env

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_REDIS_TIMEOUT_SECONDS = 3.0

load_project_env()


def mask_redis_url(url: str) -> str:
    parsed = urlsplit(url)
    username = parsed.username or ""
    auth = f"{username}:***@" if username else ""
    netloc = f"{auth}redacted"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


class DataLayer(Protocol):
    status: str

    def create_run(self, goal: str) -> str:
        ...

    def save_agent_output(self, run_id: str, agent: str, output: dict[str, Any]) -> str:
        ...

    def append_event(self, run_id: str, agent: str, event: dict[str, Any]) -> str:
        ...

    def finish_run(self, run_id: str, status: str, judgment: dict[str, Any]) -> None:
        ...

    def get_agent_output(self, run_id: str, agent: str) -> dict[str, Any] | None:
        ...

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        ...

    def get_run_meta(self, run_id: str) -> dict[str, str]:
        ...


@dataclass
class RedisDataLayer:
    client: redis.Redis
    status: str = "redis"

    def create_run(self, goal: str) -> str:
        run_id = str(uuid.uuid4())
        self.client.hset(
            self.run_meta_key(run_id),
            mapping={
                "goal": goal,
                "status": "running",
                "created_at": str(time.time()),
            },
        )
        self.append_event(run_id, "system", {"type": "run_started", "goal": goal})
        return run_id

    def save_agent_output(self, run_id: str, agent: str, output: dict[str, Any]) -> str:
        key = self.agent_state_key(run_id, agent)
        self.client.hset(
            key,
            mapping={
                "agent": agent,
                "output": json.dumps(output),
                "updated_at": str(time.time()),
            },
        )
        return key

    def append_event(self, run_id: str, agent: str, event: dict[str, Any]) -> str:
        event_id = self.client.xadd(
            self.run_events_key(run_id),
            {
                "agent": agent,
                "payload": json.dumps(event),
                "ts": str(time.time()),
            },
        )
        return str(event_id)

    def finish_run(self, run_id: str, status: str, judgment: dict[str, Any]) -> None:
        self.client.hset(
            self.run_meta_key(run_id),
            mapping={
                "status": status,
                "finished_at": str(time.time()),
                "judgment": json.dumps(judgment),
            },
        )
        self.append_event(
            run_id,
            "system",
            {"type": "run_finished", "status": status, "judgment": judgment},
        )

    def get_agent_output(self, run_id: str, agent: str) -> dict[str, Any] | None:
        value = self.client.hget(self.agent_state_key(run_id, agent), "output")
        if value is None:
            return None
        return json.loads(value)

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        events = []
        for event_id, fields in self.client.xrange(self.run_events_key(run_id)):
            payload = fields.get("payload", "{}")
            events.append(
                {
                    "id": str(event_id),
                    "agent": fields.get("agent"),
                    "payload": json.loads(payload),
                    "ts": fields.get("ts"),
                }
            )
        return events

    def get_run_meta(self, run_id: str) -> dict[str, str]:
        return self.client.hgetall(self.run_meta_key(run_id))

    def cache_get(self, key: str) -> dict[str, Any] | None:
        value = self.client.get(f"cache:{key}")
        return json.loads(value) if value else None

    def cache_set(self, key: str, value: dict[str, Any], ttl_seconds: int = 3600) -> None:
        self.client.setex(f"cache:{key}", ttl_seconds, json.dumps(value))

    @staticmethod
    def run_meta_key(run_id: str) -> str:
        return f"run:{run_id}:meta"

    @staticmethod
    def run_events_key(run_id: str) -> str:
        return f"run:{run_id}:events"

    @staticmethod
    def agent_state_key(run_id: str, agent: str) -> str:
        return f"agent:{run_id}:{agent}:state"


@dataclass
class NullDataLayer:
    status: str = "off"

    def create_run(self, goal: str) -> str:
        return str(uuid.uuid4())

    def save_agent_output(self, run_id: str, agent: str, output: dict[str, Any]) -> str:
        return ""

    def append_event(self, run_id: str, agent: str, event: dict[str, Any]) -> str:
        return ""

    def finish_run(self, run_id: str, status: str, judgment: dict[str, Any]) -> None:
        return None

    def get_agent_output(self, run_id: str, agent: str) -> dict[str, Any] | None:
        return None

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        return []

    def get_run_meta(self, run_id: str) -> dict[str, str]:
        return {}


def create_data_layer(mode: str = "auto", redis_url: str | None = None) -> DataLayer:
    url = redis_url or os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    timeout_seconds = float(os.environ.get("REDIS_TIMEOUT_SECONDS", DEFAULT_REDIS_TIMEOUT_SECONDS))

    if mode == "off":
        return NullDataLayer()

    if mode in {"auto", "real"}:
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            health_check_interval=30,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        try:
            client.ping()
            return RedisDataLayer(client=client, status="redis:connected")
        except redis.RedisError as exc:
            if mode == "real":
                raise RuntimeError("Could not connect to Redis") from exc

    if mode in {"auto", "fake"}:
        import fakeredis

        return RedisDataLayer(client=fakeredis.FakeRedis(decode_responses=True), status="fakeredis")

    raise ValueError(f"Unsupported Redis data layer mode: {mode}")
