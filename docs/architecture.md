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
       ├── content_security_policy  middleware: every response says what the
       │                         page may load, and it is all `'self'`. Outermost
       │                         of the three, so it covers the responses the gate
       │                         makes itself — a login redirect is a response too.
       │                         The app's, not Caddy's: the policy is a fact about
       │                         these templates and static files, so it lives where
       │                         a test can read it (ADR-0021). Two responses state
       │                         their own and keep it: a PDF shown in the browser
       │                         (ADR-0030), and GoAccess's traffic report, in a
       │                         sandbox (ADR-0033). A text file shown in the
       │                         browser is not one of them: it is a page of the
       │                         site, under the site's policy (ADR-0035).
       │
       ├── no_stale_pages ...... middleware: every HTML response gets
       │                         `Cache-Control: no-cache`, so a deployed change
       │                         is never masked by yesterday's copy in Safari.
       │                         Photographs and static files say the opposite on
       │                         purpose — they are version-stamped and cacheable
       │                         for a year.
       │
       ├── auth_gate ........... middleware: works out who is asking and what
       │                         their role lets them do, and sets
       │                         `request.state.principal`, `.authed` (may edit)
       │                         and `.sees_private`. Browsers are trusted by
       │                         session cookie only, so logging out is
       │                         reliable; `/api/*` and `/docs` also take a
       │                         bearer token or HTTP Basic, for the MCP server
       │                         and the command-line tools. A wrong credential
       │                         is rate-limited by client IP exactly as the
       │                         login form is. With no accounts yet, everything
       │                         goes to /setup (ADR-0032).
       │
       ▼
    route handler ............. in routers/, with a per-request DB session from
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

Computers, parts, projects and locations **share one id namespace**, allocated by
`api/app/ids.py`. Two things sharing an id would put one's history on the other's
page, because `/items/<id>` resolves to whichever kind of thing holds it and the
log is keyed by id alone. The namespace is a table, `register`, with the tag as
its primary key, so the database itself refuses a second thing with a tag already
taken (ADR-0036).

- Historic ids are sequential (`RH-0001`); new ones are `RH-` plus four random
  characters (`RH-K7Q2`).
- The alphabet **drops I, L and O** — they are unreadable off a printed label
  next to 1 and 0, so each confusable pair keeps a single form.
- Ids are matched case-insensitively; lookups uppercase first.
- `GET /items/<id>` is the public redirect every printed QR code points at. It is
  the reason ids may never be reused or reassigned: labels already exist on
  shelves, and some of them point at a GitHub Pages site that predates this app.
  A deleted thing's row stays in `register`, its `what` saying `deleted`, for that
  reason, so its tag is never issued again.
- A label's Code 128 barcode carries the id and nothing else (ADR-0034), so the id
  is the whole of what a scanner hands the app, in the audit as in the search
  box. There is no `L:`/`I:` prefix: which table holds the id is the answer to
  what kind of thing it is.

## 4. The data model

`api/app/models.py` holds the ORM tables; `api/migrations/` holds the Alembic
migrations that build them. Nothing else may construct an engine.

**The register and its tree.** `register` holds every tag in the pool, one row
for each computer, part, location and project with `what` it is, and the one link
that says where everything is: `inside_id`, the thing it is directly inside, a
real foreign key back into `register` (ADR-0036). A location is inside a location;
a machine is inside a location; a part is inside a location, a machine or another
part; a project is inside nothing. What a link means is read off what holds it:
inside a location is *kept*, inside a machine is *fitted*, inside a part is
*mounted*. The four kinds' own tables hang off `register` by `asset_id`.

**The two item tables.** `computers` and `parts` carry the columns every item has
— identity, manufacturer, model, year, serial, condition, source, acquisition
date, disposal, and `location_public`, whether a visitor is told where it is kept.
Where an item is lives in `register.inside_id` and not here. Deleting a computer or
a part deletes everything inside it; deleting a location deletes nothing inside it,
and leaves what was there inside nothing (ADR-0036).

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
| `files`, `file_tag` | files kept beside the register — drivers, manuals, ROM dumps — and the tags that say what each one is |
| `file_asset`, `file_model` | what a file is for: one unit by asset id, or every item of a model by catalogue key or by maker and model |
| `register` | every tag in the pool, its kind, and `inside_id`, what it is directly inside: the one tree that says where everything is (ADR-0036) |
| `locations` | where things are kept: a building, a room, a rack, a box, a bag, each with an id from the pool, a kind, notes and photographs. What it is inside is its `register.inside_id`, and its path is read up the tree when shown, never stored (ADR-0034, ADR-0036) |
| `moves` | each change in what a thing or a location is inside, whether kept, fitted or mounted: from, to, when, the user, and whether by edit, scan, API or undo |
| `stock_checks`, `stock_check_scans` | an audit round: the locations and machines it opened, what each was expected to hold, and every scan with what it did |
| `users`, `memberships` | who may sign in, and the role each has on a site — one site today, and the row a second collection would hang from (ADR-0032) |
| `sessions`, `api_tokens` | a signed-in browser and a program's token, each kept as a digest of the key it was handed, so either ends the moment its row goes |
| `projects`, `project_asset`, `project_task`, `project_order` | a piece of work, the things it is about (one project to a thing), its job list — each job optionally naming one of those things — and what is on order for it |

