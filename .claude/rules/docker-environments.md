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
- Keep the build context small with a `.dockerignore` **in each build context**
  (`api/`, `mcp/`, `backup/`): Docker reads the one at the root of the context and
  no other, and no build here starts at the repository's root, so a root one would
  do nothing. A context that holds only a script or two names what it sends (`*`,
  then `!` the files the Dockerfile copies) rather than what it leaves out --
  `backup/` is where the off-site copy runs, beside its `.env`, its key and the
  restic repository. The suite checks both.

## Environments

- `docker-compose.yml` — the whole stack, and what production runs: every service
  `restart: unless-stopped`, the app as a non-root user, the database behind a
  healthcheck the app waits on (`condition: service_healthy`).
- `docker-compose.dev.yml` — layered on top for local work: the source
  bind-mounted over the image and `--reload`, watching the code directory only.
- **A production override is the installation's, not the project's.** Where an
  installation runs images from a registry of its own, pins a project name, or
  otherwise differs, that belongs in a file it keeps beside its `.env`, not here.
  The project ships what every install shares — which now includes the images.

## Published images

- **A release publishes the two images built here** (ADR-0041): pushing a tag
  `vX.Y.Z` runs `.github/workflows/publish.yml`, which builds `api` and `mcp` on
  amd64 and arm64 runners and pushes them to
  `ghcr.io/hmerrett/retro-hardware-database/{api,mcp}` as `X.Y.Z` and `X.Y`. Never
  `latest`: like every other image in the compose file, it changes when an
  installation says so.
- **Compose names them beside the builds.** `api`, `api-init` and `mcp` each have an
  `image:` tagged `${RHDB_VERSION:-X.Y.Z}`, the default being the release the
  checkout belongs to — the suite holds it to `__version__` — and a `build:`. So
  `docker compose pull` fetches the release's images, and `docker compose up -d
  --build` (and `deploy.sh`) makes the same images from the checkout under the same
  names. An installation does one or the other: the image a release published is
  older than the code a build after it was made from.
- **Nothing installation-specific goes into an image.** One image serves every
  installation, so configuration stays in the environment and branding and the
  Caddyfile stay mounted. The one thing a build is told is the commit it was made
  from (`RHDB_COMMIT`), which is the same for everyone who pulls it.

## The app runs as `appuser`, not root

- The image ends `USER appuser` (uid 10001). It owns `/app/images` and
  `/app/files`, the two places it writes, and nothing else — the code stays root's.
- `api-init` runs `fix-volumes.sh` as root before the app starts, giving those two
  volumes to appuser if anything in them is not. A fresh install never needs it;
  an install from before the change, or a restore done as root, does. It looks
  before it changes anything.
- The MCP server's image ends `USER appuser` too, with the same fixed uid. It
  writes nothing, so it owns nothing: all of its image is root's.
- Anything that writes into a volume from outside the app — a restore, a one-off
  script through `docker compose exec` — runs as appuser by default, which is
  what keeps the volumes consistent between `api-init` runs.

## Each image is built in two stages

The first installs the dependency tree from its `uv.lock` alone (`api/uv.lock`,
`mcp/uv.lock`); the second copies the virtual environment out of it and adds the
code. So the expensive layer is rebuilt when the lockfile changes and not when a
template does, neither uv nor a compiler is in an image that is published, and
two builds of one tag hold the same dependencies.
