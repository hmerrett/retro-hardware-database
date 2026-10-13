# 0041 — A release publishes its images, and an installation pulls them

**Status:** Accepted
**Date:** 2026-10-13

## Context

Every installation built the app's image and the tool server's on its own machine,
the first time and at every upgrade. On a Synology or a Raspberry Pi that build is
the slowest part of setting up, and it was raised on Discord (#179): publish what
the project builds, so that people can pull it.

Two images are built from this repository: `api`, from `api/`, which `api-init`
also runs, and `mcp`, from `mcp/`. Everything else in the stack is somebody else's
image already. Nothing about an installation is baked into either: its
configuration is the environment, and its branding and its Caddyfile are mounted.
One image can serve every installation.

docker-environments said the opposite: an installation that ran prebuilt images
from a registry kept that in an override of its own, and the project shipped only
what every installation shares. Published images are now something every
installation shares.

The tool server's dependencies floated (`mcp>=2,<3`, `httpx>=0.27`), so two builds
of one tag could hold different code. The app's had been locked since #72.

## Decision

**Pushing a tag `vX.Y.Z` publishes both images**, to
`ghcr.io/hmerrett/retro-hardware-database/api` and `.../mcp`, for `linux/amd64` and
`linux/arm64`, tagged `X.Y.Z` and `X.Y`. There is no `latest`: as with the
database, the proxy and GoAccess, an image changes when an installation says so.
Each architecture is built on a runner of its own rather than under emulation, and
the two are joined under the release's tags. A release candidate, `vX.Y.Z-rc.N`,
is published under its own tag alone.

**The tag has to be the release the code names.** The workflow refuses a tag that
is not `__version__` in `api/app/__init__.py`. The Settings page reports that
number (MANUAL §19), and an image published as one release that calls itself
another would mislead the administrator reading it.

**`docker-compose.yml` names the published images**, beside the builds it already
had: `image:` on `api`, `api-init` and `mcp`, tagged `${RHDB_VERSION:-X.Y.Z}`. The
default is the release the checkout belongs to, and the suite holds it to
`__version__`, so a checkout of a release's tag pulls that release's images.
`RHDB_VERSION` is in `.env.example`, blank, and an installation sets it only to run
another release's images. It has a default rather than failing fast because every
installation that builds from the code has an `.env` without it, and `deploy.sh`
has to keep working there unchanged. A build takes the same name, so to
`docker compose up` a build and a pull are interchangeable.

**The tool server is locked**, as the app is: `mcp/pyproject.toml` pins its two
dependencies, `mcp/uv.lock` pins the tree behind them, and its image is built in
two stages with `uv sync --frozen`. The lock resolved to exactly what the running
server already had.

The workflow's actions are pinned to commits rather than tags, because it runs with
`packages: write`: a tag moved under it would be somebody else's code publishing
under this project's name. Dependabot moves the pins, and now watches `mcp/` too.

## Consequences

- An installation from a release is `git checkout vX.Y.Z`, `docker compose pull`
  and `docker compose up -d`, and nothing is compiled on its machine. An upgrade is
  the same three steps with a newer tag.
- An installation that follows the code as it is written changes nothing.
  `deploy.sh` still builds, still tells the image its commit, and names the build
  after the release, which is the number the Settings page already shows. It must
  not also pull: the published image under that number is older than the code it
  built, and the older app stops at start against a database migrated past it.
  INSTALL.md says so.
- 32-bit ARM stays out. It never worked, because MariaDB publishes no image for it.
- A release moves the version in one more file, `docker-compose.yml`, and the suite
  fails until it does. Nothing about the packages is set by hand: the first publish,
  `v0.2.0-rc.1`, created both public and linked to this repository. This record
  first said a new package started private and would be made public once, which
  that publish showed was not so.
- The first release with images is 0.2.0. `v0.1.0` has no workflow to build it and
  no compose file that names an image, so it is not backfilled.
- Revisit if an installation needs another registry, or another architecture.