## 5. The modules

`api/app/main.py` is `create_app()`: the three middlewares, the static mount and
every router, and nothing else. The routes live in `api/app/routers/`, one module
to a group, and everything else is a module with one job. `common.py` is
deliberately dependency-free, so the rest can import downward without a cycle.

<!-- module-inventory: kept in step with api/app/*.py by test_architecture.py -->

| module | what it owns |
|---|---|
| `main.py` | create_app(): the middlewares (including the content policy), the static mount and every router — the wiring, and nothing else |
| `auth.py` | the login, the logout, first-run setup, and the gate every request passes through |
| `errors.py` | what a browser is shown when a request cannot be answered: the 403, 404 and 500 pages, and the JSON everything else keeps |
| `accounts/roles.py` | roles as lists of permissions, the principal a request is made by, and `can()`, the one check |
| `accounts/store.py` | users, memberships, sessions and API tokens: making them, checking them, ending them |
| `accounts/firstrun.py` | an installation with no accounts: the setup code, seeding from the old login, and what the log says at startup |
| `accounts/__main__.py` | the accounts command, run inside the container: people, roles, passwords and tokens |
| `assets.py` | what a machine's page and a part's page do the same way: photographs, notes, forms, disposal, deletion |
| `pages.py` | the small pieces an editable page needs: what has been typed before, and a note posted with photographs |
| `work.py` | the jobs on a project and the things it is about, read from the project, the item and the API alike |
| `routers/items.py` | /items/<id>: the address a label carries, and the history written under it |
| `routers/files.py` | the files kept beside the register, what each is for, and who may see it |
| `routers/computers.py` | the pages of a machine |
| `routers/parts.py` | the pages of a part, including the spec pickers |
| `routers/api_assets.py` | the JSON API for computers and parts |
| `routers/api_projects.py` | the JSON API for projects, their jobs and their orders |
| `routers/accounts.py` | the account pages: Settings → Accounts for administrators, and Your account for everybody signed in |
| `routers/health.py` | /healthz: up, and able to reach the database |
| `routers/print_queue.py` | the print queue: the owner's half, and the half a print agent's key opens |
| `routers/locations.py` | a location's page, its form, emptying, merging and deleting one, its photographs and its labels -- each route asking Show locations who may see it |
| `routers/api_locations.py` | /api/locations, and where a thing or a location has been at /api/items/<id>/moves |
| `routers/storage.py` | the audit (`/audit`; its first name, storage, is still the code's): the screen, a scan, an undo, finishing a round, and the report |
| `routers/projects.py` | the project pages: jobs, orders, and the things a project is about |
| `register.py` | the register as one id space: which table an asset id is in, what sits either side, whether a page has gone stale |
| `disposal.py` | disposing of a thing and bringing it back, including everything inside it, read off the tree |
| `forms.py` | what was typed turned into what a column holds, and what changed |
| `history.py` | the change log: writing a line, reading them back, and folding a burst into one |
| `web.py` | the templates object and what a page needs around one: the globals, the share card, the schema.org data |
| `cards.py` | the share card for a page that is a wall of photographs: the montage of four, its content-addressed cache, the sweep |
| `routers/seo.py` | robots.txt, the sitemap, and the icons asked for at the domain root |
| `routers/gallery.py` | the wall of cards, the /browse slice of it, the owner's /for-sale shortlist, and the suggestions under the search bar |
| `routers/stats.py` | the two pages of figures: /stats and the GoAccess report at /traffic, with the sandbox it runs in |
| `routers/settings.py` | /settings: the two routes behind the page of preferences |
| `routers/catalogue.py` | the catalogue as a page and as JSON: /machines, a model's own page at /machines/<key>, and /api/machines |
| `routers/images.py` | serving a photograph: the watermark, the narrower copy, the refusals |
| `routers/styles.py` | /style/data.css: the generated stylesheet, served the way a static one is |
| `routers/chrome.py` | /rail/<state>: folding the side rail away and opening it again, with no script |
| `datacss.py` | the rules whose values are data — a bezel's swatch, a bar's length — built at import |
| `models.py` | the ORM tables and their relationships |
| `db.py` | the engine and the per-request session — the only place either is made |
| `schemas.py` | the request and response shapes for `/api/*` |
| `ids.py` | allocating an asset id from `register`, which never gives one out twice |
| `common.py` | the "still held" filter, small query helpers, the image folder, collection constants |
| `settings.py` | what is kept because somebody prefers it: the definitions, where each one's answer comes from, and the writing of it |
| `presets.py` | the looks the register ships with, read from the design data — so the page cannot offer one no stylesheet was written for |
| `typefaces.py` | the ways the three faces can be pointed, read from the same design data — a pairing repoints them and changes nothing else |
| `accent.py` | the installation's accent: one colour in, the five tokens the page is painted with out, derived for the preset and the mode and served as a stylesheet of its own |
| `filekinds.py` | what a file is, read from its name and size: the drawing it gets, the list that finds it, the size it is given as, and whether it is read in the browser |
| `textfiles.py` | a text file read as a page of the register: the words in one, and Markdown set as the site's own markup, with nothing in it that runs or is fetched (ADR-0035) |
| `rail.py` | what the side rail holds besides links: each section's count for this reader, and the owner's last three |
| `locations.py` | what belongs to a location alone: its kinds, finding one by tag, path or name, what the Location box offers, a path as words, emptying, merging and forgetting one, and its label |
| `tree.py` | the one tree everything is in (ADR-0036): what a thing is inside, what is inside it, the chain up, which kinds may hold which, the loop check, and moving something and writing the move |
| `storage.py` | the audit's rounds: what a scan does -- open, found, moved in, refused -- undoing one, and the report a round ends with |
| `entry.py` | guided-entry vocabularies and quick-entry shorthands, ported from the flat-file system |
| `machines.py` | the catalogue of known machine models and the variations each was built in |
| `machinedb.py` | mapping an asset's catalogue identity between its rows and plain values |
| `specstruct.py` | converting between the free-text specs string and a normalised structure |
| `specdb.py` | mapping a part's structured specs between the typed tables and that structure |
| `ramdb.py` | mapping a computer's fitted memory between its child tables and plain counts |
| `drivedb.py` | a machine's fitted removable-media drives: rows in, canonical string out |
| `resync.py` | re-rendering the derived caches when something upstream changes |
| `search.py` | the term parser, the "any field" haystack, the suggestion list and the catalogue models offered beside it, the `/browse` views |
| `stats.py` | the figures and the pool of facts behind the public `/stats` page |
| `projects.py` | projects: the work, as against the things it is done to |
| `filesdb.py` | files kept beside the register, what each is attached to, and the bytes on disk |
| `photos.py` | watermarking, upload verification, reference photos, kept originals, crop/rotate |
| `thumbs.py` | smaller copies of the photographs, made once and kept |
| `enhance.py` | the one-touch tuneup: the automatic levels-and-colour fix a phone does |
| `enrich.py` | fetching a photo for an item from its reference URL |
| `labels.py` | what a label says and where on it that goes, for either surface: the two labels as Settings → Labels sets them up, and the stock deciding a label's shape (ADR-0037) |
| `printing.py` | the queue of labels waiting for a printer on somebody else's machine, and what any item's label is read from, for the queue and the label routes alike |
| `surfaces.py` | the two things a label is drawn on: a PDF page, and a printer's own dots |
| `barcode.py` | Code 128: a tag as the bars a label carries, set B only, and the table the browser's reader in static/code128.js is held to |
| `audit_storage.py` | checking every storage part against the questions its kind is actually asked |

Outside `api/`:

- `api/app/templates/` — 39 Jinja2 templates. `api/app/static/` — the stylesheet
  and scripts, moved out of `base.html` so they can be cached — and that move is
  what made the content policy in `main.py` possible, there being nothing inline
  left to have to allow.
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
  login. The rule lives in `may` / `_public_page` in `auth.py`.
  **Visitors must log in** takes the public pages away too, leaving the login,
  setup, the health check, the static files and the print agent's door.
- **Permissions are asked for by name, never by role.** `can(principal,
  permission)` in `accounts/roles.py` is the only check; a role is a list of
  permissions. `request.state.authed` means *may edit*, and anything that is
  about *reading* what a visitor may not see asks `sees_private` — so a viewer
  sees it, and a place that asks the wrong one hides it from a viewer rather than
  showing it to a stranger. *(ADR-0032, enforced: `test_accounts.py`)*
- **A new installation is set up by whoever can read its log.** No accounts means
  every page goes to `/setup`, which wants the code the app logged at startup;
  an installation upgraded from the single login is seeded from it instead.
  *(ADR-0032, enforced: `test_first_run.py`)*
- **There is always an administrator.** The last one cannot be demoted or switched
  off. *(enforced: `test_accounts.py`)*
- **A key handed out is never stored.** Sessions and API tokens keep a SHA-256
  digest; passwords an argon2 hash. Nothing in the log carries any of them.
- **An asset id is never reused or reassigned.** Printed labels exist. *(§3)*
- **The child rows are the truth; the string is a cache.** *(§4)*
- **A migration must not assume specific data exists.** A one-off correction to a
  named row belongs in a `tools/` script, not in the shared history, or it breaks
  every fresh install. *(ADR-0002, enforced: CI migrates an empty database)*
- **What a file is for is stated, never inferred.** A link to an asset id or to a
  model, made by hand; a tag says what a file *is* and decides nothing about where
  it appears. Matching is equality on the stored key, so renaming an item cannot
  move its files and a short tag cannot reach across the register.
  *(ADR-0006, ADR-0020, enforced: `test_files.py`)*
- **A file is not public until it is ticked.** Unpublished files answer 404, not
  401 — there is no account a reader could hold, so a prompt would only confirm
  the file exists. *(ADR-0009)*
- **A file is never shown as itself unless it is a PDF.** Everything else is a
  download, or -- a text file -- words put into a page of the register, escaped,
  with Markdown parsed with HTML off and its links and pictures made fit for the
  site's policy. A name is never evidence: a PDF is checked by its bytes, and a
  text file by having no zero byte. *(ADR-0030, ADR-0035, enforced: `test_files.py`)*
- **A share card is made of photographs that are already public.** The montage a
  grid page previews as is built from what an anonymous reader is shown, so a
  private project puts nothing on one, and `/og/{name}` opens a file by hash
  rather than reading a query. *(ADR-0017, enforced: `test_share_cards.py`)*
- **A column kept off the page is kept out of the search too.** `_haystack` reads
  every column off the model, so a new one joins the anonymous search by merely
  existing. Owner-only columns are the named set `OWNER_ONLY` in `common.py`, not
  a habit of remembering. *(ADR-0018, enforced: `test_for_sale.py`)*
- **What is kept back, it keeps out of the search as well.** Where a thing is
  kept is shown to a visitor only when that thing's `location_public` tick says so,
  so a visitor's haystack carries the names along a path only for a thing whose
  tick is on — `OWNER_ONLY` is one answer to what *this* reader is denied, and not
  the whole of it. *(ADR-0027, ADR-0036, enforced: `test_locations.py`)*
- **Where a thing is, is worked out and never written down.** Everything points at
  the one thing it is directly inside, so moving a box, a machine or a card is one
  write and what is in it follows. Nothing may be inside itself, however far down,
  and only the pairs `tree.py` lists may hold one another. *(ADR-0034, ADR-0036,
  enforced: `test_tree.py`)*
- **A thing is in one place.** A part is fitted, mounted or kept, never two at
  once; where one request names a machine and a location, the machine wins.
  *(ADR-0036, enforced: `test_tree.py`)*
- **Every change of what something is inside writes a move.** Fitting and taking
  out included, by edit, by scan, by API, by undo: each a `moves` row with its
  user. A box moving writes one row, on the box. *(ADR-0034, ADR-0036, enforced:
  `test_moves.py`)*
- **What is inside an item shares its fate; what is inside a location does not.**
  Disposing of or deleting a machine or a part does the same to everything inside
  it, all the way down; deleting a location leaves what was in it inside nothing.
  *(ADR-0036, enforced: `test_tree.py`)*
- **`public_locations` gates the location routes, not only the row.** A location's
  page, photographs, labels and API answer a visitor with the login while the
  switch is off, and a location's page shows a visitor only the things whose tick
  is on. An item's own Location row answers to its tick. *(ADR-0034, ADR-0036,
  enforced: `test_storage_visibility.py`)*
- **The API's published shape is pinned.** `api/openapi.json` is committed and a
  change a caller could see fails the suite. *(ADR-0010, enforced)*
- **Configuration comes from the environment; a preference comes from the page.**
  Told apart by who decides: whoever runs the server decides where the database
  is, and whoever owns the collection decides what it is called. Where both can
  speak the environment wins and the page says which variable holds it, because a
  click that the next restart forgets is a fault nobody can find.
  *(ADR-0023, enforced: `test_settings.py`)*
- **Touch controls are 16px.** iOS zooms the page when it focuses a control whose
  text is smaller, and does not zoom back out. Any rule that sizes a control must
  be restated in the `@media (pointer: coarse)` block. *(enforced:
  `test_stylesheet.py`)*
- **Action colours clear 4.5:1 in both themes**, computed from the theme
  variables. *(enforced: `test_stylesheet.py`)*
- **The suite runs on MariaDB and builds its schema from the real migrations.**
  There is no SQLite path to fall back to. *(ADR-0008)*
- **The models describe the schema the migrations build, and nothing else.**
  Asked what it would write, `alembic revision --autogenerate` answers nothing:
  no table, column, type or nullability differs between `Base.metadata` and a
  database migrated from empty. A model is typed for mypy's benefit and never as
  a way of changing what is stored -- `Mapped[str]` without `Optional` means NOT
  NULL, so an annotation is a schema statement whether or not it was meant as one.
  *(enforced: `test_models_match_migrations.py`)*

## 7. Where the work is

- **The `main.py` split is finished** (#66-#70), so what is left is the habit
  rather than the job: a cohesive non-route block belongs in its own module and a
  group of routes in its own router, lifted in small independently verifiable
  steps. `stats.py`, `search.py`, `photos.py`, `common.py` and `projects.py` came
  out that way, and `routers/` holds the rest.
- **The content policy is `'self'` in every directive**, with no token anywhere:
  the 69 `style` attributes are classes in `app.css`, and the two whose values are
  data — a bezel's swatch, a bar's length — name rules generated into
  `/style/data.css` (ADR-0021, ADR-0022). A new kind of data-valued rule goes in
  `datacss.py`; `test_content_security_policy.py` is what stops it going into the
  markup instead. The one response that allows script inline is GoAccess's report
  at `/traffic`, which is not the register's markup: its scripts run in a sandbox
  with an origin of their own, and no page carries its policy (ADR-0033).
- **Every module is held to `mypy --strict`**, with no list of exceptions: the
  models are typed (`Mapped[...]` on `mapped_column`), mypy runs in CI, and a new
  module is strict by doing nothing (backend-standards). That finishes the
  standards' *adopt next* list -- `ruff format --check` in CI (#77), `uv` with a
  committed lockfile and a multi-stage Dockerfile (#72), and the development
  compose override (#40) had already landed.

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
- **`request.state.authed` still says *authed* and means *may edit*.** The rename
  ADR-0032 wanted waits until the design-system branch has landed, because nearly
  every use is in a template that branch is rewriting.
- **One site.** `memberships.site_id` is always 1 and the collection's tables have
  no site at all. Tenancy would add both; ADR-0032 says what it would take.
- **Accessibility** is a decided standard rather than a courtesy: WCAG 2.2 AA
  with no exception taken (ADR-0014), narrowed on purpose to the part of it the
  suite can hold — contrast, touch targets, the skip link, header scopes, reduced
  motion and reflow at 320px — with `accessibility-standards` saying what is
  expected of new markup. The register says what it tests and makes no conformance
  claim.

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
| 0014 | Accessibility is a tested standard, not a set of habits |
| 0015 | A work project is called what the item is called |
| 0016 | One project to a thing, and a job may name the thing |
| 0017 | A page of photographs shares a montage of them |
| 0018 | A sale flag is the owner's alone |
| 0019 | Running open is supported, but never silent *(superseded by 0032)* |
| 0020 | A model link names a maker and a model, not only a catalogue key |
| 0027 | A remembered vocabulary is deleted when it is turned off *(superseded by 0034)* |
| 0028 | A file is linked to the things it is for, by their asset ids |
| 0029 | An upload starts public where the owner says so |
| 0030 | A PDF is read in the browser, and everything else is still a download |
| 0031 | The look is a design system, and its values are data |
| 0032 | Accounts, roles, and a site to hold them |
| 0033 | The traffic report runs in a sandbox of its own |
| 0034 | A location is a record in the register |
| 0035 | A text file is read as a page of the register |
| 0036 | Where a thing is, is one tree |

A significant decision becomes an ADR rather than a commit message. A finding is
decided when it is found — fixed, raised as an issue, written up, or consciously
accepted — rather than left lying.
