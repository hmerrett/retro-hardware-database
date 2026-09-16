# The Retro Hardware Database — how it is built

A map of the system: what exists, where it lives, and which rules hold
everywhere. Read this before changing the code; read `CLAUDE.md` for how we work
and `.claude/rules/` for the standards each area is held to.

**This document describes the code. It does not define it.** It was written by
reading the software, so it can be wrong in the way a photograph of a house can
be wrong about what the architect intended — it shows what got built. The parts
that *are* enforced say so, and the module inventory below is checked by the test
suite, so it cannot quietly come to describe modules that no longer exist. The
prose around it is ordinary documentation and carries ordinary risk.

For what the software *does*, case by case, see `docs/behaviour.md` — generated
from the test suite, so every line of it is executed by CI.

---

## 1. What this is

A self-hosted catalogue for a retro-computer collection and the workshop around
it. Every machine, expansion card, drive and chip gets an asset tag, a page,
photographs and a dated history. You print a QR label, stick it on the item, and
scanning it opens that item's page. Browsing is public; editing needs a login.

**It is a product other people run** (ADR-0011) — not a hosted service with
accounts, but something someone installs for their own collection, on their own
machine, with their own data. That was not true at the start and the code still
shows it in places; §8 lists where.

It began as one person's CSV file and grew into a web app, which is why some of
its shape is historical rather than designed. The data-entry model — the
vocabularies, the guided walk, the quick-entry shorthands — is a deliberate port
of the flat-file system that preceded it, so that years of established habits
kept working. Those habits are one collector's, which is a thing to remember when
another collector's shelf has something on it the model has no word for.

Three kinds of thing live in the register:

- **Computers** — whole machines.
- **Parts** — cards, drives, chips and everything else, each optionally linked to
  the computer it is fitted in or the part it is mounted on.
- **Projects** — the *work*, as against the things it is done to: a restoration,
  a repair, a hunt for a missing card. A project is not an object on a shelf and
  never gets a printed label, but it draws an id from the same pool (see §3).

## 2. The shape of a request

    the internet
       │
       ▼
    Caddy ...................... the only service exposed; TLS, HSTS, security
       │                         headers, automatic Let's Encrypt certificates
       ▼
    uvicorn → FastAPI ("api") .. listens on localhost only
       │
       ├── no_stale_pages ...... middleware: every HTML response gets
       │                         `Cache-Control: no-cache`, so a deployed change
       │                         is never masked by yesterday's copy in Safari.
       │                         Photographs and static files say the opposite on
       │                         purpose — they are version-stamped and cacheable
       │                         for a year.
       │
       ├── auth_gate ........... middleware: decides `request.state.authed`.
       │                         Browsers are trusted by signed session cookie
       │                         only, so logging out is reliable; `/api/*` and
       │                         `/docs` also accept HTTP Basic, for the MCP
       │                         server and the command-line tools. A wrong Basic
       │                         credential is rate-limited by client IP exactly
       │                         as the login form is.
       │
       ▼
    route handler ............. in main.py, with a per-request DB session from
       │                        db.py's `get_db` dependency
       ▼
    Jinja2 template ........... server-rendered HTML (no frontend framework), or
                                a Pydantic model rendered as JSON for `/api/*`

MariaDB and the MCP server sit alongside, also on localhost. The whole stack is
Docker Compose. **Migrations run at container start** — `entrypoint.sh` runs
`alembic upgrade head` before uvicorn — so a deploy that carries a schema change
applies it on the way up.

## 3. The register: one pool of asset ids

The single most load-bearing rule in the system.

Computers, parts and projects **share one id namespace**, allocated by
`api/app/ids.py`. Two things sharing an id would put one's history on the other's
page, because `/items/<id>` resolves to whichever kind of thing holds it and the
log is keyed by id alone.

- Historic ids are sequential (`RH-0001`); new ones are `RH-` plus four random
  characters (`RH-K7Q2`).
- The alphabet **drops I, L and O** — they are unreadable off a printed label
  next to 1 and 0, so each confusable pair keeps a single form.
