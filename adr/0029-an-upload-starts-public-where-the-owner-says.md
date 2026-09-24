# 0029 — An upload starts public where the owner says so

**Status:** Accepted
**Date:** 2026-09-24
**Amends:** [ADR-0009](0009-a-file-is-published-by-hand.md) — the default only.

## Context

ADR-0009 made every upload start private, and said when to revisit: if the tick
became the thing always done rather than sometimes, the answer would be "a default
per upload form rather than a default per column". An owner who files drivers and
manuals, which is most of what the box is used for here, ticks every one.

ADR-0028 also moved the tick. It used to sit on every row of every list; it is now
in the upload box and on the file's own page, so forgetting it costs a trip to
that page.

## Decision

A preference, **New files are public**, off by default. On, it starts the
**Public** box in the upload form ticked. The upload still sends what the box says,
and `files.public` still defaults to false, so a file is published only when a
tick visible on the form said so at the moment it was sent: the preference moves
where the tick starts, and never publishes anything by itself.

On a private project's page the box starts unticked whatever the preference says.
A private project is where the receipt is most likely to be, and a default that
published it would be the one place the preference could disclose something nobody
chose to.

## Consequences

- An installation that files manuals and drivers gets them published in one
  gesture again, with the choice still printed on the form in front of it.
- An installation that changes nothing behaves exactly as ADR-0009 describes.
- The preference lives in the `setting` table like the others (ADR-0023), under
  Server options, and has no environment variable: it was never configuration.
- Revisit if files end up published that were meant to be private, which is the
  failure ADR-0009 was written to prevent.
