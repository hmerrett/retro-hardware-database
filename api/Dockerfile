# Two stages, so the dependency tree is a layer of its own: it is built from the
# lockfile alone and rebuilt only when the lockfile changes, while the code above
# it changes several times a day. That is the whole reason for the split, and it
# is why it arrived with uv rather than before it (backend-standards).
FROM python:3.12-slim AS deps
# Pinned, like everything else the build depends on: a floating tag here would
# make the layer below it reproducible and the tool that built it not.
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --frozen: use the lockfile as committed and fail rather than quietly resolving
# something else. --no-dev leaves pytest and ruff out of the image; the app is not
# a package, so there is no project to install either.
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
WORKDIR /app

# The app runs as its own unprivileged user rather than as root, so a process that
# answers the public internet owns nothing it does not need. The uid and gid are
# fixed so that a volume's ownership means the same thing from one build to the next.
RUN groupadd --gid 10001 --system appuser \
    && useradd --uid 10001 --gid 10001 --system --create-home \
       --shell /usr/sbin/nologin appuser

# The virtual environment, and nothing that built it: no uv, no compiler, no wheel
# cache. Putting it on PATH is what makes `python`, `uvicorn` and `alembic` the
# locked ones for entrypoint.sh and for anything run with `docker compose exec`.
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
COPY entrypoint.sh fix-volumes.sh ./
# Only the two places the app writes are its own; the code stays root's, so the
# app cannot rewrite itself. A named volume mounted over an empty path takes that
# path's ownership from the image, which is how a fresh install's volumes come to
# belong to appuser. An install from before this has volumes that are still root's;
# the api-init service in docker-compose.yml puts those right (fix-volumes.sh).
RUN chmod +x entrypoint.sh fix-volumes.sh \
    && mkdir -p /app/images /app/files /app/stats \
    && chown appuser:appuser /app/images /app/files

USER appuser
EXPOSE 8000
CMD ["./entrypoint.sh"]
