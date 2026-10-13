# Two stages, as the app's image is built: the first installs the dependency tree
# from the lockfile alone, and the second copies the virtual environment out of it
# and adds the server. So the tree is what uv.lock says and nothing that resolved on
# the day, every build of a release holds the same code (ADR-0041), and uv is not in
# the image that runs.
FROM python:3.14-slim AS deps
# Pinned, as the app's build pins it.
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --frozen: the lockfile as committed, or fail. The server is a script rather than a
# package, so there is no project to install.
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim
WORKDIR /app

# Its own unprivileged user, as the app has: the server handles what an agent sends
# it and holds the API token, and as root it would own its container outright. The
# uid is fixed, as api's is, so it means the same thing from one build to the next.
# It writes nothing, so nothing here is given to it; the code stays root's.
RUN groupadd --gid 10001 --system appuser \
    && useradd --uid 10001 --gid 10001 --system --no-create-home \
       --shell /usr/sbin/nologin appuser

# The virtual environment and nothing that built it. On PATH, so `python` is the
# locked one.
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY server.py .

USER appuser
EXPOSE 8001
CMD ["python", "server.py"]
