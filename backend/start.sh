#!/usr/bin/env bash
set -e

# Apply migrations then start the API.
alembic upgrade head || echo "alembic upgrade failed (continuing)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
