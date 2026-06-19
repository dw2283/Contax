from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from env_config import load_project_env

load_project_env()

import agent_monitor
from data_layer import create_data_layer
from demo_multi_agent_weave import AGENT_ORDER, run_multi_agent
from npc_harness import initial_world_state, run_npc_harness_step
from prm_pipeline import PRMRedisStore, demo_screenshots, duplicate_candidates_for, prepare_person_record, run_ingest, run_match, seed_demo_people


PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_SCREENSHOT_DIR = PROJECT_ROOT / "anonymized_screenshots"
LOCAL_SCREENSHOT_REF_PREFIX = "anonymized_screenshots"

LOCAL_SCREENSHOT_TEXT: dict[str, str] = {
    "01_whatsapp_business_fake.png": "\n".join(
        [
            "Name: Sophia Laurent",
            "Company: Horizon Bay Properties",
            "Role: Operations Director",
            "Location: Dubai, UAE",
            "Interests: real estate, smart technology, UAE property services",
            "How_we_met: WhatsApp Business profile for Horizon Bay Properties",
        ]
    ),
    "02_whatsapp_business_fake.png": "\n".join(
        [
            "Name: Atlas Auto",
            "Company: Atlas Auto",
            "Role: Automotive Service Marketplace",
            "Location: Dubai, UAE",
            "Interests: automotive service, online marketplace, customer experience",
            "How_we_met: WhatsApp Business profile for Atlas Auto",
        ]
    ),
    "03_wechat_profile_fake.png": "\n".join(
        [
            "Name: 李晨",
            "Company: University research lab",
            "Role: Researcher",
            "Location: Unknown",
            "Interests: AI UX, evals, startups",
            "How_we_met: WeChat profile from Tech summit; note mentions startup project",
        ]
    ),
    "04_linkedin_profile_fake.png": "\n".join(
        [
            "Name: Jordan Blake",
            "Company: Northstar Labs",
            "Role: Product Risk Program Manager",
            "Location: San Francisco Bay Area",
            "Interests: security, enterprise AI, product strategy, collaboration",
            "How_we_met: LinkedIn new connection via Taylor and Morgan",
        ]
    ),
    "05_linkedin_profile_fake.png": "\n".join(
        [
            "Name: Priya Nair",
            "Company: Cloudworks",
            "Role: Senior Software Engineer",
            "Location: San Diego, California, United States",
            "Interests: distributed systems, cloud infra, MLOps",
            "How_we_met: LinkedIn new connection via Maya",
        ]
    ),
    "06_wechat_profile_fake.png": "\n".join(
        [
            "Name: 王明",
            "Company: Medical AI project",
            "Role: Medical AI Researcher",
            "Location: Unknown",
            "Interests: enterprise AI, evals, privacy",
            "How_we_met: WeChat profile from Tech summit; note mentions medical AI project",
        ]
    ),
    "07_linkedin_profile_fake.png": "\n".join(
        [
            "Name: Emily Chen",
            "Company: Nova Electronics",
            "Role: General Manager",
            "Location: United States",
            "Interests: robotics, supply chain, growth, product strategy",
            "How_we_met: LinkedIn new connection",
        ]
    ),
    "08_chat_fake.png": "\n".join(
        [
            "Name: alexyu",
            "Company: University lab",
            "Role: AI Researcher",
            "Location: Unknown",
            "Interests: LLM infrastructure, evals, AI UX",
            "How_we_met: Chat follow-up after Tech Summit",
        ]
    ),
}

app = FastAPI(title="WeaveHacks Multi-Agent API")
RUN_CACHE: dict[str, dict[str, Any]] = {}
REDIS_ENDPOINT_RE = re.compile(r"redis:redis://\S+|redis://\S+", flags=re.IGNORECASE)

