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
- Lift the `files` routes into `files.py` while in there — a free step of item 5,
  paid for by work already happening.

**4. `uv` with a committed `uv.lock`, then `ruff format --check .` in CI.**
Dependencies first, so everything after it builds from a pinned tree.

**5. Finish splitting `main.py`.** 4,851 lines and 122 routes after
`common`/`stats`/`photos`/`search`. It is why #25 collided with #26, so it pays for itself
in reduced conflict.

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
strict across a 5,361-line `main.py` would either block the release or produce a
lot of `Any`.

**7. Content-Security-Policy.** `security-standards` calls it the strongest
single anti-XSS control, and it is blocked only by `base.html`'s inline scripts;
the CSS half is already done. Two steps: move the inline JS to a cacheable static
file, then send the header from Caddy alongside those already there. Independent
of items 5 and 6, so it can go earlier if the split runs long.

**8. Close the accessibility gaps, and decide the target.** The contrast and
touch-size tests in `test_stylesheet.py` exist because each of those things
shipped broken and a contributor reported one of them (#21). That is care living
in whoever last looked at it, which is what `security-standards` was written to
end — so `accessibility-standards` now records what is enforced and what is
expected, and [ADR-0014](adr/0014-accessibility-is-a-tested-standard.md) proposes
WCAG 2.2 AA as the target. **The ADR is Proposed and wants a decision**; the
three gaps below are an afternoon either way.

- A skip link in `base.html` — a keyboard user currently tabs the whole header
  on every page.
- `scope` on the 43 `<th>` in the templates.
- A `prefers-reduced-motion` block in `app.css`.
- Tests for the first two in the suite, in the way `test_stylesheet.py` already
  tests the stylesheet: these are gaps no single change surfaces, so a habit will
  not catch them coming back.

Sits beside item 7 rather than after it: both are `base.html` work, and the
inline JavaScript that blocks the CSP is in the same file as the missing skip
link.

**9. Docker environment separation.** Base plus `dev`/`prod` overrides, a
multi-stage Dockerfile with deps-before-source layering, a non-root user in prod,
and a database healthcheck behind `depends_on: condition: service_healthy`.

**10. Read the docs against the running app, then tag.** README, INSTALL, DEPLOY
and MANUAL are detailed, which is exactly why they drift — and the drift is not
only in the user-facing docs. This pass found `testing-standards`,
`workflow-and-ci` and `CLAUDE.md` all describing a SQLite test run that no longer
exists, and a README crediting contributors without ever stating the project's
licence. So this item covers `.claude/rules/` and `CLAUDE.md` too — including
`accessibility-standards`, which item 8 will have just changed.

The release gate: item 1's walk repeated on a clean host, the docs corrected to
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

**An item's Projects panel becomes its work record.** `_projects.html` names the
projects an item is on and colours them by status, which answers whether a board
is spoken for but not what it is waiting for. Two extensions, both reading tables
that already exist:

- The open jobs, and the orders still in the post, for this item on the item's own
  page — so a board says what is outstanding without anybody opening the project
  to find out.
- Finished projects as well as live ones, so a machine's page reads as what has
  been done to it over the years and not only what is promised now. That is the
  half of the record the panel currently drops, and it is the half that matters
  when you are holding the machine wondering whether the caps were already done.

`project_asset`, `project_task` and `project_order` carry all of it; the work is
in the query and in keeping the panel readable once it says more than a name. Mind
[ADR-0004](adr/0004-work-projects-are-public.md) on the way out — a private
project may not name itself to a visitor, and an item page is public.

## Out of scope

Reference BOMs, stock quantities, harvest-and-install workflows and substitution
facts — see [ADR-0007](adr/0007-the-register-records-what-is-owned.md) for the
argument. `AssetChip` and `AssetVariant` are the in-scope form of component
detail.
