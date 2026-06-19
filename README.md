# Contax AI

Contax AI turns contact screenshots and profile notes into an interactive relationship graph. It helps you understand who is in your network, how people are connected by company, role, location, interests, and source, and who is most relevant for a specific request.

The app is built around one workflow: upload or load contacts, explore the graph, ask for the right person, and review an intro draft before taking action.

## Core Features

- Ingest contact screenshots from LinkedIn, WeChat, WhatsApp, and similar sources.
- Extract structured contact records with name, company, role, location, interests, source, and how-you-met context.
- Store contacts in Redis so the graph can persist across sessions.
- Detect overlapping contacts and keep duplicate-review data available for cleanup.
- Render an interactive relationship graph grouped by companies, topics, roles, places, and sources.
- Highlight the best matching parts of the graph for a natural-language request.
- Draft warm intro messages for the top recommended contacts.
- Open a contact detail panel with profile metadata, tags, and the original screenshot reference.
- Generate a Vapi-ready mock interview brief for a selected contact and validate it with a live assistant chat.
- Monitor ingest and match runs with agent topology, timeline, Redis status, and Weave trace links.

## Main Screens

### Graph

The Graph view is the primary workspace. It shows the relationship map, contact count, storage status, upload controls, demo loading, match highlights, and the Network Copilot sidebar.

Use it to:

1. Upload contact screenshots.
2. Load demo contacts for a quick walkthrough.
3. Click tags or people to inspect the network.
4. Ask the copilot for a need such as `Find someone in SF who knows GPU kernels`.
5. Review the ranked contacts and copy or approve the generated intro drafts.

### Monitor

The Monitor view explains what happened behind the scenes. It shows the latest ingest and match runs, each agent span, Redis memory status, and timing for the pipeline.

Use it to debug the flow, confirm Redis connectivity, inspect recent agent activity, and open Weave traces when tracing is enabled.

## How It Works

1. Screenshots are uploaded from the browser or loaded from demo data.
2. The backend extracts or prepares contact records.
3. Entity-resolution logic merges obvious duplicates and stores review candidates.
4. Redis keeps the contact graph and vector-search-ready memory.
5. The frontend builds a relationship graph from structured tags.
6. The matchmaker ranks contacts for a natural-language request and returns reasons plus intro drafts.
7. The monitor records agent spans so the pipeline can be inspected after each run.

## Local Run

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm install
```

Start the backend:

```bash
source .venv/bin/activate
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```bash
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open:

```text
http://127.0.0.1:3000
```

## Useful Configuration

The app reads local settings from `.env`.

```bash
REDIS_MODE=real
REDIS_URL=redis://localhost:6379/0
WEAVE_MODE=auto
OPENAI_API_KEY=<your-openai-key>
VAPI_API_KEY=<your-vapi-key>
```

Use `REDIS_MODE=fake` for an in-memory demo. Use `WEAVE_MODE=disabled` when you do not need trace links.
