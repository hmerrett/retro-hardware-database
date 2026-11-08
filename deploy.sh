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
# The image has no repository inside it, so it is told which commit it is, and the
# Settings page says so (MANUAL §19, "The version that is running").
export RHDB_COMMIT="$(git rev-parse --short HEAD)"
docker compose up -d --build

echo "==> Reloading Caddy's configuration"
# The Caddyfile is mounted rather than built in, so a change to it reaches nothing
# until Caddy reads it again. A reload is graceful and checks the file first: one
# that does not parse stops the deploy here and leaves the running one in place.
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile

echo "==> Pruning dangling images"
docker image prune -f >/dev/null || true

echo "==> Recent api logs"
docker compose logs --tail=20 api

# The domain is this installation's, and .env is where it lives.
SITE="$(grep -E '^RHDB_DOMAIN=' .env 2>/dev/null | cut -d= -f2-)"
echo "==> Done. Live at https://${SITE:-<your domain>}/"
