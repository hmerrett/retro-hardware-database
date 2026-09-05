# Workflow & CI

British English. Scaled for a small team / solo maintainer — light, not ceremonial.

## Branches & commits

- **Never commit straight to `main`.** Branch per change (`feat/…`, `fix/…`),
  open a PR, merge when CI is green. Squash-merge to keep history readable.
- Small, focused commits with clear, imperative messages that say *why*.
- **CI must be green before merge.**

## CI

CI (`.github/workflows/ci.yml`) runs on pull requests. The backend job shape is:

1. install dependencies (from the pinned set / lockfile),
2. `ruff check .` (and *adopt next:* `ruff format --check .`, `mypy app`),
3. **`alembic upgrade head` against a real MariaDB** (a service container) — proves
   a fresh database migrates cleanly,
4. `pytest` — the suite, on MariaDB as well as SQLite,
5. `pip-audit` against the pinned runtime dependencies.

Keep the fast SQLite unit run for quick feedback and the MariaDB run for fidelity
(testing-standards).

## Dependencies

- Pinned/locked (backend-standards). **Dependabot** (`.github/dependabot.yml`)
  raises weekly grouped update PRs; that plus `pip-audit` is how security
  advisories get noticed rather than piling up.

## Decisions & findings

- A **significant decision becomes an ADR** (`adr/`), not just a commit message.
- **Decide a finding at the moment you find it** — fix it now, raise an issue,
  write an ADR, or consciously accept it — rather than leaving it undecided. A
  `TODO`/`FIXME` should reference an issue.

## Structural work in flight

- `api/app/main.py` is a single large module holding most routes and helpers.
  The direction is to split it — lift cohesive non-route blocks (stats, photos,
  search) into their own modules and group routes into `APIRouter`s — leaning on
  the test suite as the safety net. Extract in small, independently-verifiable
  steps; don't rewrite wholesale.
- Inline CSS/JS in `base.html` is being moved into cacheable static files; that
  also unlocks a real Content-Security-Policy (security-standards).
