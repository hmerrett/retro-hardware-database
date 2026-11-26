# 0056 — Verified leaves out the clock's battery, and is a blue check

**Status:** Accepted
**Date:** 2026-11-26
**Amends:** [ADR-0055](0055-a-motherboard-whose-own-tests-pass-is-verified.md)

## Context

ADR-0055 counted the clock and its CMOS memory among the board's tests. When it went
live, two boards that passed everything else were failed by their clocks: a Tulip TC16
whose clock was not running (register A read 7Fh, and DOS had started at 1 January
1980), and an Amstrad PC2086 whose clock said its battery was flat. Both are the
battery, which runs down and is changed, as a keyboard is plugged in. Neither is a
fault in the board. The owner asked for the clock's battery to be left out too.

The owner also asked for the mark to be seen where people look: a blue check beside
the item's title and on the front page, for a verified board and for a computer whose
board is verified. ADR-0055 marked the board alone, with a green chip in lists and a
row in its Details.

## Decision

- **A clock failure the battery explains does not count.** tinydiag's clock test
  checks first what the battery keeps: the bit that says the clock's memory is valid
  (`battery flat`), the SET bit left on (`clock halted`), the divider that runs the
  clock (`oscillator off`), the BIOS's own note that the CMOS lost power or that its
  checksum is bad, and the checksum itself. A clock that fails on one of those is
  taken as not applying, as a clock on an XT is. A clock that runs and fails (its
  seconds counted wrong, a second the wrong length, the update flag stuck, IRQ8 lost)
  still fails the board. The register reads which it was from the test's detail
  (`DETAIL_RTC`), as it reads `DETAIL_RAM`, and a clock failure whose detail it does
  not know still counts.
- **The clock's timing and IRQ8 go unproved then.** The clock test stops at its first
  failure, so a board passed this way has not shown that its clock keeps time, or
  that IRQ8 reaches the second interrupt controller. That is accepted: the rest of
  the board was tested.
- **A computer shows its motherboard's Verified.** A computer with a verified
  motherboard fitted in it is marked as the board is, and its Details say which board
  and when (`Its motherboard, RH-XQZ7: 2026-11-20, with TINYDIAG 0.14.0`). The mark is
  still the board's: it goes when the board is taken out or stops being verified, and
  the computer's history says nothing of it. A machine whose board is part of its own
  record carries it as before.
- **The mark is a blue check**, beside the title on the item's page, and beside the
  name in the gallery (tiles, table and searches), on **Every item**, in a machine's
  list of parts and on a catalogue model's page. It replaces ADR-0055's green chip,
  so the mark looks the same wherever it is. It is blue in every preset, from two
  colour tokens of its own (`tick` and `on-tick`) held to the contrast pairs like
  every other colour, and says "Verified" to a screen reader and on hover.
- **Surveys already taken are judged again** by the same rule (migration 0052).

## Consequences

- Migration 0052 works out every survey's `board_result` again with the clock's
  battery left out. On the register as it stands, that verifies the Tulip TC16
  (RH-E02E) and the PC2086's board (RH-0M34), without a line in their histories, as
  0051's backfill did.
- `DETAIL_RTC`'s wording is now read, as `DETAIL_RAM`'s is. If tinydiag reports the
  battery in a key of its own one day, read that first.
- A board verified with a flat battery loses its settings when it is switched off.
  Verified says the board works, not that it keeps the time, and the survey's page
  says the battery was left out.
- The check is the one mark of the feature. The words that go with it are in the
  item's Details, the survey's **Board tests** row and the receipt at the machine.
