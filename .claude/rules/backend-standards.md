# Backend standards

Python + FastAPI, server-rendered Jinja2. British English.

## Tooling

- **Linting & formatting: ruff** (both). Config lives in `pyproject.toml`
  (`line-length = 100`, `target-version = "py312"`). Run `ruff check .` and
  `ruff format .` before committing; CI runs both, the second as
  `ruff format --check .`, so an unformatted branch fails rather than being
  argued about in review.
- **Dependencies: locked.** `api/pyproject.toml` names them with `==` pins and
  `api/uv.lock` pins the whole transitive tree behind them; CI and the Dockerfile
  both install with `uv sync --frozen`, so a build gets what was reviewed rather
  than what resolves on the day. Upgrading is deliberate: edit the list, `uv lock`,
  and let the tests and `pip-audit` vouch for it. Dependabot raises a grouped PR
  weekly.
  - Locally: `uv sync --project api --all-groups`, then `uv run --project api
    pytest`. There is no requirements.txt any more.
- **Types: mypy, strict.** Config is `[tool.mypy]` in `api/pyproject.toml`, with
  the pydantic plugin; CI runs `uv run --directory api mypy app`, and so should
  you before committing.
  - **Strict is the default, and the exceptions are a list that only shrinks.**
    The modules not yet typed are named in one override. A new module is not on
    it, so it is strict by doing nothing; a module comes off it by being typed,
    and never goes back on.
  - **The ways round it are closed.** No bare `# type: ignore` and none left
    behind once its error has gone (both configured as errors), and no `Any`
    written by hand. An ignore that has to stay names its error code and says
    why on the lines above it -- `test_type_checking.py` fails one that does
    not. The answer to "mypy is wrong here" is nearly always a more exact type:
    a `TypedDict` for a table of dicts, `object` for a value that really is
    anything, a union where two things really arrive.
  - **An annotation on a model is a schema statement.** `Mapped[str]` means NOT
    NULL; `Mapped[str | None]` is what a nullable column is (database-standards).

## Structure & conventions

- Configuration comes from the **environment** (`RHDB_*` variables), read once at
  startup. Never hard-code config or secrets. Commit `.env.example`, never `.env`.
- Handlers validate input at the boundary and raise `HTTPException` with a useful
  status — **never leak a stack trace or internal detail** to the client.
- Keep cohesive, non-route logic in its own module rather than in the route
  handler. Routes are `APIRouter`s in `api/app/routers/`, a module to a group,
  with their shared helpers in modules beside them; `main.py` is the wiring.
- **Logging:** use the stdlib `logging` module with lazy `%s` interpolation
  (`log.info("saved %s", asset_id)`), not f-strings in the log call. Never log
  credentials, cookies or the session token.
- Comments explain *why*. Match the surrounding density and idiom.
