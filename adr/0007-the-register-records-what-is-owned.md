# 0007 — The register records what is owned, not what it is made of

**Status:** Accepted
**Date:** 2026-09-08

## Context

A large contribution (PR #25, closed) proposed a second domain on top of the
register: reference BOMs with an expected part per board position, house and
manufacturer part numbering beside a generic component, stock lots and
quantities, harvest-from-donor and install-into-board workflows, and evidenced
directional substitution facts. Twenty-one tables and four migrations.

Declining a pull request is not the same as deciding the question, and the
question will be asked again by whoever next stands over a board with a dead
chip. The reasoning in that contribution was also not poor — its treatment of
compatibility as an evidenced, directional claim, kept apart from historical
production use, was careful and correct on its own terms. So the boundary has to
be argued rather than asserted.

The register as it stands answers three questions: what do I have, what is it,
and what has happened to it. Every table hangs off an asset id or describes a
catalogue model, and history is dated notes and photographs. Component detail is
already in scope and already present: `AssetChip` records which variant sits in
each of an asset's sockets — the ULA, the SID, the CRTC, the Kickstart — keyed by
the catalogue's stable role slug, with the number as it is marked on the chip.

What the proposal added was a different kind of thing: a model of what *ought* to
be in a position, stock to draw from, and a grading of what may go in instead.

## Decision

Out of scope. The register describes assets, the catalogue models they answer to,
and their history. It does not model reference BOMs or board positions, does not
hold stock quantities, does not run harvest or install workflows, and does not
record substitution or production-use facts.

The line is that the register records **what is observed** — this socket holds
this chip, marked thus — and not what should be there, nor what is on the shelf to
put there, nor which alternatives would do. `AssetChip` and `AssetVariant` are
the in-scope form of component detail and are sufficient for it.

Two things this does not exclude. A purchase is still recorded, on
`ProjectOrder`, which is where money and a supplier already live. And a
replacement chip, once fitted, is described the ordinary way — the socket's row
changes and the work is noted at check-in (ADR-0003).

The argument that settles it is asymmetry of failure. A register that is slightly
out of date is still useful: the machine is on the shelf whether or not its page
is current. A stock system that is slightly out of date is worse than none,
because it will tell you that you have a part you do not, and you will plan a
repair around it. Stock earns its keep only where it is maintained as a matter of
routine, and this collection is browsed, photographed and labelled — not worked
through at volume.

## Consequences

- The roadmap is honing and hardening what exists, not extending the domain.
  A future proposer reads this record first.
- Anyone wanting the workbench keeps it outside the register, where being wrong
  about stock costs them a wasted afternoon rather than corrupting the catalogue.
- Prior art is not lost: PR #25's branch survives locally as `pr25` — 4,340 lines
  and 98 tests — should the decision ever be revisited.
- Revisit if the collection starts being repaired at volume and a stock list is
  being kept somewhere anyway. A spreadsheet already in daily use is the signal
  that this was decided too early; nothing else is.