if LOCAL_SCREENSHOT_DIR.exists():
    app.mount(
        "/assets/screenshots",
        StaticFiles(directory=str(LOCAL_SCREENSHOT_DIR)),
        name="real_screenshots",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    goal: str = Field(..., min_length=3)
    weave_mode: str | None = None
    redis_mode: str | None = None


class NPCStepRequest(BaseModel):
    world: dict[str, Any]
    target_npc: str = Field(..., min_length=2)
    player_message: str = Field(..., min_length=3)
    mode: str = "multi_agent"
    weave_mode: str | None = None
    redis_mode: str | None = None


class IngestRequest(BaseModel):
    screenshots: list[dict[str, Any]] | None = None
    demo: bool = False
    demo_size: int | None = Field(default=None, ge=1, le=500)
    weave_mode: str | None = None
    redis_mode: str | None = None


class LocalIngestRequest(BaseModel):
    paths: list[str] | None = None
    weave_mode: str | None = None
    redis_mode: str | None = None


class SeedRequest(BaseModel):
    size: int = Field(default=100, ge=1, le=500)
    redis_mode: str | None = None


class MatchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    ensure_demo_data: bool = True
    weave_mode: str | None = None
    redis_mode: str | None = None


class DeleteDemoRequest(BaseModel):
    confirm: bool = False
    redis_mode: str | None = None


class DuplicatePreviewRequest(BaseModel):
    people: list[dict[str, Any]] = Field(default_factory=list)
    redis_mode: str | None = None


def _redact_redis_endpoint(value: str) -> str:
    return REDIS_ENDPOINT_RE.sub("redis:connected", value)


def _public_redis_status(value: str) -> str:
    lowered = value.lower()
    if "error" in lowered:
        return "error"
    if "fake" in lowered:
        return "fakeredis"
    if "off" in lowered:
        return "off"
    if "redis" in lowered:
        return "redis:connected"
    return _redact_redis_endpoint(value)


def _redact_monitor_payload(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_redis_endpoint(value)
    if isinstance(value, list):
        return [_redact_monitor_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_monitor_payload(item) for key, item in value.items()}
    return value


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "weave_project": os.environ.get("WEAVE_PROJECT", "weavehacks-multi-agent-demo"),
        "weave_mode": os.environ.get("WEAVE_MODE", "auto"),
        "redis_mode": os.environ.get("REDIS_MODE", "auto"),
    }


@app.get("/api/status")
def status(redis_mode: str | None = None) -> dict[str, Any]:
    """Live state for the Agent Monitor: Redis memory + latest per-agent run spans."""
    snap = _redact_monitor_payload(agent_monitor.snapshot())
    try:
        store = PRMRedisStore(redis_mode or os.environ.get("REDIS_MODE", "auto"))
        people = store.list_people(limit=500)
        redis_state = {
            "status": _public_redis_status(store.status),
            "person_count": len(people),
            "vector_index_ready": store.ensure_index(),
        }
    except Exception as exc:  # noqa: BLE001 - surface as state, don't 500 the poll
        redis_state = {"status": _redact_redis_endpoint(f"error: {exc}"), "person_count": 0, "vector_index_ready": False}

    return {
        "weave_project": os.environ.get("WEAVE_PROJECT", "weavehacks-multi-agent-demo"),
        "redis": redis_state,
        "embed": snap["embed"],
        "runs": snap["runs"],
    }


def _screenshots_from_request(request: IngestRequest) -> list[dict[str, Any]]:
    if request.demo or not request.screenshots:
        return demo_screenshots()
    return [_enrich_screenshot_input(screenshot) for screenshot in request.screenshots]


def _source_from_filename(filename: str) -> str:
    lower = filename.lower()
    if "linkedin" in lower:
        return "linkedin"
    if "whatsapp" in lower:
        return "whatsapp"
    return "wechat"


def _screenshot_filename(raw_ref: str) -> str:
    return Path(raw_ref).name


def _fallback_screenshot_text(raw_ref: str, source: str) -> str:
    label = Path(raw_ref).stem.replace("_", " ").replace("-", " ").strip()
    name = label.title() if label else f"{source.title()} contact"
    return "\n".join(
        [
            f"Name: {name}",
            "Company: Unknown",
            "Role: Contact from uploaded screenshot",
            "Location: Unknown",
            "Interests: uploaded screenshot",
            f"How_we_met: Uploaded {source} screenshot",
        ]
    )


def _enrich_screenshot_input(screenshot: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(screenshot)
    raw_ref = str(enriched.get("raw_screenshot_ref") or "")
    filename = _screenshot_filename(raw_ref)
    source = str(enriched.get("source") or _source_from_filename(filename or raw_ref))
    enriched["source"] = source
    if not enriched.get("text"):
        enriched["text"] = LOCAL_SCREENSHOT_TEXT.get(filename, _fallback_screenshot_text(raw_ref or filename, source))
    return enriched


def _screenshot_summaries(screenshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": screenshot.get("source"),
            "raw_screenshot_ref": screenshot.get("raw_screenshot_ref"),
        }
        for screenshot in screenshots
    ]


def _resolve_local_screenshot_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    candidate = candidate.resolve()

    try:
        candidate.relative_to(LOCAL_SCREENSHOT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Local screenshot path must be inside {LOCAL_SCREENSHOT_REF_PREFIX}/: {raw_path}",
        ) from exc

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"Local screenshot not found: {raw_path}")
    if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail=f"Unsupported screenshot file type: {candidate.name}")
    return candidate


