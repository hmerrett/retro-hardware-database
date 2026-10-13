# Workflow & CI

British English. Scaled for a small team / solo maintainer — light, not ceremonial.

## Branches & commits

- **Never commit straight to `main`.** Branch per change (`feat/…`, `fix/…`),
  open a PR, merge when CI is green. Squash-merge to keep history readable.
- Small, focused commits with clear, imperative messages that say *why*.
- **CI must be green before merge.**

## CI

CI (`.github/workflows/ci.yml`) runs on pull requests. The backend job shape is:

1. `uv sync --project api --all-groups --frozen` (the lockfile as committed),
2. `uv run --project api ruff check .`, `ruff format --check .`, and
   `uv run --directory api mypy app` -- strict, on every module (backend-standards),
3. `pytest` against a **real MariaDB service container** — the suite builds its
   schema by running the migrations from empty, so this covers both the migration
   path and the tests (ADR-0008),
4. `pip-audit` against the runtime half of the lock, exported with `uv export
   --no-dev` -- the whole transitive tree rather than the names in pyproject.toml.

There is no SQLite run: the suite is MariaDB-only, for fidelity, and the
migrations are exercised on every run rather than in a step of their own
(testing-standards).

**The API's published shape is pinned** in `api/openapi.json` and checked by the
suite (ADR-0010). A change a caller could see fails that test; record an intended
one with `RHDB_UPDATE_OPENAPI=1 pytest api/tests/test_openapi_contract.py` and the
diff of the file is the change being asked for.

## Dependencies

- Locked (backend-standards): the app's in `api/uv.lock`, the tool server's in
  `mcp/uv.lock`. **Dependabot** (`.github/dependabot.yml`) raises weekly grouped
  PRs for both lockfiles, the base images and the actions CI and a release run;
  that plus `pip-audit`, which CI runs over both, is how security advisories get
  noticed rather than piling up.

## Releases

A release is a tag, `vX.Y.Z`, on a commit of `main`. Pushing it runs
`.github/workflows/publish.yml`, which builds the app's and the tool server's
images on amd64 and arm64 runners and publishes them to
`ghcr.io/hmerrett/retro-hardware-database/{api,mcp}` as `X.Y.Z` and `X.Y`
(ADR-0041). It refuses a tag that is not the release the code names.

1. **A pull request makes the release**: `__version__` in `api/app/__init__.py`
   moves to `X.Y.Z`, the image tags in `docker-compose.yml` move with it (the suite
   fails until they do), and the CHANGELOG's *Unreleased* becomes `## X.Y.Z`.
2. **Merge it, then tag the merge commit** `vX.Y.Z` and push the tag.

Nothing about the packages is set by hand. The first publish, `v0.2.0-rc.1`, created
both public and linked to this repository, so a release is the tag and nothing else.

A release candidate is tagged `vX.Y.Z-rc.N` on a commit whose `__version__` is
already `X.Y.Z`, and is published under that tag alone. A pull request that changes
a Dockerfile or a lockfile runs the same workflow to build both images on both
architectures, and pushes nothing. Its actions are pinned to commits, because it can
publish under the project's name; Dependabot moves the pins.

## Decisions & findings

- A **significant decision becomes an ADR** (`adr/`), not just a commit message.
- **Decide a finding at the moment you find it** — fix it now, raise an issue,
  write an ADR, or consciously accept it — rather than leaving it undecided. A
  `TODO`/`FIXME` should reference an issue.

## Structural work in flight

- The split of `api/app/main.py` is finished (#66-#70): it is `create_app()`
  and nothing else, the routes are `APIRouter`s in `api/app/routers/` and the
  helpers they share are modules beside them. The habit it was done by still
  holds for the next one — lift cohesive non-route blocks out in small,
  independently-verifiable steps, leaning on the suite, rather than rewriting
  wholesale.
- Inline CSS/JS has moved out of `base.html` into cacheable static files, the
  Content-Security-Policy that unlocked is sent by the app, and the style
  attributes that kept `'unsafe-inline'` on `style-src` have gone with it — the
  policy is `'self'` throughout and the suite holds the markup to it (ADR-0021,
  ADR-0022, security-standards).
