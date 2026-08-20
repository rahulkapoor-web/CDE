# ONA — AI Planning Engine

## Problem Statement

Salesforce Life Sciences Cloud (LSC) delivery teams receive JIRA tickets that must be
translated into safe, ordered, executable change plans. Today this planning is manual,
inconsistent, and error-prone: architects must recall LSC managed-package constraints,
deployment ordering rules, sandbox-first practices, and regulatory concerns from memory.

**ONA — AI Planning Engine** is a full-stack web application that ingests a JIRA
requirement together with live Salesforce org context, GitHub repo state, and LSC
Configuration Guide references, then produces a precise, ordered, schema-validated change
plan (as structured JSON, rendered for review) for a Salesforce architect or developer to
approve. The application wraps the ONA planning system prompt, drives it through a
pluggable LLM provider, validates the output against a strict schema, and presents it in a
reviewable, exportable UI.

## Goals

- Generate deterministic, schema-conformant LSC change plans from JIRA tickets.
- Gather org/repo/guide context automatically via live integrations, with manual fallback.
- Enforce the ONA planning contract (classification, risk, ordered steps, testing,
  deployment sequence, rollback, open questions) via a strict JSON schema.
- Let architects review, edit inputs, regenerate, and export approved plans.

## Non-Goals

- Executing the generated plan (no automated deployment to Salesforce from this app).
- Writing Apex/LWC/flow metadata on the user's behalf.
- Replacing JIRA or GitHub as systems of record.

## Users

- **Salesforce Architect** — reviews and approves plans, manages connections.
- **Salesforce Developer** — executes plan steps manually; consumes exports.

## Decisions (confirmed with requester)

| Topic | Decision |
|---|---|
| Deliverable | Full app: backend API + web UI |
| Codebase | Fresh start on current branch (`Salesforce_Devlopment_Agent`) |
| LLM provider | Pluggable/configurable via env (Claude + OpenAI adapters) |
| Integrations | Live JIRA + GitHub + Salesforce, with manual paste fallback |
| Auth & persistence | User auth + PostgreSQL (store users, connections, plans, history) |
| SF metadata source | Both live SF API and SFDX project source |
| LSC guide references | Both: RAG over ingested guide docs if present, else model knowledge |
| Plan presentation | Rendered plan view (step cards, risk, references) + raw JSON toggle + export |
| Output validation | Strict schema validation with auto-retry on invalid output |

## Stack (chosen)

- **Backend**: Python 3.12 / FastAPI (async), SQLAlchemy 2.x, Alembic migrations.
- **Frontend**: React 18 / TypeScript / Vite / Ant Design.
- **Database**: PostgreSQL 16.
- **Auth**: JWT (access token), passlib/bcrypt password hashing.
- **LLM abstraction**: provider interface with `anthropic` and `openai` adapters,
  selected by `LLM_PROVIDER` env var.
- **Schema validation**: Pydantic models mirroring the plan JSON schema; `jsonschema`
  for the canonical schema artifact.
- **RAG (LSC guide)**: local document ingestion + embedding store (pgvector on Postgres)
  with a no-op fallback when no guide docs are loaded.
- **Secrets**: connection credentials encrypted at rest (Fernet), never returned to client.
- **Dev env**: Docker Compose (db, redis optional) matching the existing devcontainer.

## Requirements

### R1 — Authentication & Users
- Register, login, logout; JWT-protected API.
- Passwords hashed (bcrypt). Tokens signed with `SECRET_KEY`.
- All plan/connection resources scoped to the authenticated user.

### R2 — Connection Management
- CRUD for three connection types: **JIRA**, **GitHub**, **Salesforce**.
- Salesforce connection supports sandbox/production flag and both auth styles
  (username+token, and OAuth client credentials/access token).
- Credentials encrypted at rest (Fernet); secrets masked/omitted in API responses.
- "Test connection" endpoint for each type.

### R3 — Context Gathering
- **JIRA**: fetch ticket by ID → summary, description, acceptance criteria, type, priority.
- **GitHub**: fetch branch, recent commits, open PRs for a configured repo.
- **Salesforce metadata snapshot** (both sources):
  - Live: query relevant objects, fields, flows, Apex classes, permission sets,
    org edition, active LSC modules, installed packages.
  - SFDX: parse metadata from a connected SFDX project checkout/path.
- **Manual fallback**: every context field can be entered/overridden by the user.
- Present a consolidated, editable "context" object before plan generation.

### R4 — LSC Guide References (RAG)
- Ingest LSC Configuration Guide documents (upload/local path) into a pgvector store.
- On generation, retrieve relevant sections and pass as grounding context.
- When no guide docs are present, instruct the model to use its knowledge and emit
  `"Verify in LSC Configuration Guide: [topic]"` rather than fabricating references.

