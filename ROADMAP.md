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
  written: the multi-stage Dockerfile went with the lockfile, since it is the lockfile that
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
  surfaced by any single change. The decision under them closed a week later,
  with ADR-0014 accepted.
- **The accessibility target is decided.** WCAG 2.2 AA, with no exception taken
  ([ADR-0014](adr/0014-accessibility-is-a-tested-standard.md), accepted
  2026-09-17), and narrowed on purpose to the part of it the suite can hold: the
  register says what it tests and makes no conformance claim. Accepting it turned
  up the one item on its own list that nothing tested — reflow at 320px — and it
  was already broken, the files list pushing a phone 683px sideways with the box
  you re-file a file in off the edge. Fixed, and `test_reflow.py` now asks the
  question of every list page rather than of that one table.
- **`main.py` is split.** It is `create_app()` and nothing else: 136 lines, the two
  middlewares, the static mount and every router. The routes are in
  `api/app/routers/`, a module to a group, and the helpers they share are modules
  beside them — `assets`, `pages`, `work`, `register`, `disposal`, `forms`,
  `history`, `web`, `auth`. It went in nine steps, each verbatim and each with the
  suite green, and the finish line the item named (under about 500 lines) is met
  with room to spare.
- **A file says what it is for.** `file_asset` and `file_model` replace the
  substring match that decided what a file applied to: a link to one unit, or to a
  model — the catalogue's key where the catalogue knows the machine, the maker and
  model as written where it does not
  ([ADR-0020](adr/0020-a-model-link-names-a-maker-and-a-model.md), which fills the
  hole ADR-0006 left for every part and every PC clone). Attached by hand from the
  item's page or from `/files`, matched exactly, and tags demoted to labels. 0039
  ran the old matcher once and wrote down what it found, against a copy of the
  register first: 14 model links, one file left unfiled, and one landing on five
  cards because "Creative Labs Sound Blaster" is inside all five names — preserved
  rather than quietly corrected, and now visible on one page (#65).
- **The dependency tree is locked, and the image is built from it.**
  `api/pyproject.toml` names the fourteen, `api/uv.lock` pins the sixty-six behind
  them, and CI and the Dockerfile both install with `uv sync --frozen` — so a build
  gets what was reviewed and not what resolved that morning. The Dockerfile is two
  stages, which is what the lockfile made worth having: the dependency layer is
  rebuilt when the lock changes and not when a template does, and neither uv nor a
  compiler ships in the image facing the internet. `pip-audit` now reads the whole
  transitive tree rather than the direct names, and `.github/dependabot.yml` exists
  at last — `workflow-and-ci` had been describing it for months.
- **`ruff format` is enforced.** It runs in CI beside `ruff check`, and the tree
  was put through it in one pass to meet it — 99 files, with no hand-picked
  exception kept back. It waited for the `main.py` split rather than leading it:
  run while nine router extractions were in flight, it would have conflicted with
  every one of them. Nothing new was decided by it, since the formatter reads the
  `line-length = 100` already in `pyproject.toml`; layout simply stopped being
  something to argue about in review.
- **The content policy allows nothing inline, styles included.** `style-src` is
  `'self'` like every other directive, with no token anywhere: the 69 `style`
  attributes across nineteen templates and the two `<style>` blocks are classes in
  `app.css`, and the two whose values are data — the swatch for a bezel's shade and
  its yellowing, mixed in Python, and the length of a bar on `/stats` — name rules
  generated into `/style/data.css` by `datacss.py`, cached for a year against a
  stamp of their contents ([ADR-0022](adr/0022-no-style-attribute-and-the-rules-that-are-data-are-generated.md)).
  The roadmap offered keeping the token and writing down why as a legitimate
  outcome; it was refused because the work turned out to be a day, and a stated
  compromise nobody retires is how a temporary hole becomes a permanent one. The
  test that used to skip while the token stood now asserts, so a style attribute
  in a template fails CI rather than silently having no effect.
- **The models are typed, and mypy is in CI.** All 203 columns are `Mapped[...]`
  on `mapped_column`, converted by reading each one's nullability off the `Column`
  it replaced — `Mapped[str]` means NOT NULL, and 119 of them had never said either
  way. The schema did not move: the DDL the models compile to is byte-identical
  before and after, and `test_models_match_migrations.py` now asks Alembic what
  autogenerate would write against a migrated database and requires the answer to
  be nothing. mypy earned its place on the first run, by reading a form value as
  `UploadFile | str`: a file posted under a text field's name was a 500 on every
  form handler, the login included.
- **Every module is held to `mypy --strict`.** All fifty-one, with no list of
  exceptions left in `api/pyproject.toml` and the ways round it — a bare
  `# type: ignore`, a hand-written `Any` — configured as errors rather than left to
  review. It was scoped as "strict per module, ratcheted forward", for fear that
  strict everywhere would block the release or fill the code with `Any`; measured
  rather than feared, it was about 550 unannotated functions and fewer than 200
  errors that needed thought, so the ratchet was turned all the way instead of
  being left half way. What it found on the way is the argument for having done
  it: a machine's chip mountings could not be changed over the API without sending
  the chips again (a loop reused the name of the row the next line read), and a
  label would not print for a machine holding a part with no type. The tables the
  forms are built from, the catalogue and the gallery's cards are typed as what
  they are rather than as dictionaries of anything.
- **The backup can be restored, and is checked.** `tools/restore.sh` restores a
  backup and then checks it — every table's row count and the schema version
  against the dump, every archived photograph and file, and the public pages
  answering (#41) — and a round-trip test guards the dump-and-restore commands it
  leans on (#43).
- **The install was walked on a clean host, and a backup restored.** The reading
  half was done first (#78) — every guide and every rule file read against the
  tree and against the running stack, what had drifted corrected, and
  `CHANGELOG.md` started — but the part no reading can stand in for is the walk
  itself, and it has now been made: `INSTALL.md` followed from the top on a clean
  host that had never run this, and a backup of that host restored into a second
  stack with `tools/restore.sh`. So "it installs on your own server" stops being
  a claim with one witness, who was also the author.

  Between this and the k3s deployment above, 0.1 goes out having been stood up
  three times in two shapes — the author's own box, a clean host from the guide,
  and a Kubernetes cluster that shares none of Compose's assumptions. That was
  the point of putting both before the tag rather than after it.
- **The stack stands up on k3s.** Deployed to a three-node Civo cluster at a real
  domain, with a real certificate, and written up in
  [docs/deploying-on-k3s.md](docs/deploying-on-k3s.md). It answered all four
  questions it was set, two of them differently from how they were guessed:
  - **`.env` becomes one Secret**, read with `envFrom`, and the app needs no change
    to take it. But `${VAR:?message}` really has no equivalent, and the gap is
    worse than "no fail-fast": `api/app/db.py` defaults `DATABASE_URL` to
    `retro:retro@db`, so a Secret missing that key does not stop the stack, it
    quietly tries a guessable password. Compose has been hiding that default for
    as long as it has existed. Raised as a finding rather than fixed here.
  - **`fix-volumes.sh` does not become an init container.** It does not need to
    become anything: `fsGroup` on the pod does declaratively what the script does
    imperatively, for the app's uid 10001 and for MariaDB's 999 alike. The guess
    was that Kubernetes would need the same work in a different shape; it needs
    the work not to exist.
  - **The migrations-on-start race did not arise, and not by design.** The volumes
    are ReadWriteOnce block storage, which forces `strategy: Recreate` and caps
    the app at one replica — so the storage class prevents the second replica that
    would race, and nothing in the app does. Anyone moving to a shared filesystem
    gets the race back with no warning.
  - **TLS and the hostname went to an ingress**, so Caddy left the stack — and
    `caddy/conf.d` means nothing in this deployment. What that costs is the four
    headers Caddy sends, which are gone. What it does not cost is the
    Content-Security-Policy, because ADR-0021 had already moved it into the app;
    the split it drew is exactly the line the ingress cut along, which is the
    nearest thing to a controlled test that decision will get.

  Two things the item did not think to ask turned out to matter more than one that
  it did. `build: ./api` has no equivalent — Compose builds on the host it runs
  on, and Kubernetes needs a registry and an image built for the nodes'
  architecture, which is most of the write-up. And GoAccess reads Caddy's log off
  a shared volume, so dropping Caddy drops `/traffic` with it; the traffic report
  is coupled to the proxy, not to the app.

  The deployment was three nodes rather than the single node the item named, which
  is what surfaced the ReadWriteOnce constraint. Whether manifests ship in the
  repository stays open: the write-up carries them inline, which is enough for a
  second installer to follow and stops short of a second delivery path nobody has
  asked for yet.

## The work, in order

Nothing. Every item that 0.1 was defined by has left this file, which is what
that definition was for. **Tag `v0.1.0`.**

## After 0.1

0.2 is shaped by what 0.1's installers report; guessing now would be inventing
requirements. Six items are decided already and waiting on the release:

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

**A preferences page.** Printing options to start with — where a label goes — but
that is the first thing on it rather than the point of it. It is the first place
in the app where something is recorded because somebody *prefers* it rather than
because it is true of the collection, and once that place exists a good deal wants
to live there. It is also the foundation the multi-user work needs: accounts and
tiered permissions are, underneath, somewhere to keep "this person prefers this"
and "this person may do that", and building that on a page that already exists is
a smaller job than inventing both at once.

Fairly high up the list for soon after 0.1, and deliberately before the printing
work below rather than after it, so the first preference has somewhere to be put
down instead of being wedged in beside the theme.

**Printing options: Niimbot, remote print servers, and the rest.** A small label
is a PDF today, and getting one onto the Niimbot B1 means the phone's share sheet
and the vendor app, which rescales it on the way. Both ends were proved on the
server (2026-09-12) rather than argued about:

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

Where a label goes is then a preference — a PDF, a Bluetooth printer, or a named
printer on an agent — and it is a fact about the device rather than about the
collection: the phone by the shelf wants the Niimbot, the workshop machine the
Dymo, a visitor the PDF. So it belongs on the preferences page above, which is why
that comes first; `localStorage` beside the theme is where a per-device choice
still physically lands, but the place to *change* it is a page rather than a
menu hanging off a button. The server says what is possible and the device says
what is preferred.

The packet encoding stays in Python where the suite can reach it, and the
chooser's JavaScript is a static file from the start — the content policy
(ADR-0021, ADR-0022) will not accept another inline block.

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
