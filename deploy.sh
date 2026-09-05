#!/usr/bin/env bash
# Deploy this installation: pull the latest code and rebuild the running stack.
#
# Run it on the server, from the repo root:
#     ./deploy.sh
#
# Database migrations run automatically when the api container starts
# (entrypoint.sh runs `alembic upgrade head`), so there is no separate step.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Pulling latest from origin"
git pull --ff-only

echo "==> Rebuilding and restarting containers"
docker compose up -d --build

echo "==> Pruning dangling images"
docker image prune -f >/dev/null || true

echo "==> Recent api logs"
docker compose logs --tail=20 api

# The domain is this installation's, and .env is where it lives.
SITE="$(grep -E '^RHDB_DOMAIN=' .env 2>/dev/null | cut -d= -f2-)"
echo "==> Done. Live at https://${SITE:-<your domain>}/"
