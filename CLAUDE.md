# Retro Hardware Database — project guide for Claude

This file is loaded automatically. Read it first, then the rule files under
`.claude/rules/` when a task touches their area. British English throughout.

## What this is

A self-hosted catalogue for a retro-computer collection. Every machine, card,
drive and chip gets an asset tag, a page, photographs and a dated history; you
print a QR label and scanning it opens the item's page. Browsing is public;
editing needs a login. Live at db.2600.me.

## Stack

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic. Server-rendered **Jinja2**
  templates with a little plain JavaScript — **no frontend framework**. Do not
  introduce React/SPA tooling without an ADR; server-rendering is a deliberate
  choice (public, crawlable item pages).
- **Database:** MariaDB in production and Docker. The test suite can also run on
  SQLite for speed (see testing-standards).
- **Delivery:** Docker Compose — Caddy (reverse proxy, automatic HTTPS) in front;
  the app, database and MCP server listen on localhost and are reached through it.

## Where things live

- `api/app/main.py` — the app and its routes *(large; being split — see
  workflow-and-ci)*.
- `api/app/models.py` — SQLAlchemy models. `api/app/db.py` — engine/session.
- `api/app/machines.yaml` — the machine catalogue (validated, self-documenting;
  add machines here with a text editor).
- `api/migrations/` — Alembic migrations. `api/tests/` — the test suite.
- `docker-compose.yml`, `caddy/Caddyfile` — the stack.
- `.claude/rules/` — the standards below. `adr/` — architecture decision records.

## How we work

- **Discuss the approach before writing code.** Ask when scope is ambiguous.
- **British English** in code, comments, docs and UI.
- **Every change is tested.** Prefer test-first: write a test that fails before
  the change and passes after, and keep the whole suite green (testing-standards).
- **Comments explain *why*, not *what*** — this codebase does that well; match it.
- **Significant decisions become ADRs** (`adr/`), not just commit messages.
- **Config comes from the environment**, never hard-coded; secrets never committed
  (`.env` is gitignored, `.env.example` is committed).

## The standards (read the file when the task touches it)

- `.claude/rules/backend-standards.md` — Python/FastAPI conventions, tooling.
- `.claude/rules/database-standards.md` — models, sessions, **Alembic migrations**.
- `.claude/rules/testing-standards.md` — how the suite runs; SQLite vs MariaDB.
- `.claude/rules/workflow-and-ci.md` — branches, commits, CI, dependencies.
- `.claude/rules/docker-environments.md` — Compose, environments, secrets.
- `.claude/rules/security-standards.md` — the security rules this app holds to.

If a rule here and a rule file ever disagree, the specific rule file wins; if
both are silent, ask.
