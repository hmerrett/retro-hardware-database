# Docker & environments

Compose V2, Docker Engine. British English.

## Shape

- The stack is Docker Compose: **Caddy** (reverse proxy, automatic HTTPS) is the
  only service exposed to the internet; the app, MariaDB and MCP server listen on
  localhost and are reached through Caddy.
- Migrations run on container start (`entrypoint.sh`: `alembic upgrade head` then
  uvicorn).

## Secrets & config

- **No secrets in the image or in git.** Config comes from the environment;
  Compose reads a gitignored root `.env`; only `.env.example` is committed.
- **Required secrets fail fast.** Use `${VAR:?message}` in compose so a missing
  value stops the stack with a clear message rather than falling back to a default
  — the database passwords already do this. Never ship a default password.
- Keep the build context small with `.dockerignore` (exclude `.env`, `.venv`,
  `.git`).

## Adopt next: environment separation

Currently one `docker-compose.yml`. The target is a **base + per-environment
override** pattern:

- `docker-compose.yml` — shared service definitions.
- `docker-compose.dev.yml` — source bind-mounts + `--reload` for local work.
- `docker-compose.prod.yml` — no reload, `restart: unless-stopped`, non-root user.

with a **multi-stage Dockerfile** (`dev`/`prod` targets), deps-before-source layer
ordering, and a healthcheck on the database that `depends_on: condition:
service_healthy` waits for.
