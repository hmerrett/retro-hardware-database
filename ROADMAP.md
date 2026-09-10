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

**1. Walk the install on a clean host.** ADR-0002 exists because a fresh
`docker compose up` crash-looped. CI proves the migrations reach head from empty,
but nothing exercises the walk a person does: clone, fill `.env`, set the
hostname, start it, log in, add an item, print a label, scan it. Do this *first*
rather than last — a stale step is cheap to find now and expensive to find in a
release. The `RHDB_SECRET_KEY` fail-fast and the compose `${VAR:?}` guards are
already in place and can be trusted.

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

**5. Finish splitting `main.py`.** 5,361 lines and 116 routes after
`common`/`stats`/`photos`. It is why #25 collided with #26, so it pays for itself
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

**8. Docker environment separation.** Base plus `dev`/`prod` overrides, a
multi-stage Dockerfile with deps-before-source layering, a non-root user in prod,
and a database healthcheck behind `depends_on: condition: service_healthy`.

**9. Read the docs against the running app, then tag.** README, INSTALL, DEPLOY
and MANUAL are detailed, which is exactly why they drift — and the drift is not
only in the user-facing docs. This pass found `testing-standards`,
`workflow-and-ci` and `CLAUDE.md` all describing a SQLite test run that no longer
exists, and a README crediting contributors without ever stating the project's
licence. So this item covers `.claude/rules/` and `CLAUDE.md` too.

The release gate: item 1's walk repeated on a clean host, the docs corrected to
match, a `CHANGELOG.md` started, then tag `v0.1.0`.

## After 0.1

0.2 is shaped by what 0.1's installers report; guessing now would be inventing
requirements. One item is decided already and waiting on the release:

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

## Out of scope

Reference BOMs, stock quantities, harvest-and-install workflows and substitution
facts — see [ADR-0007](adr/0007-the-register-records-what-is-owned.md) for the
argument. `AssetChip` and `AssetVariant` are the in-scope form of component
detail.
