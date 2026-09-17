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
  written: the multi-stage Dockerfile is item 4's, since it is the lockfile that
  makes the layering worth having; and a *production* override is the
  installation's own file, not the project's, which `docker-environments.md` now
  says.
- **Three accessibility gaps closed.** A skip link as the first stop on every
  page, `scope` on all 43 heading cells, and a reduced-motion answer in both
  places it has to be given — the stylesheet, and the one scroll that asks for
  motion in JavaScript, where the media query cannot reach it.
  `test_keyboard_and_motion.py` holds all three, because none of them is
  surfaced by any single change. What did not close is the decision: see item 8.
- **The backup can be restored, and is checked.** `tools/restore.sh` restores a
  backup and then checks it — every table's row count and the schema version
  against the dump, every archived photograph and file, and the public pages
  answering (#41) — and a round-trip test guards the dump-and-restore commands it
  leans on (#43).

## The work, in order

**1. Make the repository public, then walk §2.** The walk was done on a clean
Ubuntu 24.04 host (2026-09-10) and everything after §2 holds: all 35 migrations
ran from empty with no crash-loop, Caddy had a certificate on the first attempt,
and logging in, adding a machine from the catalogue, adding a part to it,
printing a label and scanning it all worked. What it found is fixed — the missing
`docker` group step, a check that passed without reaching the daemon, a SQLite
development path that cannot work since Alembic took the schema, a backup script
that left the `files` volume behind, and a QR scan that dropped to plain HTTP.

What could not be walked is §2 itself: the repository is private, so `git clone`
fails for anybody who is not the author, and the guide named the wrong repository
besides. The licence is in place and the intent is a public release, so this is
now a decision and a click rather than a piece of work — but until it is made,
nobody can follow the guide from its second step, and the walk cannot be repeated
end to end by a stranger.

**2. Turn CI on for fork pull requests.** #25 arrived from a fork with four
migrations and zero checks. Ten minutes of settings, and it protects everything
after it.

**3. Implement ADR-0006 — file links.** The only user-visible correctness item
left in the file store. The half that risked exposing something personal is done:
a file is published by hand and starts unpublished (ADR-0009 amends ADR-0006's
default), the listing and the download are both gated, and an unpublished one is
a 404 served `private, no-store`. What remains is the association under that gate,
which is still a substring match recomputed per request.

- `file_asset` and `file_model` join tables; asset ids as plain columns.
- Backfill by running the existing matcher once and writing what it finds.
  Test-first: assert the fixture set's associations survive. Read the output
  before trusting it — it preserves the matcher's mistakes too.
- Demote tags to descriptive labels; rewrite the two docstrings that argue for
  name-matching.
- Lift the `files` routes into `routers/files.py` while in there — a free step of
  item 5, paid for by work already happening.

**4. `uv` with a committed `uv.lock`, then `ruff format --check .` in CI.**
Dependencies first, so everything after it builds from a pinned tree. The
multi-stage Dockerfile belongs here rather than in an item of its own: the point
of it is a dependency layer built from the lockfile and cached apart from the
code, which is this work.

`ruff format` rewrites most of `main.py`, so it goes *after* the split rather than
before it — otherwise every router extraction in flight conflicts with it.

**5. Finish splitting `main.py`.** 4,849 lines, 118 routes still in it and 5 out,
after `common`/`stats`/`photos`/`search` and the first route group (#44). It is why
#25 collided with #26, so it pays for itself in reduced conflict.

Route groups go in an `api/app/routers/` package, one module per group, included
by `main`. The remaining groups in the order they are being taken, quietest first:
`/images`, the catalogue, stats and traffic, the gallery, auth, items, files, then
the computers, parts and projects pages, then the three `/api` groups. Shared
helpers a group needs — the templates object and page helpers, the log helpers,
`get_or_404` — come out into their own modules just before the first group that
needs them, and `create_app()` is last, because every route still using `@app` has
to be gone before it can exist.

Two things to hold on to while it happens: a test that patches a name on `main`
has to follow that name when it moves, or the patch quietly stops working; and
`/computers/new`, `/parts/new` and `/projects/new` must stay declared before their
`/{aid}` neighbours.

*This needs a finish line or it will hold the release indefinitely.* Proposed:
done when `main.py` holds only app construction, middleware and start-up wiring —
every route in an `APIRouter` module, every non-route helper in a module of its
own. Under about 500 lines is the sanity check, not the goal. Extract in small,
independently-verifiable steps, leaning on the suite.

**6. SQLAlchemy 2.0 typed ORM, then `mypy app` in CI.** `Mapped[...]` and
`mapped_column` on the models first, because that is what lets the models be
type-checked at all.

*Scope needs deciding.* `backend-standards` says to type the code as you touch
it, which is incremental and sits awkwardly with a release gate. Recommended:
gate 0.1 on `mypy app` passing, with `--strict` enabled per module for the
modules already extracted and ratcheted forward as more come out. Demanding
strict across a `main.py` of this size would either block the release or produce a
lot of `Any`.

**7. Content-Security-Policy.** `security-standards` calls it the strongest
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

Still independent of items 5 and 6, so it can go earlier — though the plan is to
take it after the split, to keep two people out of the same templates at once.

**8. Decide the accessibility target.** The gaps are closed and tested; what is
left is the decision under them.
[ADR-0014](adr/0014-accessibility-is-a-tested-standard.md) proposes WCAG 2.2 AA
and **is still Proposed**. It is the difference between a set of habits with a
few of them tested and a standard something can be measured against, and it has a
cost attached — AA asks for reflow at 320px and a focus indicator of a stated
size, neither of which this project has looked at. Accept it, accept it with
named exceptions, or write down what is held to instead; any of the three ends
the item, leaving it open does not.

**9. Read the docs against the running app, then tag.** README, INSTALL, DEPLOY
and MANUAL are detailed, which is exactly why they drift — and the drift is not
only in the user-facing docs. This pass found `testing-standards`,
`workflow-and-ci` and `CLAUDE.md` all describing a SQLite test run that no longer
exists, and a README crediting contributors without ever stating the project's
licence. So this item covers `.claude/rules/` and `CLAUDE.md` too — including
`accessibility-standards`, which item 8 will have just changed.

The release gate: item 1's walk repeated on a clean host, a backup of that host
restored into a second stack with `tools/restore.sh` (a release that invites
people to self-host should have restored one at least once), the docs corrected to
match, a `CHANGELOG.md` started, then tag `v0.1.0`.

## After 0.1

0.2 is shaped by what 0.1's installers report; guessing now would be inventing
requirements. Three items are decided already and waiting on the release:

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
the chooser's JavaScript is a static file from the start — item 7 will not accept
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
