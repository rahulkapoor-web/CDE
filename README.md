# ONA — AI Planning Engine

Turns a JIRA requirement plus live Salesforce/GitHub context into a precise,
ordered, schema-validated change plan for Salesforce Life Sciences Cloud (LSC)
implementations. A Salesforce architect or developer reviews, exports, and
approves the generated plan.

## What it does

1. **Gathers context** from JIRA (ticket fields), GitHub (branch, commits, open
   PRs), and Salesforce (live org metadata snapshot or an SFDX project source).
2. **Generates a plan** by driving the ONA planning system prompt through a
   pluggable LLM provider (Anthropic Claude or OpenAI).
3. **Validates strictly** against a canonical JSON schema plus business rules
   (≥1 Test step, production steps require sandbox counterparts, acyclic
   dependencies, rollback on high-risk steps), auto-retrying on invalid output.
4. **Presents & exports** the plan as reviewable step cards with risk badges and
   managed-package warnings, a raw-JSON toggle, and JSON/Markdown export.

## Architecture

- **Backend**: Python 3.12 / FastAPI (async), SQLAlchemy 2.x, Alembic.
- **Frontend**: React 18 / TypeScript / Vite / Ant Design.
- **Database**: PostgreSQL 16 (users, connections, plans, guide documents).
- **Auth**: JWT; connection credentials encrypted at rest (Fernet).
- **LLM**: provider interface with Anthropic + OpenAI adapters, selected by
  `LLM_PROVIDER`.
- **LSC guide RAG**: optional document ingestion with embeddings; portable
  cosine/keyword fallback and graceful no-op when no guide docs are loaded.

## Quick start

### Docker Compose

```bash
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Local development

```bash
# Postgres
docker run -d --name ona-pg -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ona_planner \
  -p 5432:5432 postgres:16

# Backend
cd backend
pip install -r requirements.txt
DATABASE_URL_SYNC=postgresql+psycopg2://postgres:postgres@localhost:5432/ona_planner \
  alembic upgrade head
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ona_planner \
  uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Configuration

Set via environment (`backend/.env`, see `backend/.env.example`):

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Async Postgres URL | `postgresql+asyncpg://postgres:postgres@localhost:5432/ona_planner` |
| `DATABASE_URL_SYNC` | Sync URL for Alembic | matching psycopg2 URL |
| `SECRET_KEY` | JWT signing key | dev default |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key; derived from `SECRET_KEY` if unset | (derived) |
| `LLM_PROVIDER` | `anthropic` or `openai` | `anthropic` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Claude config | — / `claude-sonnet-4-5` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI config | — / `gpt-4o` |
| `PLAN_MAX_RETRIES` | Retries on invalid LLM output | `2` |
| `EMBEDDING_PROVIDER` | `openai` or `none` for guide RAG | `none` |

## Usage

1. **Register / Login**.
2. **Connections** — add JIRA, GitHub, and Salesforce connection profiles;
   secrets are encrypted and never returned by the API. Use **Test** to verify.
3. **Generate** — pick connections + a JIRA ticket ID (and optional SFDX path),
   click **Gather Context**, review/edit the consolidated context, then
   **Generate Plan**. Any field can be entered manually if no live connection is
   configured.
4. **Plan view** — review ordered step cards (type/environment/automation badges,
   dependencies, rollback, managed-package warnings), risk and classification,
   testing requirements, deployment sequence, and open questions. Toggle raw JSON
   or export JSON/Markdown.
5. **Plans** — browse per-user history and re-open past plans.

## LSC guide grounding (optional)

`POST /api/guide/ingest` stores guide sections for retrieval. When documents are
present, relevant excerpts ground the plan's `lsc_guide_references`. When absent,
the model uses its knowledge and emits
`"Verify in LSC Configuration Guide: [topic]"` rather than fabricating citations.

## Testing

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ona_planner \
  python -m pytest -q
```

Covers plan schema and business-rule validation, prompt assembly, secret
encryption, SFDX parsing, the planning engine (generation, JSON extraction,
retry), and a full in-process API flow with a mocked provider. Integration tests
skip automatically if no database is reachable.

## Plan schema

The canonical JSON schema is served at `GET /api/planning/schema` and defined in
`backend/app/schemas/plan_schema.py`, mirrored by the Pydantic models in
`backend/app/schemas/plan.py`.