- Ids are matched case-insensitively; lookups uppercase first.
- `GET /items/<id>` is the public redirect every printed QR code points at. It is
  the reason ids may never be reused or reassigned: labels already exist on
  shelves, and some of them point at a GitHub Pages site that predates this app.

## 4. The data model

`api/app/models.py` holds the ORM tables; `api/migrations/` holds the Alembic
migrations that build them. Nothing else may construct an engine.

**The two item tables.** `computers` and `parts` carry the columns every item has
— identity, manufacturer, model, year, serial, condition, source, acquisition
date, disposal. A part's `computer_id` links it to the computer it is fitted in
and `parent_id` to the part it is mounted on; both are real foreign keys and
`NULL` when the part stands alone. Deleting a computer or a host part **unlinks**
what pointed at it rather than deleting it — a card outlives the machine it came
out of.

**Typed detail hangs off a part by kind.** `motherboard_spec`, `cpu_spec`,
`ram_spec`, `video_spec`, `sound_spec`, `network_spec`, `io_spec`, `storage_spec`
and `display_spec` are one-to-one with a part and only exist for the kind they
describe. Repeating detail is a child table instead: `part_slot`, `part_ram_slot`,
`part_port`, `part_attribute`.

**A computer's fitted memory and drives are child rows too** —
`computer_ram_module`, `computer_ram_chip`, `computer_drive` — because the app
used to keep them as free text and lost data whenever a label was renamed.

**The derived-cache pattern.** This one matters when you change anything in this
area. For structured specs and for fitted RAM, **the child rows are the truth and
the old free-text column is a rendered cache of them**. `parts.specs` is
re-rendered from the typed tables whenever a part changes; `api/app/resync.py`
re-renders the lot. `specstruct.py` converts between the string and the
structure, `specdb.py` between the structure and the tables. Write to the tables
and re-render; never edit the string and hope.

**Around the items:**

| table | what it holds |
|---|---|
| `asset_variant`, `asset_chip` | which issue/style/region an asset is, and the notable chips on it |
| `log_entry`, `log_photo` | the dated history of an asset, and photographs attached to a line of it |
| `files`, `file_tag` | files kept beside the register — drivers, manuals, ROM dumps — and the names they are for |
| `projects`, `project_asset`, `project_task`, `project_order` | a piece of work, the things it is about (one project to a thing), its job list — each job optionally naming one of those things — and what is on order for it |

## 5. The modules

`api/app/main.py` is the app and its routes. It is large (4,579 lines) and is
being split a module at a time, leaning on the suite as the safety net. Everything
below it is a module with one job. `common.py` is deliberately dependency-free so
the feature modules and `main` can all import downward without a cycle.

