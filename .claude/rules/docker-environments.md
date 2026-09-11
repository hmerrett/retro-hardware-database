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

## Environments

- `docker-compose.yml` — the whole stack, and what production runs: every service
  `restart: unless-stopped`, the app as a non-root user, the database behind a
  healthcheck the app waits on (`condition: service_healthy`).
- `docker-compose.dev.yml` — layered on top for local work: the source
  bind-mounted over the image and `--reload`, watching the code directory only.
- **A production override is the installation's, not the project's.** Where an
  installation runs prebuilt images from its own registry, pins a project name, or
  otherwise differs, that belongs in a file it keeps beside its `.env`, not here.
  The project ships what every install shares.

## The app runs as `appuser`, not root

- The image ends `USER appuser` (uid 10001). It owns `/app/images` and
  `/app/files`, the two places it writes, and nothing else — the code stays root's.
- `api-init` runs `fix-volumes.sh` as root before the app starts, giving those two
  volumes to appuser if anything in them is not. A fresh install never needs it;
  an install from before the change, or a restore done as root, does. It looks
  before it changes anything.
- Anything that writes into a volume from outside the app — a restore, a one-off
  script through `docker compose exec` — runs as appuser by default, which is
  what keeps the volumes consistent between `api-init` runs.

## Adopt next

A **multi-stage Dockerfile** with deps-before-source layering, alongside the move
to uv and a lockfile (backend-standards), so the dependency layer is built from the
lockfile and cached independently of the code.
