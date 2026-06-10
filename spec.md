# Migration Bridge: IQVIA OCEP → Veeva Vault CRM Migration Utility

## Problem Statement

Roche is migrating from IQVIA OCEP (built on Salesforce Sales Cloud) to Veeva Vault CRM (Vault-native platform). These are two fundamentally different systems with different data models, APIs, and object structures. The migration team needs a utility that can:

1. **Connect to both systems** and introspect their schemas.
2. **Auto-discover and map** the data models between source (Salesforce) and target (Veeva Vault).
3. **Validate migrated data** with full record-by-record comparison, identifying what's missing or mismatched from source to target.

The data volume exceeds 10M records, requiring a streaming/batch architecture. The tool runs on the Ona platform within the Roche environment and supports multiple concurrent users.

---

## System Context

### Source: IQVIA OCEP on Salesforce Sales Cloud
- **Platform**: Salesforce (standard + custom objects with IQVIA managed package)
- **APIs**: Salesforce REST API, SOAP API, Bulk API 2.0
- **Authentication**: OAuth 2.0 (Web Server flow, Username-Password flow), or API credentials (username + password + security token)
- **Key object categories**: Accounts, Contacts, Users, Territories, Products, Calls/Activities, Samples, Custom OCEP objects (prefixed with `OCEP__` or IQVIA namespace)
- **Metadata API**: Salesforce Metadata API / Describe calls for schema introspection

### Target: Veeva Vault CRM (Vault-Native)
- **Platform**: Veeva Vault (not Salesforce-based)
- **APIs**: Veeva Vault REST API (v24.x+)
- **Authentication**: Vault API username/password auth, OAuth 2.0 / SAML SSO
- **Key object categories**: Vault Objects (Account, Address, Call, Product, Territory, User, etc.), Vault Documents
- **Metadata API**: Vault Metadata API (`/api/v24.3/metadata/vobjects/`) for schema introspection

### Key Differences
| Aspect | Salesforce (IQVIA OCEP) | Veeva Vault CRM |
|---|---|---|
| Object model | SObjects (standard + custom) | Vault Objects (vObjects) |
| Field types | Salesforce field types | Vault field types (may differ) |
| Relationships | Lookup, Master-Detail | Vault object references |
| IDs | 18-char Salesforce ID | Vault record ID (different format) |
| API style | REST/SOAP/Bulk | Vault REST API |
| Namespacing | IQVIA managed package namespace | Veeva CRM namespace |

---

## Requirements

### R1: Connection Management
- **R1.1**: Support connecting to Salesforce orgs (IQVIA OCEP) via:
  - API credentials (username + password + security token + consumer key/secret)
  - OAuth 2.0 browser-based login flow
- **R1.2**: Support connecting to Veeva Vault CRM via:
  - API credentials (username + password + vault DNS)
  - OAuth 2.0 / SSO flow
- **R1.3**: Support multiple connection profiles (named connections).
- **R1.4**: Environment selector — each connection profile is tagged as `sandbox` or `production`.
- **R1.5**: Credentials stored securely (encrypted at rest, never logged).
- **R1.6**: Connection health check / test connectivity button.

### R2: Schema Discovery & Data Model Mapping
- **R2.1**: Auto-discover all objects and fields from the Salesforce org via Describe/Metadata API.
- **R2.2**: Auto-discover all Vault Objects and fields from Veeva Vault via Vault Metadata API.
- **R2.3**: User selects which objects are in scope for a given migration run (configurable per run).
- **R2.4**: Auto-suggest field-level mappings between source and target based on:
  - Field name similarity (fuzzy matching)
  - Field type compatibility
  - Field label matching
- **R2.5**: Display source and target schemas side-by-side in the web UI.
- **R2.6**: Allow manual override/correction of auto-suggested mappings.
- **R2.7**: Support mapping transformations (e.g., picklist value mapping, date format conversion, field concatenation/splitting).
- **R2.8**: Persist mapping configurations in the database for reuse across runs.
- **R2.9**: Export mapping definitions as CSV/Excel.
- **R2.10**: Import mapping definitions from CSV/Excel (to seed or override).
- **R2.11**: Flag unmapped source fields and unmapped target fields as warnings.

### R3: Data Validation (Migration Verification)
- **R3.1**: Configurable match keys — user defines which field(s) to use as the record matching key per object (e.g., `External_ID__c` ↔ `external_id__v`).
- **R3.2**: **Record count comparison** — compare total record counts per object between source and target.
- **R3.3**: **Full record-by-record diff** — for each mapped object:
  - Fetch all records from source and target (using Bulk API for Salesforce, paginated API for Vault).
  - Match records using configured match keys.
  - Compare every mapped field value.
  - Categorize results:
    - **Missing in target**: Records in source but not in target.
    - **Missing in source**: Records in target but not in source (unexpected).
    - **Matched with differences**: Records found in both but with field-level mismatches.
    - **Fully matched**: Records identical across all mapped fields.
