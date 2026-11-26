# 0055 — A motherboard whose own tests pass is verified

**Status:** Accepted
**Date:** 2026-11-25
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

A survey marks a machine **Working** when every test that applies passed (ADR-0043).
That is a statement about the whole machine, and it is easily missed for reasons that
have nothing to do with the board: a floppy drive that failed, a keyboard that was not
plugged in, a loopback plug a parallel port wanted. It also says nothing about which
part of the machine was proved.

The owner asked for a mark on a motherboard whose own functions a survey has tested
and passed: "if core motherboard and RAM functions pass, we should automatically get
this verified tag", without the keyboard and the peripherals. tinydiag runs seventeen
tests. Eleven are of the board's chips and its memory, and six are of cards and
peripherals. Asked, the owner chose the board's chips and all of the memory (the clock
included), the keyboard controller left out with the keyboard, a later failure taking
the mark away, and the mark public.

## Decision

**A motherboard is Verified when the newest survey of it that tested its board passed
every board test.**

- **The board tests** are tinydiag's `TICK`, `CPU`, `FPU`, `ROM`, `PIT`, `DMA`, `PIC`,
  `NMI`, `RTC`, `RAM` and `RAMSYS`. Each must pass, or not apply to the board (no
  coprocessor fitted, no clock on an XT, a BIOS that keeps no checksum), and the two
  memory tests must pass. The option ROMs, the ports, the keyboard, the video memory
  and the floppy (`OPTROM`, `COM`, `LPT`, `KBD`, `VRAM`, `FDC`) are cards' and
  peripherals', and do not count.
- **The keyboard controller is left out with the keyboard.** tinydiag tests the 8042
  inside its keyboard test, and stops before the 8042's own registers and A20 when no
  keyboard answers, which is how a bare board on the bench is often tested. A20 is
  still proved where it matters: the memory above 1 MiB is reached through HIMEM.SYS,
  which does not load without it.
- **All of the memory.** Where the BIOS counts memory above 1 MiB (`EXTKB`), the RAM
  test must have reached all of it through the XMS driver, less the 64 KiB of the HMA,
  which may be DOS's. tinydiag 0.14.0 says how much it reached only in `DETAIL_RAM`
  (`516K, 15156K XMS, HMA: March-U, bus ok`), so that is where it is read. A processor
  before the 286 has no memory above 1 MiB. A report from a 286 or later with no
  `EXTKB` cannot say whether there was any, and has not shown all of it tested.
- **A failure takes it away, and a survey that did not test the board says nothing.**
  A survey with a board test failed has failed the board, whatever else it ran. One
  with a board test skipped, not run or missing, or with memory above 1 MiB it did not
  reach, leaves the board as it was. Of the surveys that decided, the newest by when it
  was taken counts, so a survey filed late does not outvote a newer one.
- **What carries it** is the motherboard the survey is filed against: a board surveyed
  on its own (its tag typed at the machine, or **B**), or the board fitted in the
  machine. A machine whose board is part of its own record (a catalogue model with a
  BIOS socket of its own, as an IBM 5150 has: ADR-0045 writes that board's BIOS on the
  machine) carries it itself. A machine with no board on record verifies nothing until
  a board is given for it on the survey's page, and a survey waiting for its machine
  verifies nothing until it is filed.
- **It is read from the surveys, not kept on the board.** Each survey keeps the verdict
  of its board tests and the board they were of, and a board's Verified is the newest
  verdict about it. So deleting a survey takes away what it said, and changing a
  survey's answer for its motherboard moves what it says to the board given.
- **It is public**, like Condition and the survey's line in the history: the mark, when
  the survey was taken, and the program and version that ran the tests (`TINYDIAG
  0.14.0`). The survey itself stays with people signed in, as every survey does.
- **The board's history says when a survey changes it**: a line when a survey verifies
  it and when one takes that away, dated when the survey was taken. Deleting a survey,
  or giving its motherboard answer to another board, writes nothing.

## Consequences

- Two columns on `surveys` (migration 0051): `board`, the board its tests were of, and
  `board_result`, `PASS`, `FAIL` or empty. The migration fills both for every survey
  already taken, so a board whose newest deciding survey passed is verified from the
  start, without a line in its history.
- Verified and Working are separate. A board in a machine whose floppy failed can be
  verified, and a machine can be Working without a verified board: its memory above
  1 MiB went untested, or it has no board on record.
- `DETAIL_RAM`'s wording is now something the register reads, and the manual's report
  table says so. A key of its own would be better: if tinydiag adds one, read it first
  and keep the detail for reports that have no such key.
- The test names are tinydiag's. Another survey program verifies nothing until it names
  its board tests the same way.
- If tinydiag reports the 8042 as a test of its own one day, run with or without a
  keyboard, it can join the board tests where a report has it. That would need a
  decision of its own.
