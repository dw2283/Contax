"""In-process observability recorder for the multi-agent pipeline.

Captures one span per agent step (start / end / status / summary) for the most
recent ingest and match runs, plus cumulative embedding stats. The `/api/status`
endpoint reads `snapshot()` so the Monitor UI can draw a Gantt timeline and a
live memory panel. Pure stdlib, thread-safe, no external deps.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

_LOCK = threading.RLock()
_CURRENT: dict[str, Any] | None = None
_LATEST: dict[str, dict[str, Any]] = {}
_EMBED: dict[str, float] = {"count": 0, "total_ms": 0.0}


def start_run(kind: str, meta: dict[str, Any] | None = None) -> None:
    """Begin recording a run. `kind` is "ingest" or "match"."""
    global _CURRENT
    with _LOCK:
        _CURRENT = {
            "kind": kind,
            "started_at": time.time(),
            "finished_at": None,
            "spans": [],
            "meta": meta or {},
        }


def _add_span(span: dict[str, Any]) -> None:
    with _LOCK:
        if _CURRENT is not None:
            _CURRENT["spans"].append(span)


@contextmanager
def track(agent: str, group: str | None = None) -> Iterator[dict[str, Any]]:
    """Time an agent step. Mutate the yielded dict's `summary` to annotate it."""
    info: dict[str, Any] = {"summary": ""}
    start = time.time()
    status = "ok"
    try:
        yield info
    except Exception as exc:  # noqa: BLE001 - record then re-raise
        status = "error"
        if not info.get("summary"):
            info["summary"] = str(exc)[:160]
        raise
    finally:
        end = time.time()
        _add_span(
            {
                "agent": agent,
                "group": group,
                "start": start,
                "end": end,
                "duration_ms": round((end - start) * 1000, 2),
                "status": status,
                "summary": str(info.get("summary", ""))[:200],
            }
        )


def note_embed(ms: float) -> None:
    with _LOCK:
        _EMBED["count"] = int(_EMBED["count"]) + 1
        _EMBED["total_ms"] = round(float(_EMBED["total_ms"]) + ms, 2)


def finish_run(extra: dict[str, Any] | None = None) -> None:
    global _CURRENT
    with _LOCK:
        if _CURRENT is None:
            return
        _CURRENT["finished_at"] = time.time()
        if extra:
            _CURRENT.update(extra)
        _LATEST[_CURRENT["kind"]] = _CURRENT
        _CURRENT = None


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            "runs": {kind: dict(run) for kind, run in _LATEST.items()},
            "embed": dict(_EMBED),
        }