def _local_screenshot_paths(request: LocalIngestRequest) -> list[Path]:
    if request.paths:
        return [_resolve_local_screenshot_path(path) for path in request.paths]

    if not LOCAL_SCREENSHOT_DIR.exists():
        raise HTTPException(status_code=404, detail=f"Missing {LOCAL_SCREENSHOT_REF_PREFIX}/ directory")

    paths = sorted(
        path
        for path in LOCAL_SCREENSHOT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if not paths:
        raise HTTPException(status_code=404, detail=f"No screenshots found in {LOCAL_SCREENSHOT_REF_PREFIX}/")
    return paths


def _local_screenshots_from_request(request: LocalIngestRequest) -> list[dict[str, Any]]:
    screenshots: list[dict[str, Any]] = []
    for path in _local_screenshot_paths(request):
        image_base64 = base64.b64encode(path.read_bytes()).decode("ascii")
        ref = f"{LOCAL_SCREENSHOT_REF_PREFIX}/{path.name}"
        screenshots.append(
            {
                "source": _source_from_filename(path.name),
                "raw_screenshot_ref": ref,
                "text": LOCAL_SCREENSHOT_TEXT.get(path.name, _fallback_screenshot_text(ref, _source_from_filename(path.name))),
                "image_base64": f"data:image/{path.suffix.lower().lstrip('.')};base64,{image_base64}",
            }
        )
    return screenshots


def _run_ingest_request(request: IngestRequest) -> dict[str, Any]:
    try:
        if request.demo_size is not None:
            redis_mode = request.redis_mode or os.environ.get("REDIS_MODE", "auto")
            seeded = seed_demo_people(size=request.demo_size, redis_mode=redis_mode)
            return {"screenshots": [], "weave_mode": "seed", "weave_call_url": None, "result": seeded}

        screenshots = _screenshots_from_request(request)
        screenshot_summaries = _screenshot_summaries(screenshots)
        payload = run_ingest(
            screenshots=screenshots,  # type: ignore[arg-type]
            weave_mode=request.weave_mode,
            redis_mode=request.redis_mode,
        )
        if isinstance(payload.get("result"), dict):
            redis_mode = request.redis_mode or os.environ.get("REDIS_MODE", "auto")
            payload["result"]["people"] = PRMRedisStore(redis_mode).list_people()
            payload["result"]["screenshots"] = screenshot_summaries
        return {"screenshots": screenshot_summaries, **payload}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_match_request(request: MatchRequest) -> dict[str, Any]:
    try:
        redis_mode = request.redis_mode or os.environ.get("REDIS_MODE", "auto")
        if request.ensure_demo_data and not PRMRedisStore(redis_mode).list_people():
            seed_demo_people(size=100, redis_mode=redis_mode)
        return run_match(
            query=request.query,
            weave_mode=request.weave_mode,
            redis_mode=redis_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_seed_request(request: SeedRequest) -> dict[str, Any]:
    try:
        redis_mode = request.redis_mode or os.environ.get("REDIS_MODE", "auto")
        return seed_demo_people(size=request.size, redis_mode=redis_mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/prm/demo-screenshots")
def get_prm_demo_screenshots() -> dict[str, Any]:
    return {"screenshots": demo_screenshots()}


@app.get("/api/prm/people")
def get_prm_people(redis_mode: str | None = None) -> dict[str, Any]:
    try:
        store = PRMRedisStore(redis_mode or os.environ.get("REDIS_MODE", "auto"))
        return {"redis_status": store.status, "people": store.list_people()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/prm/export")
def export_prm_people(redis_mode: str | None = None) -> dict[str, Any]:
    try:
        store = PRMRedisStore(redis_mode or os.environ.get("REDIS_MODE", "auto"))
        return store.export_people()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/prm/duplicates")
def get_prm_duplicate_reviews(redis_mode: str | None = None) -> dict[str, Any]:
    try:
        store = PRMRedisStore(redis_mode or os.environ.get("REDIS_MODE", "auto"))
        reviews = store.list_duplicate_reviews()
        return {"redis_status": store.status, "count": len(reviews), "reviews": reviews}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/prm/dedupe/preview")
def preview_prm_duplicates(request: DuplicatePreviewRequest) -> dict[str, Any]:
    try:
        store = PRMRedisStore(request.redis_mode or os.environ.get("REDIS_MODE", "auto"))
        existing_people = store.list_people()
        previews = []
        for raw_person in request.people:
            person = prepare_person_record(dict(raw_person))  # type: ignore[arg-type]
            candidates = duplicate_candidates_for(person, existing_people)
            previews.append(
                {
                    "person": person,
                    "action": "review" if candidates else "create",
                    "candidates": candidates[:3],
                }
            )
        return {"redis_status": store.status, "previews": previews}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/prm/delete-demo")
def delete_prm_demo_people(request: DeleteDemoRequest) -> dict[str, Any]:
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to delete demo contacts.")
    try:
        store = PRMRedisStore(request.redis_mode or os.environ.get("REDIS_MODE", "auto"))
        return store.delete_demo_people()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/ingest")
def ingest(request: IngestRequest) -> dict[str, Any]:
    return _run_ingest_request(request)


@app.post("/api/seed")
def seed(request: SeedRequest) -> dict[str, Any]:
    return _run_seed_request(request)


@app.post("/match")
def match(request: MatchRequest) -> dict[str, Any]:
    return _run_match_request(request)


@app.post("/api/prm/ingest")
def api_prm_ingest(request: IngestRequest) -> dict[str, Any]:
    return _run_ingest_request(request)


@app.post("/api/ingest-local")
def ingest_local(request: LocalIngestRequest | None = None) -> dict[str, Any]:
    active_request = request or LocalIngestRequest()
    screenshots = _local_screenshots_from_request(active_request)
    screenshot_summaries = _screenshot_summaries(screenshots)
    payload = _run_ingest_request(
        IngestRequest(
            screenshots=screenshots,
            demo=False,
            weave_mode=active_request.weave_mode,
            redis_mode=active_request.redis_mode,
        )
    )

    redis_mode = active_request.redis_mode or os.environ.get("REDIS_MODE", "auto")
    payload["result"]["people"] = PRMRedisStore(redis_mode).list_people()
    payload["result"]["screenshots"] = screenshot_summaries
    payload["local_screenshot_count"] = len(screenshots)
    payload["screenshots"] = screenshot_summaries
    return payload


@app.post("/api/prm/ingest-local")
def api_prm_ingest_local(request: LocalIngestRequest | None = None) -> dict[str, Any]:
    return ingest_local(request)


@app.post("/api/prm/seed")
def api_prm_seed(request: SeedRequest) -> dict[str, Any]:
    return _run_seed_request(request)


@app.post("/api/prm/match")
def api_prm_match(request: MatchRequest) -> dict[str, Any]:
    return _run_match_request(request)


@app.get("/api/npc/session")
def create_npc_session() -> dict[str, Any]:
    return {
        "world": initial_world_state(),
        "modes": ["classic", "multi_agent"],
    }


@app.post("/api/npc/step")
def create_npc_step(request: NPCStepRequest) -> dict[str, Any]:
    if request.mode not in {"classic", "multi_agent"}:
        raise HTTPException(status_code=400, detail="mode must be classic or multi_agent")

    if request.target_npc not in request.world.get("npcs", {}):
        raise HTTPException(status_code=400, detail=f"Unknown NPC: {request.target_npc}")

    try:
        return run_npc_harness_step(
            world=request.world,
            target_npc=request.target_npc,
            player_message=request.player_message,
            mode=request.mode,
            weave_mode=request.weave_mode,
            redis_mode=request.redis_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/runs")
def create_run(request: RunRequest) -> dict[str, Any]:
    try:
        run = run_multi_agent(
            goal=request.goal,
            weave_mode=request.weave_mode,
            redis_mode=request.redis_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    RUN_CACHE[run["run_id"]] = run
    return run


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    if run_id in RUN_CACHE:
        return RUN_CACHE[run_id]

    try:
        layer = create_data_layer(os.environ.get("REDIS_MODE", "auto"))
        meta = layer.get_run_meta(run_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not meta:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    return {
        "run_id": run_id,
        "data_layer_status": layer.status,
        "redis": {
            "meta": meta,
            "events": layer.get_events(run_id),
            "agent_outputs": {
                agent: layer.get_agent_output(run_id, agent)
                for agent in AGENT_ORDER
            },
        },
    }
