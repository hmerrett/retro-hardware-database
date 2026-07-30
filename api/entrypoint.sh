#!/bin/sh
# Bring the schema to head, then start the app.
set -e

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
