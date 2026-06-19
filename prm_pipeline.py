from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from operator import add
from typing import Annotated, Any, Literal, TypedDict

import numpy as np
import redis
import weave
from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph

import agent_monitor as mon
from data_layer import create_data_layer
from demo_multi_agent_weave import DEFAULT_PROJECT, init_weave
from env_config import load_project_env


load_project_env()

EMBED_DIM = 64
PERSON_INDEX = "idx:prm:persons"
VISION_MODEL_ENV = "PRM_VISION_MODEL"
VISION_MODE_ENV = "PRM_VISION_MODE"
DEFAULT_VISION_MODEL = "gpt-4o-mini"
VISION_PROMPT = """You are the vision extraction agent for Contax, a personal relationship graph.

Extract exactly one contact from the provided social/profile screenshot.
Return only JSON matching the provided schema. Do not include markdown, notes, or extra keys.

Rules:
- Use only information visible in the screenshot. Do not invent missing fields.
- If a field is missing or unclear, return an empty string. If interests are missing, return [].
- Preserve the contact's displayed language and spelling, including Chinese names.
- Prefer a human contact's name. If the screenshot is clearly a business account, use the business name as both name and company when appropriate.
- Keep interests as 0-6 short noun phrases inferred from visible role, bio, posts, messages, skills, or topics.
- source must be one of: wechat, linkedin, whatsapp. Use the source hint unless the screenshot clearly shows another supported source.
- how_we_met should be a concise provenance phrase such as "LinkedIn profile screenshot", "WeChat profile screenshot", or a visible shared group/connection if shown.
"""
VISION_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "contax_contact_profile",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "company": {"type": "string"},
                "role": {"type": "string"},
                "location": {"type": "string"},
                "interests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 6,
                },
                "how_we_met": {"type": "string"},
                "source": {"type": "string", "enum": ["wechat", "linkedin", "whatsapp"]},
            },
            "required": ["name", "company", "role", "location", "interests", "how_we_met", "source"],
        },
    },
}

Source = Literal["wechat", "linkedin", "whatsapp"]


class ScreenshotInput(TypedDict, total=False):
    source: Source
    raw_screenshot_ref: str
    text: str
    image_base64: str
    dataset: str
    is_demo: bool


class SourceProfile(TypedDict, total=False):
    id: str
    source: str
    raw_screenshot_ref: str
    name: str
    company: str
    role: str
    location: str
    interests: list[str]
    how_we_met: str
    imported_at: float
    confidence: float


class Person(TypedDict, total=False):
    id: str
    name: str
    company: str
    role: str
    location: str
    interests: list[str]
    how_we_met: str
    source: str
    embedding: list[float]
    raw_screenshot_ref: str
    dataset: str
    is_demo: bool
    imported_at: float
    updated_at: float
    source_profiles: list[SourceProfile]
    duplicate_status: str
    duplicate_candidates: list[dict[str, Any]]
    merge_log: list[dict[str, Any]]


class IngestState(TypedDict, total=False):
    screenshots: list[ScreenshotInput]
    extracted: Annotated[list[Person], add]
    people: list[Person]
    storage: dict[str, Any]
    redis_mode: str


PRM_MEMORY_PEOPLE: dict[str, Person] = {}
PRM_DUPLICATE_REVIEWS: dict[str, dict[str, Any]] = {}

REAL_DATASET = "real"
DEMO_DATASET = "demo"
DUPLICATE_AUTO_MERGE_SCORE = 0.92
DUPLICATE_REVIEW_SCORE = 0.70

DEMO_SOURCES: list[Source] = ["wechat", "linkedin", "whatsapp"]
DEMO_SCREENSHOT_REFS = {
    "li_anna_gpu.png",
    "wechat_ben_founder.png",
    "wa_carla_design.png",
    "li_david_ml.png",
    "wechat_emma_vc.png",
    "wa_frank_ops.png",
}

DEMO_FIRST_NAMES = [
    "Anna",
    "Ben",
    "Carla",
    "David",
    "Emma",
    "Frank",
    "Grace",
    "Hannah",
    "Ivan",
    "Julia",
    "Kai",
    "Leah",
    "Maya",
    "Noah",
    "Olivia",
    "Priya",
    "Quinn",
    "Ravi",
    "Sophia",
    "Theo",
    "Uma",
    "Victor",
    "Wendy",
    "Xavier",
    "Yara",
]

DEMO_LAST_NAMES = [
    "Chen",
    "Liu",
    "Gomez",
    "Park",
    "Wang",
    "Patel",
    "Kim",
    "Nguyen",
    "Smith",
    "Tan",
    "Singh",
    "Brown",
    "Garcia",
    "Zhang",
    "Wilson",
    "Khan",
    "Miller",
    "Lee",
    "Davis",
    "Martinez",
    "Johnson",
    "Lopez",
    "Clark",
    "Young",
    "Nakamura",
]