- **R3.4**: **Execution modes**:
  - **Real-time (on-demand)**: For small objects (<100K records), run inline and show results immediately.
  - **Background batch**: For large objects, queue as a background job. User can check progress and results later.
  - Auto-select mode based on estimated record count, with manual override.
- **R3.5**: Support incremental validation — re-run validation for specific objects or subsets without re-validating everything.
- **R3.6**: Handle data type differences gracefully (e.g., date format normalization, whitespace trimming, case-insensitive comparison for text fields).

### R4: Reporting & Dashboard
- **R4.1**: **Web dashboard** showing:
  - Migration overview: per-object status (count match %, record match %, field match %).
  - Drill-down: click an object to see record-level details.
  - Drill-down: click a record to see field-level diff.
  - Validation run history with timestamps and status.
- **R4.2**: **Export reports** as CSV and Excel:
  - Summary report (object-level counts and match rates).
  - Detail report (record-level mismatches with field values from both systems).
  - Missing records report (records in source not found in target).
  - Unmapped fields report.
- **R4.3**: Filter and search within validation results (by object, status, mismatch type).
- **R4.4**: Progress indicator for running batch validation jobs.

### R5: Multi-User & Sessions
- **R5.1**: Multiple users can access the tool simultaneously with independent sessions.
- **R5.2**: Each user has their own connection profiles and validation runs.
- **R5.3**: Simple authentication (username/password or SSO via Roche identity, depending on infra).
- **R5.4**: Shared mapping configurations — mappings can be shared across users within the same project.

### R6: Deployment & Infrastructure
- **R6.1**: Runs on the Ona platform within the Roche environment.
- **R6.2**: Dockerized deployment (Python backend + web frontend).
- **R6.3**: PostgreSQL database for persistence (connection profiles, mappings, validation results, run history).
- **R6.4**: Background job processing for batch validation (Celery + Redis or similar).

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Web UI (React)                     │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │Connection│ │Schema Mapping│ │Validation Dashboard│ │
│  │ Manager  │ │   Editor     │ │  & Reports        │ │
│  └──────────┘ └──────────────┘ └──────────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────┐
│              Python Backend (FastAPI)                 │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────┐ │
│  │ Connectors │ │  Mapping   │ │   Validation     │ │
│  │ SF + Vault │ │  Engine    │ │   Engine         │ │
│  └─────┬──────┘ └────────────┘ └────────┬─────────┘ │
│        │                                │            │
│  ┌─────▼──────────────────────────────  ▼─────────┐ │
│  │         Background Job Worker (Celery)          │ │
│  └─────────────────────────────────────────────────┘ │
└──────────┬──────────────────────────────┬────────────┘
           │                              │
    ┌──────▼──────┐                ┌──────▼──────┐
    │ PostgreSQL  │                │    Redis     │
    │ (persistence)│               │ (job queue)  │
    └─────────────┘                └─────────────┘
           │                              │
    ┌──────▼──────┐                ┌──────▼──────┐
    │ Salesforce  │                │ Veeva Vault  │
    │ (IQVIA OCEP)│               │    CRM       │
    └─────────────┘                └─────────────┘
