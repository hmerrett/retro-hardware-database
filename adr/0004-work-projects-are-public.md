# 0004 — Work projects are public by default

**Status:** Accepted
**Date:** 2026-09-05
**Amends:** [ADR-0003](0003-work-is-noted-at-check-in.md) (the privacy default only;
the rest of it stands)

## Context

ADR-0003 had every project raised from a work box start **private**, reasoning that
a sentence typed at a bench in five seconds has not been considered for publication
and that the safe default for something unconsidered is that nobody reads it. That
inherited the rule from the `project` flag migration 0031 replaced, which was
private because it was the one thing on a public item page kept back from a visitor.

A day of using it says otherwise. The register is a public catalogue of old
machines, and what is wrong with one — the RIFA that wants replacing, the belt that
has perished — is a good part of what makes it interesting to read; several of the
projects kept back were the ones a visitor would most want. The default was being
undone by hand on nearly every project, and a default that is always undone is not
a default, it is a step.

Privacy is also not free while it holds: a private project is kept out of five
places and out of its items' histories, and publishing it later writes those
history lines after the fact rather than when the work was noted.

## Decision

A project raised from the work box, the quick box or the API is **public**, like
everything else in the register. `private` stays exactly as it was — the same
column, the same five doors, the same history rules — but it is set by the tick on
a project's own form, deliberately, for the project that genuinely should not be
read. It is a decision now rather than a starting point.

The projects already written behind the tick are published by
`tools/publish_projects.py`, run by hand on the database that wants it — **not** by
a migration. "Publish every private project" is a true thing to want on one
collection and a data breach on another; a shared migration doing it would publish
whatever the owner of every installation that pulled the update had decided nobody
should read. That is the shape ADR-0002 keeps out of the migration history.

## Consequences

- Noting what a machine needs is a public act, and reads on the item's page and in
  its history immediately rather than after a second decision.
- Anything genuinely private now depends on remembering the tick. The forms say so
  where the box is, and the projects list marks a private one on its row.
- The five doors and the publish/withdraw history rules are untouched and still
  tested; only the default changed.
- Revisit if the projects list fills with work nobody wants read — the pressure
  valve is the tick, and if it is being used on most projects the default is wrong
  again, in the other direction.