DEMO_COMPANY_PROFILES: list[dict[str, Any]] = [
    {
        "company": "OpenAI",
        "roles": ["Research Engineer", "Product Manager", "Developer Advocate"],
        "locations": ["SF", "NYC", "London"],
        "topics": ["agents", "evals", "LLM infrastructure", "developer tools"],
    },
    {
        "company": "Anthropic",
        "roles": ["Researcher", "ML Engineer", "Policy Lead"],
        "locations": ["SF", "London", "Toronto"],
        "topics": ["agents", "evals", "enterprise AI", "privacy"],
    },
    {
        "company": "NVIDIA",
        "roles": ["GPU Kernel Engineer", "Solutions Architect", "Robotics Engineer"],
        "locations": ["SF", "Seattle", "Singapore"],
        "topics": ["CUDA", "GPU kernels", "cloud infra", "robotics"],
    },
    {
        "company": "Databricks",
        "roles": ["Data Engineer", "ML Engineer", "Product Manager"],
        "locations": ["SF", "NYC", "Toronto"],
        "topics": ["data pipelines", "MLOps", "distributed systems", "cloud infra"],
    },
    {
        "company": "Snowflake",
        "roles": ["Backend Engineer", "Data Scientist", "Solutions Architect"],
        "locations": ["SF", "London", "Toronto"],
        "topics": ["databases", "data pipelines", "enterprise AI", "security"],
    },
    {
        "company": "Figma",
        "roles": ["Product Designer", "Design Engineer", "Product Manager"],
        "locations": ["NYC", "London", "SF"],
        "topics": ["design systems", "AI UX", "product strategy", "developer tools"],
    },
    {
        "company": "Stripe",
        "roles": ["Product Manager", "Backend Engineer", "Growth Lead"],
        "locations": ["SF", "NYC", "London"],
        "topics": ["payments", "fintech", "developer tools", "security"],
    },
    {
        "company": "Vercel",
        "roles": ["Frontend Engineer", "Developer Advocate", "Founder"],
        "locations": ["NYC", "SF", "London"],
        "topics": ["developer tools", "open source", "cloud infra", "AI UX"],
    },
    {
        "company": "Notion",
        "roles": ["Product Manager", "Designer", "Growth Lead"],
        "locations": ["SF", "NYC", "Singapore"],
        "topics": ["graph databases", "AI UX", "product strategy", "developer tools"],
    },
    {
        "company": "Airtable",
        "roles": ["Product Manager", "Data Engineer", "Designer"],
        "locations": ["SF", "NYC", "Toronto"],
        "topics": ["data pipelines", "MLOps", "product strategy", "developer tools"],
    },
    {
        "company": "Supabase",
        "roles": ["Founder", "Backend Engineer", "Developer Advocate"],
        "locations": ["London", "SF", "Singapore"],
        "topics": ["databases", "open source", "developer tools", "startups"],
    },
    {
        "company": "Neo4j",
        "roles": ["Graph Engineer", "Solutions Architect", "Researcher"],
        "locations": ["London", "NYC", "Toronto"],
        "topics": ["graph databases", "vector search", "retrieval", "databases"],
    },
    {
        "company": "Redis",
        "roles": ["Solutions Architect", "Backend Engineer", "Developer Advocate"],
        "locations": ["SF", "London", "Beijing"],
        "topics": ["Redis", "vector search", "databases", "cloud infra"],
    },
    {
        "company": "Hugging Face",
        "roles": ["ML Engineer", "Researcher", "Developer Advocate"],
        "locations": ["NYC", "Paris", "London"],
        "topics": ["open source", "MLOps", "retrieval", "LLM infrastructure"],
    },
    {
        "company": "DeepMind",
        "roles": ["Researcher", "Robotics Engineer", "ML Engineer"],
        "locations": ["London", "Toronto", "NYC"],
        "topics": ["evals", "robotics", "privacy", "agents"],
    },
    {
        "company": "Tencent",
        "roles": ["Product Manager", "Backend Engineer", "Investor"],
        "locations": ["Beijing", "Singapore", "Toronto"],
        "topics": ["marketplaces", "payments", "cloud infra", "growth"],
    },
    {
        "company": "ByteDance",
        "roles": ["ML Engineer", "Product Manager", "Growth Lead"],
        "locations": ["Beijing", "Singapore", "London"],
        "topics": ["retrieval", "growth", "AI UX", "data pipelines"],
    },
    {
        "company": "Grab",
        "roles": ["Product Manager", "Data Scientist", "Operations Lead"],
        "locations": ["Singapore", "Beijing", "Toronto"],
        "topics": ["marketplaces", "supply chain", "payments", "growth"],
    },
    {
        "company": "Shopify",
        "roles": ["Founder", "Backend Engineer", "Product Designer"],
        "locations": ["Toronto", "NYC", "London"],
        "topics": ["payments", "marketplaces", "developer tools", "startups"],
    },
    {
        "company": "Sequoia",
        "roles": ["Investor", "Founder", "Scout"],
        "locations": ["SF", "NYC", "Singapore"],
        "topics": ["fundraising", "startups", "enterprise AI", "marketplaces"],
    },
]

DEMO_EXTRA_TOPICS = [
    "agents",
    "evals",
    "LLM infrastructure",
    "CUDA",
    "GPU kernels",
    "distributed systems",
    "databases",
    "vector search",
    "Redis",
    "graph databases",
    "design systems",
    "AI UX",
    "product strategy",
    "fintech",
    "payments",
    "developer tools",
    "startups",
    "fundraising",
    "enterprise AI",
    "data pipelines",
    "MLOps",
    "retrieval",
    "security",
    "privacy",
    "robotics",
    "supply chain",
    "marketplaces",
    "growth",
    "open source",
    "cloud infra",
]

DEMO_SOURCE_CHANNELS: dict[Source, list[str]] = {
    "wechat": [
        "WeChat founder circle",
        "WeChat AI builders group",
        "WeChat hackathon alumni",
        "WeChat product leaders chat",
    ],
    "linkedin": [
        "LinkedIn AI infra thread",
        "LinkedIn product network",
        "LinkedIn founder update",
        "LinkedIn research discussion",
    ],
    "whatsapp": [
        "WhatsApp cloud builders",
        "WhatsApp design group",
        "WhatsApp investor intros",
        "WhatsApp operators circle",
    ],
}


def person_text(person: Person) -> str:
    return " ".join(
        [
            person.get("name", ""),
            person.get("company", ""),
            person.get("role", ""),
            person.get("location", ""),
            " ".join(person.get("interests", [])),
            person.get("how_we_met", ""),
            person.get("source", ""),
        ]
    ).strip()


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    numerator = sum(x * y for x, y in zip(a, b))
    left = math.sqrt(sum(x * x for x in a))
    right = math.sqrt(sum(y * y for y in b))
    if left == 0 or right == 0:
        return 0.0
    return numerator / (left * right)


@weave.op()
def deterministic_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    vector = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"[a-zA-Z0-9+#.\-]+", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 else -1.0
        vector[index] += sign
    norm = np.linalg.norm(vector)
    if norm:
        vector = vector / norm
    return vector.astype(float).tolist()


@weave.op()
def embed_text(text: str) -> list[float]:
    # Keep demo deterministic. Swap this op to OpenAI embeddings when OPENAI_API_KEY is present.
    started = time.perf_counter()
    vector = deterministic_embedding(text)
    mon.note_embed((time.perf_counter() - started) * 1000)
    return vector