```

### Tech Stack
| Layer | Technology |
|---|---|
| Frontend | React + TypeScript, Ant Design or Material UI |
| Backend | Python 3.12+, FastAPI |
| Database | PostgreSQL 16 |
| Job Queue | Celery + Redis |
| Salesforce SDK | `simple-salesforce` (REST/Bulk API) |
| Veeva Vault SDK | Custom REST client (Vault API) — no official Python SDK |
| Auth | JWT-based sessions |
| Deployment | Docker Compose (Ona platform) |

---

## Data Model (Internal Database)

### Core Tables
- **users** — user accounts and auth info
- **connection_profiles** — named connections to SF/Vault orgs (encrypted credentials, environment tag)
- **migration_projects** — groups connections + mappings + validation runs
- **object_mappings** — source object ↔ target object mapping
- **field_mappings** — source field ↔ target field mapping (per object mapping), includes transformation rules
- **match_key_configs** — which fields to use as match keys per object
- **validation_runs** — execution metadata (start time, status, mode, user)
- **validation_results_summary** — per-object counts (source count, target count, matched, mismatched, missing)
- **validation_results_detail** — record-level diffs (match key value, field, source value, target value, status)

---

## Acceptance Criteria

### AC1: Connection Management
- [ ] User can create, edit, delete connection profiles for both Salesforce and Veeva Vault.
- [ ] User can authenticate via API credentials or OAuth for both systems.
- [ ] User can tag connections as sandbox or production.
- [ ] "Test Connection" button verifies connectivity and shows success/failure.
- [ ] Credentials are encrypted at rest in the database.

### AC2: Schema Discovery
- [ ] Tool retrieves all objects and fields from a connected Salesforce org.
- [ ] Tool retrieves all Vault Objects and fields from a connected Veeva Vault.
- [ ] User can select/deselect objects for the migration scope.
- [ ] Schema data is cached and refreshable on demand.

### AC3: Data Model Mapping
- [ ] Tool auto-suggests field mappings based on name similarity and type compatibility.
- [ ] User can view source and target schemas side-by-side.
- [ ] User can manually create, edit, and delete field mappings.
- [ ] User can define transformation rules for mapped fields.
- [ ] Unmapped fields are flagged with warnings.
- [ ] Mappings can be exported to and imported from CSV/Excel.
- [ ] Mappings persist across sessions.

### AC4: Data Validation
- [ ] User can configure match keys per object.
- [ ] Record count comparison runs and displays results per object.
- [ ] Full record-by-record diff executes for selected objects.
- [ ] Results categorize records as: missing in target, missing in source, matched with diffs, fully matched.
- [ ] Small objects (<100K records) validate in real-time with results shown inline.
- [ ] Large objects run as background batch jobs with progress tracking.
- [ ] Validation handles >10M records without memory exhaustion (streaming/chunked processing).
- [ ] Data type differences (dates, whitespace, case) are normalized before comparison.

### AC5: Reporting
- [ ] Dashboard shows per-object migration status with match percentages.
- [ ] User can drill down from object → records → field-level diffs.
- [ ] Reports exportable as CSV and Excel.
- [ ] Validation run history is preserved and browsable.
- [ ] Results are filterable by object, status, and mismatch type.

### AC6: Multi-User & Deployment
- [ ] Multiple users can log in and work independently.
- [ ] Application runs as Docker containers on the Ona platform.
- [ ] PostgreSQL and Redis are provisioned as services.

---

## Implementation Approach (Ordered Steps)

### Phase 1: Project Scaffolding & Infrastructure
1. Initialize Python backend project (FastAPI) with project structure.
2. Initialize React frontend project (TypeScript + component library).
3. Set up Docker Compose with PostgreSQL, Redis, FastAPI, Celery worker, and React dev server.
4. Configure devcontainer.json and Ona automations for the development environment.
5. Set up database migrations (Alembic) and create core tables.

### Phase 2: Connection Management
6. Build Salesforce connector module (simple-salesforce) — auth, describe, query, bulk query.
7. Build Veeva Vault connector module (custom REST client) — auth, metadata, query.
8. Build connection profile CRUD API endpoints.
9. Build connection management UI (create/edit/delete profiles, test connection, environment selector).

### Phase 3: Schema Discovery & Mapping
10. Implement Salesforce schema introspection (list objects, describe fields).
11. Implement Veeva Vault schema introspection (Vault Metadata API).
12. Build auto-mapping engine (fuzzy name matching, type compatibility scoring).
13. Build mapping CRUD API endpoints (object mappings, field mappings, transformations).
14. Build mapping editor UI (side-by-side schema view, drag-and-drop or select mapping, transformation rules).
15. Implement mapping import/export (CSV/Excel).

### Phase 4: Data Validation Engine
16. Build record extraction pipeline — Salesforce Bulk API 2.0 for source, Vault API pagination for target.
17. Implement streaming record comparison engine (chunked processing, match key lookup).
18. Build validation orchestrator — auto-select real-time vs batch mode based on record count.
19. Integrate Celery for background batch validation jobs.
20. Build validation API endpoints (trigger run, check status, get results).
21. Store validation results in PostgreSQL (summary + detail tables).

### Phase 5: Dashboard & Reporting
22. Build validation dashboard UI (overview, drill-down, progress tracking).
23. Build report export functionality (CSV/Excel generation).
24. Build validation history and run comparison views.

### Phase 6: Multi-User & Auth
25. Implement user authentication (JWT-based login).
26. Add per-user session isolation (connection profiles, validation runs).
27. Add shared mapping configurations within projects.

### Phase 7: Hardening & Deployment
28. Add credential encryption (Fernet or similar).
29. Add error handling, retry logic, and API rate limit management for both SF and Vault APIs.
30. Write integration tests with mock API responses.
31. Finalize Docker Compose for production-like deployment on Ona.
32. Write user documentation / README.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Salesforce API rate limits (daily API call limits) | Use Bulk API 2.0 for large extractions; implement rate limit tracking and backoff |
| Veeva Vault API rate limits | Implement request throttling; use burst headers from Vault API responses |
| >10M record comparison memory pressure | Stream records in chunks; use database-backed comparison (load into temp tables, SQL diff) |
| Field type mismatches between platforms | Build a type compatibility matrix; normalize values before comparison |
| No official Veeva Vault Python SDK | Build a thin REST client wrapper; version-pin Vault API version |
| Credential security | Encrypt at rest with Fernet; never log credentials; use environment variables for encryption keys |

---

## Out of Scope (v1)
- Actual data migration / ETL (this tool validates, it does not move data).
- Veeva Vault Document migration (only Vault Object records).
- Real-time sync or CDC (Change Data Capture) between systems.
- Automated remediation of mismatches (tool reports, human fixes).
