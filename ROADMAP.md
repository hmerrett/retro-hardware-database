# Roadmap — the road to 0.1

British English. Kept short, and kept honest: an item leaves this file when it is
done, not when it is started.

## What 0.1 means

A first release is a promise that somebody who is not the author can install this
from `INSTALL.md`, on their own server, and have it work — that nothing in it
leaks what it should not or claims what is not true, and that the inside is in a
state a contributor can work in.

That last clause is a deliberate choice: everything below ships before 0.1,
including the internal work that a release could technically go out without. The
reasoning is that a first release invites people in, and the state they find is
the state they will judge and build on.

**The repository goes public after 0.1, not as part of it.** 0.1 is the point at
which it is ready enough for other people to use, and opening it before that
invites them to judge it half-finished. The cost is that §2 of the install guide
— `git clone` — is the one step a stranger cannot walk until the click is made,
so it is walked from a local clone and taken on trust until then. Every other
step is walked for real.

## Settled

The licence (AGPL-3.0), the version's single home
(`api/app/__init__.py`, now `0.1.0`), the file-association and scope questions
(ADR-0006, ADR-0007) and the test engine (ADR-0008). Nothing open remains to
decide before the work below can start.

## Done, and gone from the list

An item leaves this file when it is done, so what has left is recorded once here
rather than being wondered about later.

