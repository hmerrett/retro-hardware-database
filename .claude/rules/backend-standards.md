# Backend standards

Python + FastAPI, server-rendered Jinja2. British English.

## Tooling

- **Linting & formatting: ruff** (both). Config lives in `pyproject.toml`
  (`line-length = 100`, `target-version = "py312"`). Run `ruff check .` before
  committing.
  - *Adopt next:* also enforce `ruff format` (drop any hand-formatting debates) —
    add `ruff format --check .` to the pre-commit hook and CI.
- **Dependencies: pinned to exact versions.** `api/requirements.txt` uses `==`
  pins, not `>=` floors, so builds are reproducible. Upgrading is deliberate:
  bump a pin, run the tests and `pip-audit`.
  - *Adopt next:* move to **uv** with a committed `uv.lock` and `uv sync --frozen`
    in CI and Docker. This pins the full transitive tree (not just direct deps)
    and is faster. This is the target dependency workflow.
- *Adopt next:* **mypy `--strict`** with the pydantic plugin, run in CI
  (`mypy app`). Type the code as you touch it.

## Structure & conventions

- Configuration comes from the **environment** (`RHDB_*` variables), read once at
  startup. Never hard-code config or secrets. Commit `.env.example`, never `.env`.
- Handlers validate input at the boundary and raise `HTTPException` with a useful
  status — **never leak a stack trace or internal detail** to the client.
- Keep cohesive, non-route logic in its own module rather than in the route
  handler (see workflow-and-ci on splitting `main.py`).
- **Logging:** use the stdlib `logging` module with lazy `%s` interpolation
  (`log.info("saved %s", asset_id)`), not f-strings in the log call. Never log
  credentials, cookies or the session token.
- Comments explain *why*. Match the surrounding density and idiom.
