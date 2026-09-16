# Architecture Decision Records

Short records of decisions that shape the project — why we chose something, so a
future reader (or a returning maintainer) doesn't have to reverse-engineer it.

## Convention

- One file per decision: `NNNN-kebab-title.md`, numbered in order.
- Each record has: **Status** (Proposed | Accepted | Superseded by ADR-XXXX),
  **Date** (ISO), **Context** (the forces/constraints), **Decision** (stated
  plainly), **Consequences** (what it makes easy or hard, and when to revisit).
- **Supersede, don't rewrite.** If a decision changes, add a new ADR and mark the
  old one *Superseded by ADR-XXXX* — the history is the point.
- Keep them short. An ADR is a paragraph or two per section, not an essay.

## Index

- [0001](0001-record-architecture-decisions.md) — Record architecture decisions —
  *Accepted*
- [0002](0002-migrations-must-not-assume-specific-data.md) — Migrations must not
  assume specific data — *Accepted*
- [0003](0003-work-is-noted-at-check-in.md) — Work is noted at check-in —
  *Accepted* (privacy default amended by [0004](0004-work-projects-are-public.md))
- [0004](0004-work-projects-are-public.md) — Work projects are public by default —
  *Accepted*
- [0005](0005-the-tuneup-is-conservative-and-takes-one-step-back.md) — The photo
  tuneup is conservative, and takes exactly one step back — *Accepted*
- [0006](0006-files-are-linked-to-what-they-are-for.md) — Files are linked to what
  they are for, not named after it — *Accepted* (privacy default amended by
  [0009](0009-a-file-is-published-by-hand.md))
- [0007](0007-the-register-records-what-is-owned.md) — The register records what is
  owned, not what it is made of — *Accepted*
- [0008](0008-the-suite-runs-on-mariadb.md) — The suite runs on MariaDB, and builds
  its schema from the migrations — *Accepted*
- [0009](0009-a-file-is-published-by-hand.md) — A file is published by hand —
  *Accepted*
- [0010](0010-the-published-api-shape-is-kept-in-the-repository.md) — The published
  API shape is kept in the repository — *Accepted*
- [0011](0011-the-register-is-a-product-other-people-run.md) — The register is a
  product other people run — *Accepted*
- [0012](0012-run-alongside-an-existing-reverse-proxy.md) — Run alongside an
  existing reverse proxy — *Proposed*
- [0013](0013-stay-server-rendered-polish-through-design.md) — Stay server-rendered;
  polish comes from design, not a SPA — *Proposed*
- [0014](0014-accessibility-is-a-tested-standard.md) — Accessibility is a tested
  standard, not a set of habits — *Proposed*
- [0015](0015-a-work-project-is-called-what-the-item-is-called.md) — A work project
  is called what the item is called — *Accepted* (amends
  [0003](0003-work-is-noted-at-check-in.md)'s naming clause)
- [0016](0016-one-project-to-a-thing.md) — One project to a thing, and a job may
  name the thing — *Accepted* (changes the shape
  [0003](0003-work-is-noted-at-check-in.md) and
  [0004](0004-work-projects-are-public.md) assume)
- [0019](0019-running-open-is-supported-but-never-silent.md) — Running open is
  supported, but never silent — *Accepted* (0017 and 0018 are on a branch in
  flight; this leaves room for them)
