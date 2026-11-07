# 0046 — Only what is directly on a bench is the bench's

**Status:** Accepted
**Date:** 2026-11-07
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

ADR-0043 made a bench a kind of location, and what is kept on one the bench's own
equipment: never fitted in the machine being surveyed, never counted when working
out which machine it is, and never moved. It said "on a bench, or in something on
a bench", so that a box of the bench's network cards would count.

The first bench made a Bench on a real register held two trays: 12 network cards
and 33 I/O cards (disk controllers, serial and parallel cards, SCSI, an XT-CF).
Those are the collection's spare cards, kept beside the machines because that is
where they get tried, and not the bench's kit. Under the rule as written, a card
taken from a tray, fitted in a machine and named at the machine would have been
left in the tray, every time, by every survey. The one card that is the bench's
(the network card every machine is started from) stands on the bench itself.

## Decision

**What is kept directly on a bench is the bench's, and so is anything mounted on
it** (a boot ROM on the bench's network card). A box, a tray or a drawer on a
bench is storage like any other: a part in one is found and fitted as a part on
a shelf is.

The place still says it, as ADR-0043 chose over a tick on the part: a card
becomes the bench's by being put on the bench, and stops being the bench's by
being put away.

## Consequences

- A tray of spare cards can sit on the bench without its cards being treated as
  test equipment.
- Kit the bench keeps in a box (a box of boot cards) is not the bench's until it
  is taken out and put on the bench. One card on the bench is the usual case,
  and the trays were the evidence.
- Working out whether a part is the bench's reads one location, the first one up
  its chain, rather than every location above it.
