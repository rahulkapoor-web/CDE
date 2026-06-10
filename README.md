# Migration Bridge

Data model mapping and migration validation utility for IQVIA OCEP (Salesforce) → Veeva Vault CRM migrations.

## What it does

1. **Connects** to both Salesforce (IQVIA OCEP) and Veeva Vault CRM via their respective APIs
2. **Discovers schemas** and auto-suggests field-level mappings between source and target
3. **Validates migrated data** with full record-by-record comparison, reporting what's missing or mismatched

## Architecture

- **Backend**: Python 3.12 / FastAPI
- **Frontend**: React 18 / TypeScript / Ant Design
- **Database**: PostgreSQL 16 (mappings, results, user sessions)
- **Job Queue**: Celery + Redis (background batch validation for large datasets)
- **Connectors**: `simple-salesforce` for Salesforce, custom REST client for Veeva Vault API

## Quick Start

### With Docker Compose

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Requires PostgreSQL and Redis running locally (or via `docker compose up db redis`).

## Configuration

Environment variables (set in `.env` or Docker Compose):

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@db:5432/migration_bridge` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `SECRET_KEY` | JWT signing key | `dev-secret-change-in-production` |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for encrypting stored credentials | dev key |

## Usage

1. **Register/Login** — create an account
2. **Add Connections** — configure Salesforce and Veeva Vault connection profiles
3. **Create a Project** — link a source (Salesforce) and target (Vault) connection
4. **Map Objects** — select which objects to map, use auto-mapping for field suggestions
5. **Configure Match Keys** — define how records are matched between systems
6. **Run Validation** — execute record-by-record comparison
7. **Review Results** — drill down from object → record → field-level diffs
8. **Export Reports** — download CSV/Excel reports of mismatches and missing records
