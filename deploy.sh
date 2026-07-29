#!/usr/bin/env bash
# Deploy db.2600.me: pull the latest code and rebuild the running stack.
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

echo "==> Done. Live at https://db.2600.me/"