### R5 — Plan Generation Engine
- Assemble the ONA system prompt (from the requester's spec) with all runtime variables
  filled from the gathered context (`{{JIRA_TICKET_ID}}`, `{{SF_ORG_EDITION}}`, etc.).
- Call the configured LLM provider; enforce JSON-only output.
- **Strict validation with auto-retry**: validate the response against the plan schema;
  on failure, re-prompt with the validation errors up to N (configurable, default 2)
  retries before surfacing a structured error to the user.
- Persist the generated plan (input snapshot + output JSON + provider/model + timestamp).
- Store the system prompt as a versioned, editable server-side asset.

### R6 — Plan Schema (canonical contract)
The output must conform exactly to the schema below (checked at runtime):

- `plan_id`, `jira_ticket`, `summary`
- `change_classification`: `Configuration | Customisation | Mixed`
- `deployment_risk`: `Low | Medium | High`, `risk_rationale`, `estimated_effort`
- `lsc_guide_references[]`: `{module, section, page_or_url, relevance}`
- `prerequisites[]`
- `steps[]`: `{step_number, title, type, environment, description,
  lsc_guide_reference, metadata_path, acceptance_check, estimated_minutes,
  automation_feasibility, automation_notes, dependencies[], rollback}`
  - `type`: `Configuration | Apex | LWC | Flow | PermissionSet | IntegrationSetup |
    DataMigration | Test | Deploy`
  - `environment`: `Sandbox | Production | Both | GitHub`
  - `automation_feasibility`: `Full | Partial | Manual`
- `testing_requirements`: `{unit_tests, functional_tests, regression_areas,
  minimum_code_coverage}`
- `deployment_sequence`: `{sandbox_steps[], production_steps[], github_actions_steps[]}`
- `post_deployment[]`
- `open_questions[]`
- `copilot_assist_available`, `copilot_suggested_actions[]`

Enforced business rules (validated post-parse):
- At least one step of `type: Test` must exist.
- No production step may lack a corresponding sandbox step in `deployment_sequence`.
- `dependencies` must reference valid earlier `step_number`s (no cycles).
- Steps that are destructive/high-risk must have a non-empty `rollback`.

### R7 — Plan Presentation & Export (UI)
- **Rendered plan view**: summary header (classification, risk badge, effort);
  prerequisites list; ordered step cards showing type/environment badges, description,
  acceptance check, automation feasibility, dependencies, and rollback; testing
  requirements panel; deployment sequence; post-deployment; open questions (highlighted).
- Managed-package warnings (`⚠️ MANAGED PACKAGE FIELD`) visually flagged.
- **Raw JSON toggle** to view/copy the exact JSON.
- **Export**: download plan as JSON and Markdown.
- **History**: list past plans per user with re-open and regenerate.

### R8 — Configuration & Secrets
- Env-driven: `LLM_PROVIDER`, provider API keys, `DATABASE_URL`, `SECRET_KEY`,
  `CREDENTIAL_ENCRYPTION_KEY`, plan-retry count.
- No secret is logged or returned to the client.

## Acceptance Criteria

1. A user can register, log in, and only see their own connections and plans.
2. A user can create and test JIRA, GitHub, and Salesforce connections; stored secrets
   are encrypted and never returned in API responses.
3. Given a valid JIRA ticket ID, the app fetches ticket fields, GitHub repo state, and a
   Salesforce metadata snapshot (live or SFDX), and shows an editable consolidated context.
4. Generating a plan produces JSON that validates against the plan schema and satisfies
   all business rules (≥1 Test step; production steps have sandbox counterparts; valid,
   acyclic dependencies; rollback on high-risk steps).
5. Invalid LLM output triggers auto-retry (default 2) and, if still invalid, returns a
   clear structured error rather than a malformed plan.
6. The rendered plan view displays classification, risk, ordered steps with badges,
   testing, deployment sequence, open questions, and managed-package warnings; a raw JSON
   toggle and JSON/Markdown export are available.
7. Switching `LLM_PROVIDER` between Claude and OpenAI works without code changes.
8. When no LSC guide docs are ingested, references fall back to model knowledge with
   "Verify in LSC Configuration Guide" phrasing; when docs are present, retrieved
   sections ground the references.
9. Plans persist and appear in per-user history; a plan can be re-opened and regenerated.
10. Backend has automated tests covering schema validation, business-rule enforcement,
    provider abstraction (mocked), and context assembly; tests pass in CI/local.

## Implementation Approach (ordered)

1. **Scaffold project** — backend (FastAPI app skeleton, config, Docker Compose,
   Alembic) and frontend (Vite + React + TS + Ant Design); update `.ona/automations.yaml`
   and devcontainer as needed; ensure `.gitignore` covers deps/build/env.
2. **Auth & users** — user model, register/login/JWT, password hashing, auth deps.
3. **Data model & migrations** — users, connections, plans, guide_documents (+ pgvector),
   with initial Alembic migration.
4. **Connection management** — CRUD + encrypted credentials + test-connection endpoints
   for JIRA, GitHub, Salesforce.
5. **Context connectors** — JIRA fetch, GitHub state fetch, Salesforce live metadata query
   and SFDX source parser; consolidated editable context assembly.
6. **Plan schema** — canonical JSON schema artifact + Pydantic models + business-rule
   validators.
7. **LLM provider abstraction** — provider interface, Claude and OpenAI adapters,
   env-based selection.
8. **Planning engine** — system-prompt assembly with variable injection, generation call,
   strict validation with auto-retry, persistence.
9. **LSC guide RAG** — document ingestion, embeddings in pgvector, retrieval into prompt;
   graceful fallback when empty.
10. **Frontend — auth & connections** — login/register pages, connections management UI.
11. **Frontend — context & generation** — ticket input, context review/edit, generate.
12. **Frontend — plan view & export** — rendered step cards, risk/classification, raw JSON
    toggle, JSON/Markdown export, warnings, history list.
13. **Testing** — backend unit/integration tests (schema, rules, mocked providers,
    context assembly); minimal frontend smoke tests.
14. **Docs & run** — README (setup, env vars, provider config), verify end-to-end via
    Docker Compose / preview server.

## Open Questions / Assumptions

- **PDF export** not included (JSON + Markdown only) — can add later if needed.
- **Redis/Celery**: plan generation is synchronous request/response for now; background
  queue only added if generation latency requires it.
- **pgvector** assumed available in the Postgres image; if not, RAG uses a simple
  in-table cosine fallback.
- **SFDX parsing** covers common metadata types (objects, fields, flows, classes,
  permission sets); exhaustive coverage is out of scope for v1.