<!-- module-inventory: kept in step with api/app/*.py by test_architecture.py -->

| module | what it owns |
|---|---|
| `main.py` | the FastAPI app, the middleware, and the routes not yet lifted out |
| `auth.py` | the login, the logout, and the gate every request passes through |
| `web.py` | the templates object and what a page needs around one: the globals, the share card, the schema.org data |
| `cards.py` | the share card for a page that is a wall of photographs: the montage of four, its content-addressed cache, the sweep |
| `routers/seo.py` | robots.txt, the sitemap, and the icons asked for at the domain root |
| `routers/gallery.py` | the wall of cards, the /browse slice of it, the owner's /for-sale shortlist, and the suggestions under the search bar |
| `routers/stats.py` | the two pages of figures: /stats and the GoAccess report at /traffic |
| `routers/catalogue.py` | the catalogue as a page and as JSON: /machines and /api/machines |
| `routers/images.py` | serving a photograph: the watermark, the narrower copy, the refusals |
| `models.py` | the ORM tables and their relationships |
| `db.py` | the engine and the per-request session — the only place either is made |
| `schemas.py` | the request and response shapes for `/api/*` |
| `ids.py` | allocating an asset id, unique across the whole register |
| `common.py` | the "still held" filter, small query helpers, the image folder, collection constants |
| `entry.py` | guided-entry vocabularies and quick-entry shorthands, ported from the flat-file system |
| `machines.py` | the catalogue of known machine models and the variations each was built in |
| `machinedb.py` | mapping an asset's catalogue identity between its rows and plain values |
| `specstruct.py` | converting between the free-text specs string and a normalised structure |
| `specdb.py` | mapping a part's structured specs between the typed tables and that structure |
| `ramdb.py` | mapping a computer's fitted memory between its child tables and plain counts |
| `drivedb.py` | a machine's fitted removable-media drives: rows in, canonical string out |
| `resync.py` | re-rendering the derived caches when something upstream changes |
| `search.py` | the term parser, the "any field" haystack, the suggestion list, the `/browse` views |
| `stats.py` | the figures and the pool of facts behind the public `/stats` page |
| `projects.py` | projects: the work, as against the things it is done to |
| `filesdb.py` | files kept beside the register and the names they are for |
| `photos.py` | watermarking, upload verification, reference photos, kept originals, crop/rotate |
| `thumbs.py` | smaller copies of the photographs, made once and kept |
| `enhance.py` | the one-touch tuneup: the automatic levels-and-colour fix a phone does |
| `enrich.py` | fetching a photo for an item from its reference URL |
| `labels.py` | print-ready label PDFs, with the QR encoding every printed label already uses |
| `audit_storage.py` | checking every storage part against the questions its kind is actually asked |

Outside `api/`:

- `api/app/templates/` — 27 Jinja2 templates. `api/app/static/` — the stylesheet
  and scripts, moved out of `base.html` so they can be cached and so a real
  Content-Security-Policy becomes possible.
- `tools/` — operator scripts with their own venv: backups, label sheets, imports,
  reports. Not imported by the app.
- `mcp/` — an MCP server, a separate compose service, so an assistant can read and
  write the register over HTTP.
- `caddy/` — the reverse proxy. `branding/` and `.env` — this installation's own
  identity and secrets, never in git.

## 6. The rules that hold everywhere

These are the invariants. Several are enforced by tests, and those are marked —
breaking one turns CI red rather than merely being wrong.

- **Public read, login to edit.** Anonymous visitors get `GET` on the gallery,
  item pages, images and static files. Everything else — new and edit forms,
  delete confirmations, labels, `/api/*`, `/docs`, and every write — requires a
  login. The rule lives in `_is_public_read` / `_public_page` in `auth.py`.
- **…unless there is no login at all, and then the app says so.** With
  `RHDB_AUTH_USER`/`RHDB_AUTH_PASSWORD` unset, every visitor is the owner. That is
  a supported configuration, but an unreadable `.env` produces it too, so it is
  announced: `RHDB_OPEN` says it was meant, and without it there is a startup
  warning and a banner on every page. *(ADR-0019, enforced: `test_running_open.py`)*
- **An asset id is never reused or reassigned.** Printed labels exist. *(§3)*
- **The child rows are the truth; the string is a cache.** *(§4)*
- **A migration must not assume specific data exists.** A one-off correction to a
  named row belongs in a `tools/` script, not in the shared history, or it breaks
  every fresh install. *(ADR-0002, enforced: CI migrates an empty database)*
- **A file is not public until it is ticked.** Unpublished files answer 404, not
  401 — there is no account a reader could hold, so a prompt would only confirm
  the file exists. *(ADR-0009)*
- **A share card is made of photographs that are already public.** The montage a
  grid page previews as is built from what an anonymous reader is shown, so a
  private project puts nothing on one, and `/og/{name}` opens a file by hash
  rather than reading a query. *(ADR-0017, enforced: `test_share_cards.py`)*
- **A column kept off the page is kept out of the search too.** `_haystack` reads
  every column off the model, so a new one joins the anonymous search by merely
  existing. Owner-only columns are the named set `OWNER_ONLY` in `common.py`, not
  a habit of remembering. *(ADR-0018, enforced: `test_for_sale.py`)*
- **The API's published shape is pinned.** `api/openapi.json` is committed and a
  change a caller could see fails the suite. *(ADR-0010, enforced)*
- **Touch controls are 16px.** iOS zooms the page when it focuses a control whose
  text is smaller, and does not zoom back out. Any rule that sizes a control must
  be restated in the `@media (pointer: coarse)` block. *(enforced:
  `test_stylesheet.py`)*
- **Action colours clear 4.5:1 in both themes**, computed from the theme
  variables. *(enforced: `test_stylesheet.py`)*
- **The suite runs on MariaDB and builds its schema from the real migrations.**
  There is no SQLite path to fall back to. *(ADR-0008)*

## 7. Where the work is

- **`main.py` is being split.** Lift cohesive non-route blocks into their own
  module, group routes into `APIRouter`s, in small independently verifiable steps.
  `stats.py`, `search.py`, `photos.py`, `common.py` and `projects.py` came out
  this way.
- **Inline CSS and JS are moving into static files.** That is what unlocks a real
  Content-Security-Policy, which is the strongest single anti-XSS control
  available here.
- **Named in the standards as *adopt next*:** `ruff format --check`, `mypy
  --strict` in CI, `uv` with a committed lockfile, SQLAlchemy 2.0 typed ORM, and
  per-environment compose overrides with a multi-stage Dockerfile.

## 8. Open questions

Things genuinely undecided, recorded here so they are not rediscovered:

- **What 0.1 means** — which of the below must be true before it is cut.
- **The specification is generated, not authored.** `api/openapi.json` is now
  pinned, so the shape cannot change silently, but the document is still a report
  of the code rather than a definition the code is built to. Now that strangers
  write against it, inverting it buys something real. *(ADR-0010, ADR-0011)*
- **The database is someone else's choice.** MariaDB-only is a sound testing
  decision for one installation and a hardware requirement for a product. No raw
  SQL exists anywhere and the ORM is used throughout, so Postgres or SQLite is
  probably close — but nothing proves it. *(ADR-0008, ADR-0011)*
- **There is one username and one password**, from the environment, with no user
  table. A workshop is often more than one person, and there is no way to add a
  second without sharing the first. Whether that becomes accounts is a question to
  answer deliberately.
- **The vocabularies are one collector's**, ported from the flat-file system.
  Another collection has things on it this model cannot name.
- **The asset-id prefix is hard-coded** to `RH-` in `ids.py`. It stands for Retro
  Hardware rather than anyone's initials, so it is not wrong for a stranger — but
  it is not theirs either.
- **Upgrades run against data nobody here has seen.** ADR-0002 already forbids a
  migration assuming specific rows; the cost of breaking that is now someone
  else's collection rather than a reimport.
- **Most tests describe rather than require.** 1,220 of them, nearly all driving
  the app through the HTTP boundary. They are a real asset and they do test
  observable behaviour — but they were written after the code, so they ratify it.
  A handful of acceptance tests stating what must always be true would change that
  where it matters, without touching the rest.
- **Eight of the 26 `/api` operations declare no response model**, so the pinned
  contract is thin exactly at the deletes and at `/api/machines`,
  `/api/items/{aid}/log` and `/api/files`.
- **There is no user table.** Authentication is one username and password from the
  environment. Fine for one person; a question the moment it is two.
- **Accessibility** is partly true by accident — contrast and touch targets are
  tested, public pages have landmarks and alt text — and is not yet a rule anyone
  is held to. For a product other people run it is an obligation rather than a
  courtesy, and it is wanted before 0.1.

## 9. Where decisions are written down

`adr/` holds the architecture decision records. Each says what was decided, what
it was weighed against, and what it costs.

| | |
|---|---|
| 0001 | Record architecture decisions |
| 0002 | Migrations must not assume specific data |
| 0003 | Work is noted at check-in |
| 0004 | Work projects are public by default |
| 0005 | The photo tuneup is conservative, and takes exactly one step back |
| 0006 | Files are linked to what they are for, not named after it |
| 0007 | The register records what is owned, not what it is made of |
| 0008 | The suite runs on MariaDB, and builds its schema from the migrations |
| 0009 | A file is published by hand |
| 0010 | The published API shape is kept in the repository |
| 0011 | The register is a product other people run |
| 0012 | Run alongside an existing reverse proxy *(proposed)* |
| 0013 | Stay server-rendered; polish comes from design, not a SPA *(proposed)* |
| 0014 | Accessibility is a tested standard, not a set of habits *(proposed)* |

A significant decision becomes an ADR rather than a commit message. A finding is
decided when it is found — fixed, raised as an issue, written up, or consciously
accepted — rather than left lying.
