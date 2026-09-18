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
2. `uv run --project api ruff check .` and `ruff format --check .` (and
   *adopt next:* `mypy app`),
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

- Locked (backend-standards). **Dependabot** (`.github/dependabot.yml`) raises
  weekly grouped PRs for the lockfile, the base images and the actions CI runs;
  that plus `pip-audit` is how security advisories get noticed rather than piling
  up.

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
- Inline CSS/JS has moved out of `base.html` into cacheable static files, and the
  Content-Security-Policy that unlocked is sent by the app (ADR-0021,
  security-standards). What is left of that thread is the 69 inline `style`
  attributes, which keep `'unsafe-inline'` on `style-src` until they go.
