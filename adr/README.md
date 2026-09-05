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
  *Accepted*
