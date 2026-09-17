# Backend standards

Python + FastAPI, server-rendered Jinja2. British English.

## Tooling

- **Linting & formatting: ruff** (both). Config lives in `pyproject.toml`
  (`line-length = 100`, `target-version = "py312"`). Run `ruff check .` before
  committing.
  - *Adopt next:* also enforce `ruff format` (drop any hand-formatting debates) —
    add `ruff format --check .` to the pre-commit hook and CI.
- **Dependencies: locked.** `api/pyproject.toml` names them with `==` pins and
  `api/uv.lock` pins the whole transitive tree behind them; CI and the Dockerfile
  both install with `uv sync --frozen`, so a build gets what was reviewed rather
  than what resolves on the day. Upgrading is deliberate: edit the list, `uv lock`,
  and let the tests and `pip-audit` vouch for it. Dependabot raises a grouped PR
  weekly.
  - Locally: `uv sync --project api --all-groups`, then `uv run --project api
    pytest`. There is no requirements.txt any more.
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
