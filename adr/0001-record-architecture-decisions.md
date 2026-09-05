# 0001 — Record architecture decisions

**Status:** Accepted
**Date:** 2026-09-05

## Context

The project is maintained by one or two people, in bursts, with long gaps. When a
decision (why MariaDB, why server-rendered HTML, why a rule is shaped a certain
way) lives only in someone's head or in a commit message, it gets lost, and the
next person — or the same person months later — either re-litigates it or breaks
it by accident.

## Decision

Record significant decisions as short ADRs in `adr/`, following the convention in
`adr/README.md`. "Significant" means anything that shapes the structure, changes
an interface others depend on, or that you'd otherwise have to explain twice.

## Consequences

- Decisions are discoverable and have a rationale attached.
- A little discipline per decision; ADRs are meant to be short, so the cost is low.
- Changed decisions are superseded, not edited, so the reasoning trail survives.