def infer_source(value: str) -> Source:
    lower = value.lower()
    if "linkedin" in lower:
        return "linkedin"
    if "whatsapp" in lower:
        return "whatsapp"
    return "wechat"


def field(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def split_interests(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,;/|]", value) if item.strip()]


def _clean_string(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _clean_interests(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = split_interests(value)
    elif isinstance(value, list):
        raw_items = [_clean_string(item) for item in value]
    else:
        raw_items = []

    interests: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        cleaned = _clean_string(item)
        key = cleaned.lower()
        if cleaned and key not in seen:
            interests.append(cleaned)
            seen.add(key)
        if len(interests) >= 6:
            break
    return interests


def _clean_source(value: Any, default: Source) -> Source:
    source = str(value or "").lower()
    if source in {"wechat", "linkedin", "whatsapp"}:
        return source  # type: ignore[return-value]
    return default


def _now() -> float:
    return time.time()


def _normal_lookup(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _normal_phone(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def is_demo_person(person: Person) -> bool:
    raw_ref = str(person.get("raw_screenshot_ref") or "")
    return bool(person.get("is_demo")) or person.get("dataset") == DEMO_DATASET or raw_ref.startswith("demo_people/") or raw_ref in DEMO_SCREENSHOT_REFS


def person_dataset(person: Person) -> str:
    dataset = _clean_string(person.get("dataset"))
    if dataset:
        return dataset
    return DEMO_DATASET if is_demo_person(person) else REAL_DATASET


def _source_profile_from_person(person: Person, imported_at: float) -> SourceProfile:
    raw_ref = str(person.get("raw_screenshot_ref") or "")
    source = str(person.get("source") or "")
    profile_id = hashlib.sha1(
        json.dumps(
            {
                "source": source,
                "raw_screenshot_ref": raw_ref,
                "name": person.get("name", ""),
                "company": person.get("company", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "id": profile_id,
        "source": source,
        "raw_screenshot_ref": raw_ref,
        "name": str(person.get("name") or ""),
        "company": str(person.get("company") or ""),
        "role": str(person.get("role") or ""),
        "location": str(person.get("location") or ""),
        "interests": list(person.get("interests") or []),
        "how_we_met": str(person.get("how_we_met") or ""),
        "imported_at": imported_at,
        "confidence": 1.0,
    }


def _merge_source_profiles(left: list[SourceProfile], right: list[SourceProfile]) -> list[SourceProfile]:
    merged: list[SourceProfile] = []
    seen: set[str] = set()
    for profile in left + right:
        profile_id = str(profile.get("id") or "")
        if not profile_id:
            profile_id = hashlib.sha1(json.dumps(profile, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
            profile["id"] = profile_id
        if profile_id in seen:
            continue
        merged.append(profile)
        seen.add(profile_id)
    return merged


def prepare_person_record(person: Person, dataset: str | None = None, is_demo: bool | None = None) -> Person:
    timestamp = float(person.get("imported_at") or _now())
    inferred_demo = is_demo_person(person) if is_demo is None else is_demo
    active_dataset = dataset or str(person.get("dataset") or (DEMO_DATASET if inferred_demo else REAL_DATASET))
    person["dataset"] = active_dataset
    person["is_demo"] = bool(inferred_demo or active_dataset == DEMO_DATASET)
    person["imported_at"] = timestamp
    person["updated_at"] = float(person.get("updated_at") or timestamp)

    profiles = person.get("source_profiles")
    if not isinstance(profiles, list) or not profiles:
        person["source_profiles"] = [_source_profile_from_person(person, timestamp)]
    return person


def _identity_values(person: Person) -> set[str]:
    values: set[str] = set()
    for key in ["email", "linkedin_url", "profile_url", "wechat_id", "whatsapp_id", "external_id"]:
        normalized = _normal_lookup(person.get(key))
        if normalized:
            values.add(f"{key}:{normalized}")
    phone = _normal_phone(person.get("phone") or person.get("whatsapp_phone"))
    if len(phone) >= 7:
        values.add(f"phone:{phone}")
    return values


def _interest_overlap(left: Person, right: Person) -> float:
    left_items = {_normal_lookup(item) for item in left.get("interests", []) if _normal_lookup(item)}
    right_items = {_normal_lookup(item) for item in right.get("interests", []) if _normal_lookup(item)}
    if not left_items or not right_items:
        return 0.0
    return len(left_items & right_items) / len(left_items | right_items)


def duplicate_score(existing: Person, candidate: Person) -> dict[str, Any]:
    """Score whether two Person records likely represent the same real contact."""
    if existing.get("id") == candidate.get("id"):
        return {"score": 1.0, "reasons": ["same contact id"], "conflicts": []}

    reasons: list[str] = []
    conflicts: list[str] = []
    score = 0.0

    if is_demo_person(existing) != is_demo_person(candidate):
        conflicts.append("demo and real records are kept separate")
        return {"score": 0.0, "reasons": [], "conflicts": conflicts}

    existing_identities = _identity_values(existing)
    candidate_identities = _identity_values(candidate)
    shared_identities = existing_identities & candidate_identities
    if shared_identities:
        reasons.append("shared stable identity field")
        score = max(score, 0.97)

    same_raw_ref = bool(existing.get("raw_screenshot_ref")) and existing.get("raw_screenshot_ref") == candidate.get("raw_screenshot_ref")
    if same_raw_ref:
        reasons.append("same source screenshot")
        score = max(score, 0.95)

    same_name = bool(normalize_name(existing.get("name", ""))) and normalize_name(existing.get("name", "")) == normalize_name(candidate.get("name", ""))
    if same_name:
        reasons.append("same normalized name")
        score += 0.34

    matching_context: set[str] = set()
    for key, weight, label in [
        ("company", 0.22, "company"),
        ("role", 0.12, "role"),
        ("location", 0.08, "location"),
    ]:
        left = _normal_lookup(existing.get(key))
        right = _normal_lookup(candidate.get(key))
        if left and right and left == right:
            reasons.append(f"same {label}")
            matching_context.add(key)
            score += weight
        elif same_name and left and right and left != right and key in {"company", "location"}:
            conflicts.append(f"different {label}")
            score -= 0.10

    if same_name and {"company", "role", "location"}.issubset(matching_context):
        reasons.append("same name, company, role, and location")
        score += 0.18
    elif same_name and {"company", "role"}.issubset(matching_context):
        reasons.append("same name, company, and role")
        score += 0.12

    embedding_similarity = cosine(existing.get("embedding", []), candidate.get("embedding", []))
    if embedding_similarity >= 0.90:
        reasons.append("very similar profile embedding")
        score += 0.22
    elif embedding_similarity >= 0.78:
        reasons.append("similar profile embedding")
        score += 0.14

    overlap = _interest_overlap(existing, candidate)
    if overlap >= 0.5:
        reasons.append("overlapping interests")
        score += min(0.12, overlap * 0.12)

    if not same_name and not shared_identities and not same_raw_ref:
        score = min(score, 0.66)

    return {
        "score": round(max(0.0, min(0.99, score)), 4),
        "reasons": reasons,
        "conflicts": conflicts,
    }


def duplicate_review_id(candidate: Person, existing: Person) -> str:
    return hashlib.sha1(f"{candidate.get('id')}:{existing.get('id')}".encode("utf-8")).hexdigest()[:12]


def duplicate_candidates_for(candidate: Person, people: list[Person]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for existing in people:
        scored = duplicate_score(existing, candidate)
        if scored["score"] < DUPLICATE_REVIEW_SCORE:
            continue
        candidates.append(
            {
                "id": duplicate_review_id(candidate, existing),
                "candidate_id": candidate.get("id"),
                "existing_id": existing.get("id"),
                "candidate_name": candidate.get("name", ""),
                "existing_name": existing.get("name", ""),
                "score": scored["score"],
                "reasons": scored["reasons"],
                "conflicts": scored["conflicts"],
                "decision": "needs_review",
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def merge_people(existing: Person, incoming: Person, score: float | None = None, reasons: list[str] | None = None) -> Person:
    merged: Person = dict(existing)
    timestamp = _now()

    for key in ["name", "company", "role", "location", "how_we_met", "raw_screenshot_ref"]:
        old_value = _clean_string(merged.get(key))
        new_value = _clean_string(incoming.get(key))
        if not old_value or old_value.lower() in {"unknown", "n/a"}:
            merged[key] = new_value

    interests: list[str] = []
    seen_interests: set[str] = set()
    for item in list(existing.get("interests") or []) + list(incoming.get("interests") or []):
        cleaned = _clean_string(item)
        key = cleaned.lower()
        if cleaned and key not in seen_interests:
            interests.append(cleaned)
            seen_interests.add(key)
    merged["interests"] = interests[:12]

    sources = sorted({item.strip() for item in f"{existing.get('source', '')},{incoming.get('source', '')}".split(",") if item.strip()})
    merged["source"] = ",".join(sources)
    merged["dataset"] = DEMO_DATASET if is_demo_person(existing) and is_demo_person(incoming) else REAL_DATASET
    merged["is_demo"] = merged["dataset"] == DEMO_DATASET
    merged["updated_at"] = timestamp
    merged["source_profiles"] = _merge_source_profiles(
        list(existing.get("source_profiles") or [_source_profile_from_person(existing, float(existing.get("imported_at") or timestamp))]),
        list(incoming.get("source_profiles") or [_source_profile_from_person(incoming, float(incoming.get("imported_at") or timestamp))]),
    )
    merged["merge_log"] = list(existing.get("merge_log") or []) + [
        {
            "merged_person_id": incoming.get("id"),
            "merged_at": timestamp,
            "score": score,
            "reasons": reasons or [],
        }
    ]
    merged.pop("duplicate_status", None)
    merged.pop("duplicate_candidates", None)
    merged["embedding"] = embed_text(person_text(merged))
    return prepare_person_record(merged, dataset=merged["dataset"], is_demo=merged["is_demo"])


def _person_from_fields(fields: dict[str, Any], source: Source, raw_ref: str, id_seed: str) -> Person:
    clean_source = _clean_source(fields.get("source"), source)
    person: Person = {
        "id": hashlib.sha1(f"{clean_source}:{raw_ref}:{id_seed}".encode("utf-8")).hexdigest()[:12],
        "name": _clean_string(fields.get("name")),
        "company": _clean_string(fields.get("company")),
        "role": _clean_string(fields.get("role")),
        "location": _clean_string(fields.get("location")),
        "interests": _clean_interests(fields.get("interests")),
        "how_we_met": _clean_string(fields.get("how_we_met")),
        "source": clean_source,
        "embedding": [],
        "raw_screenshot_ref": raw_ref,
    }
    return prepare_person_record(person)


def _person_from_fixed_text(text: str, source: Source, raw_ref: str) -> Person:
    fields = {
        "name": field(r"(?:name|姓名)\s*[:：]\s*([^\n]+)", text),
        "company": field(r"(?:company|公司)\s*[:：]\s*([^\n]+)", text),
        "role": field(r"(?:role|title|职位)\s*[:：]\s*([^\n]+)", text),
        "location": field(r"(?:location|地点|city)\s*[:：]\s*([^\n]+)", text),
        "interests": split_interests(field(r"(?:interests|兴趣|topics)\s*[:：]\s*([^\n]+)", text)),
        "how_we_met": field(r"(?:how_we_met|met|认识渠道|channel)\s*[:：]\s*([^\n]+)", text),
        "source": source,
    }
    return _person_from_fields(fields, source, raw_ref, text)


def _apply_known_screenshot_fallback(person: Person, raw_ref: str) -> None:
    fallback_names = {
        "li_anna_gpu.png": ("Anna Chen", "NVIDIA", "GPU Kernel Engineer", "SF", ["CUDA", "GPU kernel", "systems"], "LinkedIn AI infra group"),
        "wechat_ben_founder.png": ("Ben Liu", "NeonDB", "Founder", "New York", ["databases", "Redis", "startups"], "WeChat founder circle"),
        "wa_carla_design.png": ("Carla Gomez", "Figma", "Product Designer", "Remote", ["design systems", "AI UX"], "WhatsApp design group"),
        "li_david_ml.png": ("David Park", "OpenAI", "Research Engineer", "SF", ["agents", "evals", "LLM infrastructure"], "LinkedIn LangGraph thread"),
        "wechat_emma_vc.png": ("Emma Wang", "Aster Capital", "Investor", "SF", ["AI infra", "developer tools"], "WeChat hackathon group"),
        "wa_frank_ops.png": ("Frank Patel", "AWS", "Solutions Architect", "Seattle", ["cloud", "vector search", "Redis"], "WhatsApp cloud builders"),
    }
    if person["name"]:
        return
    key = raw_ref.split("/")[-1]
    if key not in fallback_names:
        return
    name, company, role, location, interests, met = fallback_names[key]
    person.update(
        {
            "name": name,
            "company": company,
            "role": role,
            "location": location,
            "interests": interests,
            "how_we_met": met,
        }
    )


def _image_data_url(screenshot: ScreenshotInput) -> str:
    image_base64 = str(screenshot.get("image_base64") or "").strip()
    if not image_base64:
        return ""
    if image_base64.startswith("data:image/"):
        return image_base64

    raw_ref = screenshot.get("raw_screenshot_ref", "")
    suffix = raw_ref.rsplit(".", 1)[-1].lower() if "." in raw_ref else "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    if mime not in {"png", "jpeg", "webp", "gif"}:
        mime = "png"
    return f"data:image/{mime};base64,{image_base64}"


def _should_use_openai_vision(screenshot: ScreenshotInput) -> bool:
    mode = os.environ.get(VISION_MODE_ENV, "auto").strip().lower()
    if mode in {"fallback", "disabled", "off", "false", "0"}:
        return False
    return bool(os.environ.get("OPENAI_API_KEY") and _image_data_url(screenshot))


def _extract_json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("vision model returned non-object JSON")
    return parsed


def _person_from_openai_payload(payload: dict[str, Any], source: Source, raw_ref: str) -> Person:
    id_seed = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return _person_from_fields(payload, source, raw_ref, id_seed)


def _openai_vision_extract_person(screenshot: ScreenshotInput, source: Source, raw_ref: str) -> Person | None:
    image_url = _image_data_url(screenshot)
    if not image_url:
        return None

    try:
        from openai import OpenAI

        client = OpenAI()
        model = os.environ.get(VISION_MODEL_ENV, DEFAULT_VISION_MODEL)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format=VISION_RESPONSE_FORMAT,
            messages=[
                {"role": "system", "content": VISION_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"source_hint: {source}\n"
                                f"raw_screenshot_ref: {raw_ref}\n"
                                "Extract the contact profile into the required JSON schema."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        return _person_from_openai_payload(_extract_json_object(content), source, raw_ref)
    except Exception:
        return None


@weave.op()
def vision_extract_person(screenshot: ScreenshotInput) -> Person:
    source = screenshot.get("source") or infer_source(screenshot.get("raw_screenshot_ref", ""))
    raw_ref = screenshot.get("raw_screenshot_ref", f"{source}-{uuid.uuid4().hex[:8]}")
    text = screenshot.get("text", "")

    person = None
    if _should_use_openai_vision(screenshot):
        person = _openai_vision_extract_person(screenshot, source, raw_ref)
    if person is None:
        # Fallback keeps local/demo runs deterministic when API credentials or network are unavailable.
        person = _person_from_fixed_text(text, source, raw_ref)
        _apply_known_screenshot_fallback(person, raw_ref)

    dataset = str(screenshot.get("dataset") or person.get("dataset") or "")
    screenshot_is_demo = screenshot.get("is_demo")
    prepare_person_record(
        person,
        dataset=dataset or None,
        is_demo=bool(screenshot_is_demo) if screenshot_is_demo is not None else None,
    )
    person["embedding"] = embed_text(person_text(person))
    return person


@weave.op()
def entity_resolution_agent(people: list[Person]) -> list[Person]:
    merged: list[Person] = []
    for person in people:
        prepare_person_record(person)
        match_index: int | None = None
        match_score = 0.0
        match_reasons: list[str] = []
        for existing in merged:
            scored = duplicate_score(existing, person)
            if scored["score"] >= DUPLICATE_AUTO_MERGE_SCORE:
                match_index = merged.index(existing)
                match_score = scored["score"]
                match_reasons = list(scored["reasons"])
                break

        if match_index is None:
            merged.append(person)
            continue

        merged[match_index] = merge_people(merged[match_index], person, score=match_score, reasons=match_reasons)

    return merged


@dataclass
class PRMRedisStore:
    mode: str = "auto"

    def __post_init__(self) -> None:
        self.layer = create_data_layer(self.mode)
        self.client: redis.Redis | None = getattr(self.layer, "client", None)

    @property
    def status(self) -> str:
        return self.layer.status

    def ensure_index(self) -> bool:
        if self.client is None:
            return False
        try:
            existing = [str(item) for item in self.client.execute_command("FT._LIST")]
            if PERSON_INDEX in existing:
                return True
            self.client.execute_command(
                "FT.CREATE",
                PERSON_INDEX,
                "ON",
                "JSON",
                "PREFIX",
                "1",
                "person:",
                "SCHEMA",
                "$.embedding",
                "AS",
                "embedding",
                "VECTOR",
                "FLAT",
                "6",
                "TYPE",
                "FLOAT32",
                "DIM",
                str(EMBED_DIM),
                "DISTANCE_METRIC",
                "COSINE",
                "$.name",
                "AS",
                "name",
                "TEXT",
                "$.company",
                "AS",
                "company",
                "TEXT",
            )
            return True
        except Exception:
            return False

    def save_person(self, person: Person) -> str:
        prepare_person_record(person)
        key = f"person:{person['id']}"
        PRM_MEMORY_PEOPLE[person["id"]] = person
        if self.client is None:
            return key
        try:
            self.client.execute_command("JSON.SET", key, "$", json.dumps(person))
        except Exception:
            self.client.set(key, json.dumps(person))
        return key

    def delete_person(self, person_id: str) -> bool:
        removed = PRM_MEMORY_PEOPLE.pop(person_id, None) is not None
        if self.client is not None:
            removed = bool(self.client.delete(f"person:{person_id}")) or removed

        for review_id, review in list(PRM_DUPLICATE_REVIEWS.items()):
            if review.get("candidate_id") == person_id or review.get("existing_id") == person_id:
                PRM_DUPLICATE_REVIEWS.pop(review_id, None)
                if self.client is not None:
                    self.client.delete(f"duplicate_review:{review_id}")
        return removed

    def save_duplicate_review(self, review: dict[str, Any]) -> str:
        review_id = str(review["id"])
        PRM_DUPLICATE_REVIEWS[review_id] = review
        if self.client is not None:
            self.client.set(f"duplicate_review:{review_id}", json.dumps(review))
        return review_id

    def _duplicate_review_keys(self) -> list[str]:
        if self.client is None:
            return []
        keys: list[str] = []
        cursor: int | str = 0
        while True:
            cursor, batch = self.client.scan(cursor=cursor, match="duplicate_review:*", count=250)
            keys.extend(str(key) for key in batch)
            if int(cursor) == 0:
                return keys

    def list_duplicate_reviews(self) -> list[dict[str, Any]]:
        reviews = list(PRM_DUPLICATE_REVIEWS.values())
        seen = {str(review.get("id")) for review in reviews}
        if self.client is not None:
            pipe = self.client.pipeline()
            keys = self._duplicate_review_keys()
            for key in keys:
                pipe.get(key)
            for value in pipe.execute(raise_on_error=False):
                if not value or isinstance(value, Exception):
                    continue
                review = json.loads(value)
                review_id = str(review.get("id"))
                if review_id not in seen:
                    reviews.append(review)
                    seen.add(review_id)
        return sorted(reviews, key=lambda item: item.get("score", 0), reverse=True)

    def save_people_with_dedupe(self, people: list[Person]) -> dict[str, Any]:
        keys: list[str] = []
        saved_ids: list[str] = []
        merged: list[dict[str, Any]] = []
        pending_reviews: list[dict[str, Any]] = []

        for person in people:
            prepare_person_record(person)
            existing_people = self.list_people()
            candidates = duplicate_candidates_for(person, existing_people)
            top_candidate = candidates[0] if candidates else None

            if top_candidate and top_candidate["score"] >= DUPLICATE_AUTO_MERGE_SCORE and not top_candidate["conflicts"]:
                existing = next((item for item in existing_people if item.get("id") == top_candidate["existing_id"]), None)
                if existing is not None:
                    merged_person = merge_people(
                        existing,
                        person,
                        score=top_candidate["score"],
                        reasons=list(top_candidate["reasons"]),
                    )
                    keys.append(self.save_person(merged_person))
                    merged.append(
                        {
                            "kept_id": merged_person.get("id"),
                            "merged_id": person.get("id"),
                            "score": top_candidate["score"],
                            "reasons": top_candidate["reasons"],
                        }
                    )
                    continue

            if top_candidate:
                person["duplicate_status"] = "needs_review"
                person["duplicate_candidates"] = candidates[:3]
                for candidate in candidates[:3]:
                    pending_reviews.append(candidate)
                    self.save_duplicate_review(candidate)

            keys.append(self.save_person(person))
            saved_ids.append(str(person.get("id")))

        return {
            "keys": keys,
            "saved_ids": saved_ids,
            "merged": merged,
            "pending_reviews": pending_reviews,
        }

    def delete_demo_people(self) -> dict[str, Any]:
        demo_ids = [str(person.get("id")) for person in self.list_people() if person.get("id") and is_demo_person(person)]
        deleted_ids = [person_id for person_id in demo_ids if self.delete_person(person_id)]
        return {
            "deleted_count": len(deleted_ids),
            "deleted_ids": deleted_ids,
            "remaining_count": len(self.list_people()),
            "redis_status": self.status,
        }

    def export_people(self) -> dict[str, Any]:
        people = self.list_people()
        return {
            "exported_at": _now(),
            "redis_status": self.status,
            "person_count": len(people),
            "people": people,
            "duplicate_reviews": self.list_duplicate_reviews(),
        }

    def _person_keys(self, limit: int | None = None) -> list[str]:
        if self.client is None:
            return []
        keys: list[str] = []
        cursor: int | str = 0
        while True:
            cursor, batch = self.client.scan(cursor=cursor, match="person:*", count=250)
            keys.extend(str(key) for key in batch)
            if limit is not None and len(keys) >= limit:
                return keys[:limit]
            if int(cursor) == 0:
                return keys

    @staticmethod
    def _parse_person_payload(value: Any) -> Person | None:
        if not value or isinstance(value, Exception):
            return None
        parsed = json.loads(value)
        return parsed[0] if isinstance(parsed, list) else parsed

    def _load_people(self, keys: list[str]) -> list[Person]:
        if self.client is None or not keys:
            return []

        people: list[Person] = []
        fallback_keys: list[str] = []
        json_pipe = self.client.pipeline()
        for key in keys:
            json_pipe.execute_command("JSON.GET", key, "$")
        json_values = json_pipe.execute(raise_on_error=False)

        for key, value in zip(keys, json_values, strict=False):
            person = self._parse_person_payload(value)
            if person is None:
                fallback_keys.append(key)
            else:
                people.append(person)

        if fallback_keys:
            raw_pipe = self.client.pipeline()
            for key in fallback_keys:
                raw_pipe.get(key)
            for value in raw_pipe.execute(raise_on_error=False):
                person = self._parse_person_payload(value)
                if person is not None:
                    people.append(person)

        return people

    def list_people(self, limit: int | None = None) -> list[Person]:
        memory_people = list(PRM_MEMORY_PEOPLE.values())
        if self.client is None:
            return memory_people[:limit] if limit is not None else memory_people
        people = self._load_people(self._person_keys(limit))
        seen = {person["id"] for person in people}
        for person in memory_people:
            if limit is not None and len(people) >= limit:
                break
            if person["id"] not in seen:
                people.append(person)
        return people

    def vector_search(self, query: str, limit: int = 5) -> list[tuple[Person, float]]:
        query_embedding = embed_text(query)
        if self.client is not None and self.ensure_index():
            try:
                blob = np.array(query_embedding, dtype=np.float32).tobytes()
                result = self.client.execute_command(
                    "FT.SEARCH",
                    PERSON_INDEX,
                    f"*=>[KNN {limit} @embedding $vec AS score]",
                    "PARAMS",
                    "2",
                    "vec",
                    blob,
                    "SORTBY",
                    "score",
                    "RETURN",
                    "3",
                    "$",
                    "score",
                    "DIALECT",
                    "2",
                )
                hits: list[tuple[Person, float]] = []
                for i in range(2, len(result), 2):
                    fields = result[i]
                    payload = "{}"
                    score = 1.0
                    for index, field_name in enumerate(fields):
                        if field_name == "$" and index + 1 < len(fields):
                            payload = fields[index + 1]
                        if field_name == "score" and index + 1 < len(fields):
                            score = float(fields[index + 1])
                    parsed = json.loads(payload)
                    hits.append((parsed, 1 - score))
                if hits:
                    return hits
            except Exception:
                pass

        ranked = [(person, cosine(query_embedding, person["embedding"])) for person in self.list_people()]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:limit]


@weave.op()
def store_people_agent(people: list[Person], redis_mode: str = "auto") -> dict[str, Any]:
    store = PRMRedisStore(redis_mode)
    index_ready = store.ensure_index()
    result = store.save_people_with_dedupe(people)
    return {
        "keys": result["keys"],
        "count": len(result["keys"]),
        "saved_ids": result["saved_ids"],
        "merged": result["merged"],
        "pending_reviews": result["pending_reviews"],
        "duplicate_review_count": len(result["pending_reviews"]),
        "redis_status": store.status,
        "vector_index_ready": index_ready,
    }


def distribute_screenshots(state: IngestState) -> list[Send]:
    return [Send("vision_agent", {"screenshots": [screenshot]}) for screenshot in state["screenshots"]]


def vision_node(state: IngestState) -> dict[str, Any]:
    screenshot = state["screenshots"][0]
    ref = screenshot.get("raw_screenshot_ref", "screenshot")
    with mon.track("vision_agent", group=ref) as span:
        person = vision_extract_person(screenshot)
        span["summary"] = f"{person.get('name') or '?'} · {person.get('company') or '?'}"
    return {"extracted": [person]}


def resolution_node(state: IngestState) -> dict[str, Any]:
    with mon.track("entity_resolution") as span:
        people = entity_resolution_agent(state.get("extracted", []))
        span["summary"] = f"{len(people)} unique people"
    return {"people": people}


def storage_node(state: IngestState) -> dict[str, Any]:
    with mon.track("redis_store") as span:
        storage = store_people_agent(state.get("people", []), state.get("redis_mode", "auto"))
        span["summary"] = f"{storage['count']} saved · {storage['redis_status']}"
    return {"storage": storage}


def build_ingest_graph():
    graph = StateGraph(IngestState)
    graph.add_node("vision_agent", vision_node)
    graph.add_node("entity_resolution", resolution_node)
    graph.add_node("redis_store", storage_node)
    graph.add_conditional_edges(START, distribute_screenshots, ["vision_agent"])
    graph.add_edge("vision_agent", "entity_resolution")
    graph.add_edge("entity_resolution", "redis_store")
    graph.add_edge("redis_store", END)
    return graph.compile()


INGEST_GRAPH = build_ingest_graph()


@weave.op()
def langgraph_ingest_swarm(screenshots: list[ScreenshotInput], redis_mode: str = "auto") -> dict[str, Any]:
    with mon.track("orchestrator") as span:
        span["summary"] = f"fan-out {len(screenshots)} screenshot(s)"
        return INGEST_GRAPH.invoke({"screenshots": screenshots, "extracted": [], "redis_mode": redis_mode})


@weave.op()
def matchmaker_agent(query: str, candidates: list[tuple[Person, float]]) -> dict[str, Any]:
    ranked = []
    terms = set(re.findall(r"[a-zA-Z0-9+#.\-]+", query.lower()))
    for person, similarity in candidates:
        haystack = person_text(person).lower()
        keyword_overlap = sum(1 for term in terms if term in haystack)
        score = round(similarity + keyword_overlap * 0.08, 4)
        ranked.append(
            {
                "person": person,
                "score": score,
                "reason": f"Matches query through {person['role']} at {person['company']} in {person['location']}; interests include {', '.join(person['interests'][:3])}.",
                "draft_message": f"Hi {person['name']}, I’m looking for someone who can help with: {query}. Given your work around {', '.join(person['interests'][:2])}, would you be open to a quick intro?",
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {"query": query, "recommendations": ranked[:3]}


def demo_screenshots() -> list[ScreenshotInput]:
    return [
        {
            "source": "linkedin",
            "raw_screenshot_ref": "li_anna_gpu.png",
            "text": "Name: Anna Chen\nCompany: NVIDIA\nRole: GPU Kernel Engineer\nLocation: SF\nInterests: CUDA, GPU kernel, systems\nHow_we_met: LinkedIn AI infra group",
            "dataset": DEMO_DATASET,
            "is_demo": True,
        },
        {
            "source": "wechat",
            "raw_screenshot_ref": "wechat_ben_founder.png",
            "text": "Name: Ben Liu\nCompany: NeonDB\nRole: Founder\nLocation: New York\nInterests: databases, Redis, startups\nHow_we_met: WeChat founder circle",
            "dataset": DEMO_DATASET,
            "is_demo": True,
        },
        {
            "source": "whatsapp",
            "raw_screenshot_ref": "wa_carla_design.png",
            "text": "Name: Carla Gomez\nCompany: Figma\nRole: Product Designer\nLocation: Remote\nInterests: design systems, AI UX\nHow_we_met: WhatsApp design group",
            "dataset": DEMO_DATASET,
            "is_demo": True,
        },
        {
            "source": "linkedin",
            "raw_screenshot_ref": "li_david_ml.png",
            "text": "Name: David Park\nCompany: OpenAI\nRole: Research Engineer\nLocation: SF\nInterests: agents, evals, LLM infrastructure\nHow_we_met: LinkedIn LangGraph thread",
            "dataset": DEMO_DATASET,
            "is_demo": True,
        },
        {
            "source": "wechat",
            "raw_screenshot_ref": "wechat_emma_vc.png",
            "text": "Name: Emma Wang\nCompany: Aster Capital\nRole: Investor\nLocation: SF\nInterests: AI infra, developer tools\nHow_we_met: WeChat hackathon group",
            "dataset": DEMO_DATASET,
            "is_demo": True,
        },
        {
            "source": "whatsapp",
            "raw_screenshot_ref": "wa_frank_ops.png",
            "text": "Name: Frank Patel\nCompany: AWS\nRole: Solutions Architect\nLocation: Seattle\nInterests: cloud, vector search, Redis\nHow_we_met: WhatsApp cloud builders",
            "dataset": DEMO_DATASET,
            "is_demo": True,
        },
    ]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _demo_name(index: int) -> str:
    first = DEMO_FIRST_NAMES[index % len(DEMO_FIRST_NAMES)]
    last = DEMO_LAST_NAMES[(index * 7 + index // len(DEMO_FIRST_NAMES)) % len(DEMO_LAST_NAMES)]
    return f"{first} {last}"


def _demo_interests(index: int, topics: list[str]) -> list[str]:
    target_count = 2 + (index % 3)
    interests: list[str] = []
    for offset in range(len(topics)):
        topic = topics[(index + offset) % len(topics)]
        if topic not in interests:
            interests.append(topic)
        if len(interests) == target_count:
            return interests

    extra_index = index * 5
    while len(interests) < target_count:
        topic = DEMO_EXTRA_TOPICS[(extra_index + len(interests) * 7) % len(DEMO_EXTRA_TOPICS)]
        if topic not in interests:
            interests.append(topic)
        extra_index += 1
    return interests


def generate_demo_people(size: int = 100) -> list[Person]:
    """Build a deterministic, cluster-friendly demo graph without vision extraction."""
    if size < 1:
        raise ValueError("size must be at least 1")

    people: list[Person] = []
    for index in range(size):
        profile = DEMO_COMPANY_PROFILES[index % len(DEMO_COMPANY_PROFILES)]
        company = str(profile["company"])
        roles = list(profile["roles"])
        locations = list(profile["locations"])
        topics = list(profile["topics"])
        source = DEMO_SOURCES[index % len(DEMO_SOURCES)]
        name = _demo_name(index)
        role = str(roles[(index // len(DEMO_COMPANY_PROFILES) + index) % len(roles)])
        location = str(locations[(index // len(DEMO_COMPANY_PROFILES) + index) % len(locations)])
        interests = _demo_interests(index, topics)
        channels = DEMO_SOURCE_CHANNELS[source]
        how_we_met = channels[(index // len(DEMO_SOURCES) + index) % len(channels)]
        raw_ref = f"demo_people/{source}/{index + 1:03d}_{_slug(name)}.json"
        person_id = hashlib.sha1(f"demo-person-v1:{index}:{name}:{company}".encode("utf-8")).hexdigest()[:12]
        person: Person = {
            "id": person_id,
            "name": name,
            "company": company,
            "role": role,
            "location": location,
            "interests": interests,
            "how_we_met": how_we_met,
            "source": source,
            "embedding": [],
            "raw_screenshot_ref": raw_ref,
        }
        prepare_person_record(person, dataset=DEMO_DATASET, is_demo=True)
        person["embedding"] = embed_text(person_text(person))
        people.append(person)

    return people


def seed_demo_people(size: int = 100, redis_mode: str = "auto") -> dict[str, Any]:
    mon.start_run("ingest", meta={"mode": "seed", "size": size})
    try:
        with mon.track("generate_demo") as span:
            people = generate_demo_people(size)
            span["summary"] = f"{len(people)} people generated"
        with mon.track("redis_store") as span:
            storage = store_people_agent(people, redis_mode)
            span["summary"] = f"{storage['count']} saved · {storage['redis_status']}"
        return {"people": people, "storage": storage}
    finally:
        mon.finish_run({"label": f"Seed {size} demo people", "weave_call_url": None})


def run_ingest(
    screenshots: list[ScreenshotInput],
    weave_mode: str | None = None,
    redis_mode: str | None = None,
) -> dict[str, Any]:
    active_mode = init_weave(os.environ.get("WEAVE_PROJECT", DEFAULT_PROJECT), weave_mode or os.environ.get("WEAVE_MODE", "auto"))
    mon.start_run("ingest", meta={"mode": "screenshots", "screenshots": len(screenshots)})
    call_url = None
    try:
        result, call = langgraph_ingest_swarm.call(screenshots, redis_mode or os.environ.get("REDIS_MODE", "auto"))
        try:
            call_url = call.ui_url
        except ValueError:
            call_url = None
        return {"weave_mode": active_mode, "weave_call_url": call_url, "result": result}
    finally:
        mon.finish_run({"label": f"Ingest {len(screenshots)} screenshot(s)", "weave_call_url": call_url, "weave_mode": active_mode})


def run_match(query: str, weave_mode: str | None = None, redis_mode: str | None = None) -> dict[str, Any]:
    active_mode = init_weave(os.environ.get("WEAVE_PROJECT", DEFAULT_PROJECT), weave_mode or os.environ.get("WEAVE_MODE", "auto"))
    mon.start_run("match", meta={"query": query})
    call_url = None
    try:
        store = PRMRedisStore(redis_mode or os.environ.get("REDIS_MODE", "auto"))
        with mon.track("vector_search") as span:
            candidates = store.vector_search(query, limit=5)
            span["summary"] = f"{len(candidates)} candidates from {store.status}"
        with mon.track("matchmaker_agent") as span:
            result, call = matchmaker_agent.call(query, candidates)
            span["summary"] = f"{len(result['recommendations'])} recommendations"
        try:
            call_url = call.ui_url
        except ValueError:
            call_url = None
        return {
            "weave_mode": active_mode,
            "weave_call_url": call_url,
            "redis_status": store.status,
            "result": result,
            "people": store.list_people(),
        }
    finally:
        mon.finish_run({"label": f'Match "{query[:48]}"', "weave_call_url": call_url, "weave_mode": active_mode})
