# Relationship Graph PRM

WeaveHacks 4 demo: a multi-agent personal relationship manager. It ingests social screenshots, extracts structured people, stores them in Redis Stack, renders a relationship graph, and uses a CopilotKit cockpit to match a natural-language need to the best contacts.

## Stack

- LangGraph Python for multi-agent orchestration
- Redis Stack for RedisJSON storage and vector search
- Weave for traceable `weave.op()` calls
- Next.js, CopilotKit v2, and React Flow for the frontend cockpit

## Environment

Copy the sample file and put real credentials only in `.env`.

```bash
cp .env.example .env
```

Useful values:

```bash
WEAVE_PROJECT=weavehacks-prm
WEAVE_MODE=auto
WANDB_API_KEY=<your-wandb-key>
OPENAI_API_KEY=<your-openai-key>
PRM_VISION_MODEL=gpt-4o-mini
PRM_VISION_MODE=auto
REDIS_MODE=real
REDIS_URL=redis://localhost:6379/0
```

Use `WEAVE_MODE=online` to require hosted Weave traces, or `WEAVE_MODE=auto` to trace online only when `WANDB_API_KEY` / `wandb login` is available. Use `WEAVE_MODE=disabled` for local dry runs. Use `REDIS_MODE=fake` if you need a non-persistent test fallback.

When `OPENAI_API_KEY` is present, uploaded screenshots with `image_base64` are extracted by the Vision agent using `PRM_VISION_MODEL` (`gpt-4o-mini` by default). Set `PRM_VISION_MODE=fallback` to force the old fixed-format parser.

## Local Redis Stack

Real contacts should use a local Redis Stack database as the primary store. The app needs RedisJSON and RediSearch, so use Redis Stack rather than plain Redis.

Start the local database:

```bash
docker compose -f docker-compose.redis.yml up -d
```

Then keep:

```bash
REDIS_MODE=real
REDIS_URL=redis://localhost:6379/0
```

This keeps contact JSON, duplicate-review records, and embeddings on your machine. The compose file binds Redis to `127.0.0.1:6379`, so it is not exposed to your local network by default.

## Privacy Notes For Real Contacts

The repository can be public without exposing your contacts as long as you do not commit real screenshots, exported JSON, Redis dumps, or `.env` files. Keep real inputs in ignored folders such as `private_contacts/`, `real_contacts/`, or `contact_exports/`.

External services are separate privacy surfaces:

- `REDIS_MODE=real` sends contact JSON and embeddings to the configured Redis server. With the default `REDIS_URL=redis://localhost:6379/0`, that server is local.
- `WEAVE_MODE=online` or a logged-in Weave/W&B session can send trace metadata to Weave.
- `OPENAI_API_KEY` with `PRM_VISION_MODE=auto` sends uploaded screenshot images to the configured vision model provider.

For the most local/private workflow, use a local Redis Stack instance, `WEAVE_MODE=disabled`, and `PRM_VISION_MODE=fallback` unless you intentionally want hosted extraction or tracing.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm install
```

## Run The Demo

Start FastAPI:

```bash
source .venv/bin/activate
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Start Next.js in another terminal:

```bash
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`.

Demo path:

1. Click `Load demo`.
2. Watch the company/topic clusters emerge in the graph.
3. Ask: `Find someone in SF who knows GPU kernel optimization`.
4. The graph highlights matching people and shows reasons.
5. Click `Review Draft` to show the human approval modal.
6. Click a Weave trace link when `WEAVE_MODE=auto` or `online`.

## API Contract

`POST /ingest`

```json
{
  "demo": true,
  "screenshots": []
}
```

`POST /api/seed`

```json
{
  "size": 100
}
```

`POST /match`

```json
{
  "query": "Find someone in SF who knows GPU kernel optimization",
  "ensure_demo_data": false
}
```

`GET /api/prm/export` exports all current contacts and duplicate-review records as JSON before cleanup.

`GET /api/prm/duplicates` returns pending duplicate-review candidates.

`POST /api/prm/delete-demo`

```json
{
  "confirm": true
}
```

This deletes only contacts marked with `dataset=demo` / `is_demo=true`; it does not clear real contacts.

When request-level `weave_mode` / `redis_mode` values are omitted, the backend uses `.env`. Also available under `/api/prm/ingest`, `/api/prm/seed`, `/api/prm/match`, and `/api/prm/people`.

## What To Say In The Pitch

This is not a single contact-search chatbot. The demo is a multi-agent orchestration layer:

- The orchestrator fans screenshots out to parallel Vision agents.
- The entity-resolution agent merges duplicates across platforms.
- Redis stores Person JSON and vector memory.
- The matchmaker retrieves candidates and ranks them with reasons.
- CopilotKit turns the graph into an operator cockpit with human approval.
- Weave traces every important agent and storage step.

## Verify

```bash
source .venv/bin/activate
python -m unittest discover -v
npm run build
```

Optional Redis integration smoke test:

```bash
python -c "from prm_pipeline import demo_screenshots, run_ingest, run_match; r=run_ingest(demo_screenshots(), weave_mode='disabled', redis_mode='real'); print(r['result']['storage']['count'], r['result']['storage']['vector_index_ready']); m=run_match('Find someone in SF who knows GPU kernel optimization', weave_mode='disabled', redis_mode='real'); print([x['person']['name'] for x in m['result']['recommendations'][:3]])"
```

## Legacy Harness

The repo still includes the earlier deterministic Weave multi-agent demo and NPC harness endpoints:

- `POST /api/runs`
- `GET /api/npc/session`
- `POST /api/npc/step`

They are kept for comparison and regression tests, but the hackathon flow should use the PRM screen.