- **Docker environment separation.** The app runs as `appuser` and not root, the
  photograph and file volumes are put right before it starts, the database is
  behind a healthcheck the app waits on, and `docker-compose.dev.yml` layers the
  source mount and reload on top (#40). Two parts of that item did not land as
  written: the multi-stage Dockerfile is item 1's, since it is the lockfile that
  makes the layering worth having; and a *production* override is the
  installation's own file, not the project's, which `docker-environments.md` now
  says.
- **CI runs on fork pull requests.** Turned on with approval required and no
  write token or secret handed to a fork's run, so a contributor's branch is
  checked before it is read rather than after it is merged. #25 arriving with four
  migrations and zero checks is what this was for.
- **Three accessibility gaps closed.** A skip link as the first stop on every
  page, `scope` on all 43 heading cells, and a reduced-motion answer in both
  places it has to be given — the stylesheet, and the one scroll that asks for
  motion in JavaScript, where the media query cannot reach it.
  `test_keyboard_and_motion.py` holds all three, because none of them is
  surfaced by any single change. What did not close is the decision: see item 7.
- **The accessibility target is decided.** WCAG 2.2 AA, with no exception taken
  ([ADR-0014](adr/0014-accessibility-is-a-tested-standard.md), accepted
  2026-09-17), and narrowed on purpose to the part of it the suite can hold: the
  register says what it tests and makes no conformance claim. Accepting it turned
  up the one item on its own list that nothing tested — reflow at 320px — and it
  was already broken, the files list pushing a phone 683px sideways with the box
  you re-file a file in off the edge. Fixed, and `test_reflow.py` now asks the
  question of every list page rather than of that one table.
- **A file says what it is for.** `file_asset` and `file_model` replace the
  substring match that decided it: a link to one unit, or to a model — the
  catalogue's key where the catalogue knows the machine, the maker and model as
  written where it does not ([ADR-0020](adr/0020-a-model-link-names-a-maker-and-a-model.md),
  which fills the hole ADR-0006 left for every part and every PC clone). Attached
  by hand from the item's page or from `/files`, matched exactly, and tags demoted
  to labels. 0039 ran the old matcher once and wrote down what it found, on a copy
  of the register first: 14 model links, one file left unfiled, and one landing on
  five cards because "Creative Labs Sound Blaster" is inside all five names —
  preserved rather than quietly corrected, and now visible on one page (#65). The
  `files` routes came out into `routers/files.py` with it, and the history helpers
  into `history.py` ahead of them, which is the first of item 2 paid for by work
  already happening.
- **The backup can be restored, and is checked.** `tools/restore.sh` restores a
  backup and then checks it — every table's row count and the schema version
  against the dump, every archived photograph and file, and the public pages
  answering (#41) — and a round-trip test guards the dump-and-restore commands it
  leans on (#43).

## The work, in order

**1. `uv` with a committed `uv.lock`, then `ruff format --check .` in CI.**
Dependencies first, so everything after it builds from a pinned tree. The
multi-stage Dockerfile belongs here rather than in an item of its own: the point
of it is a dependency layer built from the lockfile and cached apart from the
code, which is this work.

`ruff format` rewrites most of `main.py`, so it goes *after* the split rather than
before it — otherwise every router extraction in flight conflicts with it.

**2. Finish splitting `main.py`.** 4,044 lines, 103 routes still in it and 27 out
across six router modules — `images`, the catalogue, stats, the gallery, the
crawler's pages and now the files — after `common`/`stats`/`photos`/`search`,
`auth` and `history`. It is why #25 collided with #26, so it pays for itself in
reduced conflict.

Route groups go in an `api/app/routers/` package, one module per group, included
by `main`. The remaining groups in the order they are being taken, quietest first:
items, then the computers, parts and projects pages, then the three `/api`
groups. Shared helpers a group needs — the templates object and page helpers, the
log helpers, `get_or_404` — come out into their own modules just before the first
group that needs them, and `create_app()` is last, because every route still using
`@app` has to be gone before it can exist.

Two things to hold on to while it happens: a test that patches a name on `main`
has to follow that name when it moves, or the patch quietly stops working; and
`/computers/new`, `/parts/new` and `/projects/new` must stay declared before their
`/{aid}` neighbours.

*This needs a finish line or it will hold the release indefinitely.* Proposed:
done when `main.py` holds only app construction, middleware and start-up wiring —
every route in an `APIRouter` module, every non-route helper in a module of its
own. Under about 500 lines is the sanity check, not the goal. Extract in small,
independently-verifiable steps, leaning on the suite.

**3. SQLAlchemy 2.0 typed ORM, then `mypy app` in CI.** `Mapped[...]` and
`mapped_column` on the models first, because that is what lets the models be
type-checked at all.

*Scope needs deciding.* `backend-standards` says to type the code as you touch
it, which is incremental and sits awkwardly with a release gate. Recommended:
gate 0.1 on `mypy app` passing, with `--strict` enabled per module for the
modules already extracted and ratcheted forward as more come out. Demanding
strict across a `main.py` of this size would either block the release or produce a
lot of `Any`.

**4. Content-Security-Policy.** `security-standards` calls it the strongest
single anti-XSS control, and the CSS half is already done. Counted rather than
guessed at, what stands in the way is larger than "the inline scripts in
`base.html`": 13 script blocks and 1,526 lines of JavaScript in that file, five
more templates with a block of their own, 8 inline event handlers and 65 inline
`style` attributes. So three steps, not two:

- move the JavaScript to a cacheable static file, versioned the way `app.css` is,
  and repoint the tests that assert on the markup of a page containing it;
- deal with the handlers and the `style` attributes, or decide to keep
  `'unsafe-inline'` for styles alone and write down why;
- send the header from Caddy, **`Content-Security-Policy-Report-Only` first**, so
  a week of real traffic says what it would have broken before anything breaks.

Still independent of items 2 and 3, so it can go earlier — though the plan is to
take it after the split, to keep two people out of the same templates at once.

**5. Read the docs against the running app, then tag.** README, INSTALL, DEPLOY
and MANUAL are detailed, which is exactly why they drift — and the drift is not
only in the user-facing docs. This pass found `testing-standards`,
`workflow-and-ci` and `CLAUDE.md` all describing a SQLite test run that no longer
exists, and a README crediting contributors without ever stating the project's
licence. So this item covers `.claude/rules/` and `CLAUDE.md` too — including
`accessibility-standards`, which the accessibility decision has just rewritten.

The release gate: the install walk repeated on a clean host, a backup of that host
restored into a second stack with `tools/restore.sh` (a release that invites
people to self-host should have restored one at least once), the docs corrected to
match, a `CHANGELOG.md` started, then tag `v0.1.0`.

## After 0.1

0.2 is shaped by what 0.1's installers report; guessing now would be inventing
requirements. Four items are decided already and waiting on the release:

**Make the repository public**, which is the first thing after the tag rather than
one of 0.2's. The licence is in place, the guide names the right repository and
everything after §2 has been walked on a clean host (2026-09-10) — all 35
migrations ran from empty with no crash-loop, Caddy had a certificate on the first
attempt, and logging in, adding a machine from the catalogue, adding a part to it,
printing a label and scanning it all worked. What that walk found is fixed: the
missing `docker` group step, a check that passed without reaching the daemon, a
SQLite development path that cannot work since Alembic took the schema, a backup
script that left the `files` volume behind, and a QR scan that dropped to plain
HTTP. So this is a decision and a click, and the walk is repeated end to end by
somebody who is not the author once it is made.

**Catalogue contributions without a pull request** (#29). Adding a machine
currently means editing a file in the repository and opening a PR, which filters
contributors by their comfort with git rather than by whether they know the
hardware. The fix is a GitHub issue form (`.github/ISSUE_TEMPLATE/`) collecting
the flat fields a model has — family, key, model, year, cpu, chassis, os, ram,
issues, styles, sources — and an Action that turns a labelled submission into a
pull request adding one catalogue file. CI validates it by loading it, which is
the same validation the running site does and so costs nothing to write. A GitHub
account is the prerequisite: no submission endpoint on the register, no
credential in the app, no service to host.

It needs `machines.yaml` split into per-family fragments first, so that a new
machine is a new file rather than an edit to a 9,961-line one. The `chips:` block
does not fit a flat form and is left to the pull request, where a maintainer's eye
is worth most anyway.

Not taken up from #29: the portable format, global identifiers and
synchronisation. There is one catalogue, it ships with the code and it has one
history, so duplicates only become possible once local-only entries exist — which
is a decision to take when somebody has one worth protecting, not before.

**Print a label without the share sheet.** A small label is a PDF today, and
getting one onto the Niimbot B1 means the phone's share sheet and the vendor app,
which rescales it on the way. Both ends were proved on the server (2026-09-12)
rather than argued about:

- The B1 speaks a documented Bluetooth LE protocol, and the label `labels.py`
  already renders survives the trip. At 203 dpi the 51×19 strip is 152×408 px,
  inside the B1's 384 px head, and the QR still decodes at 4.29 px per module. A
  complete job — 415 packets, 13,115 bytes, about two seconds over Bluetooth —
  assembles from it, and every checksum validates against an independent
  implementation of the protocol.
- A Dymo elsewhere on the LAN is `cups`, `printer-driver-dymo` and the `lp` call
  `tools/make_labels.py` already makes. The agent polls outbound, so the LAN needs
  no inbound hole and no dynamic DNS.

Two things are not free. The B1 takes 50×30 mm die-cut stock, not the Dymo's
51×19 strip: handing `_render_small` the new geometry produces exactly the right
raster and the wrong layout, because the QR sizes itself to the label's height and
leaves the text nothing. That is a layout of its own, not a row in a table. And
iOS Safari has no Web Bluetooth and never has, so the button cannot reach the
printer from the phone as things stand. Bluefy — a third-party WebKit browser
carrying its own Bluetooth stack — costs nothing and proves the whole design; only
if it earns its place is the next step a `WKWebView` shell that loads the site and
injects a single native bridge. A shell is not a second client, which is what
[ADR-0013](adr/0013-stay-server-rendered-polish-through-design.md) reserves a new
ADR for.

Where a label goes is then a per-device preference — a PDF, a Bluetooth printer,
or a named printer on an agent — kept in `localStorage` beside the theme. It is a
fact about the device and not about the collection: the phone by the shelf wants
the Niimbot, the workshop machine the Dymo, a visitor the PDF. The server says
what is possible and the device says what is preferred; per
[ADR-0011](adr/0011-the-register-is-a-product-other-people-run.md) there is one
account, so there is nowhere per-user to put it and no reason to want one. The
chooser hangs off the print button rather than living on a settings page nobody
would find, the packet encoding stays in Python where the suite can reach it, and
the chooser's JavaScript is a static file from the start — item 6 will not accept
another inline block.

**The orders still in the post, on the item's page.** The Work panel on a thing now
lists the jobs written against it, outstanding first, with its project named above
them ([ADR-0016](adr/0016-one-project-to-a-thing.md)) — so a board says what it is
waiting for without anybody opening the project to find out. What it does not yet
say is what has been *bought* for it. `project_order` holds that, and nothing links
an order to a thing: an order is deliberately a note about a purchase rather than a
half-made asset, so the link would have to be the same optional one a job now
carries, and is worth having for the same reason. Wanted when a project has enough
on order that "which of these is for the Amstrad?" stops being obvious.

## Out of scope

Reference BOMs, stock quantities, harvest-and-install workflows and substitution
facts — see [ADR-0007](adr/0007-the-register-records-what-is-owned.md) for the
argument. `AssetChip` and `AssetVariant` are the in-scope form of component
detail.
