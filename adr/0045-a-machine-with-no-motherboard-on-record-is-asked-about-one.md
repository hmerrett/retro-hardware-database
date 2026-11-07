# 0045 — A machine with no motherboard on record is asked about one

**Status:** Accepted
**Date:** 2026-11-07
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

A PC is described by what is fitted in it (MANUAL §1), and the motherboard is
where a survey writes most of what it learns: the BIOS's maker, version and date,
the chipset the PCI bus names, the board's serial number from SMBIOS, and the
lines of anything answered as built in (onboard video, onboard ports). A
branded machine whose catalogue model has a BIOS socket keeps its BIOS on its own
record instead (an IBM 5150's BIOS ROM).

A survey never made a motherboard. A machine made by **N** at the machine was a
computer with nothing fitted, and so was any machine catalogued by hand without
its board. For those, a board's lines were remembered and nothing was written,
and the BIOS's ROM was kept with the machine. The owner asked for the survey to
offer the board as well, so the BIOS has somewhere to go.

## Decision

**The motherboard is one more thing a survey finds**, in any report that speaks
for a board: a BIOS date or maker, a BIOS ROM, a chipset, or SMBIOS's board
strings. It is answered like a hard disk: a part of its own (a tag, or **N** for
a new one) or left out (**X**, for none). It cannot be part of the machine:
that is what the catalogue's sockets are for. At the machine it is asked first
among the things.

**It is asked only of a machine with none on record.** The register answers it
itself where it can: the board fitted in the machine; the board itself, for a
bare board surveyed on its own; `MACHINE` for a machine whose catalogue model
keeps its BIOS in a socket of its own; a board the register has, known by the
serial number SMBIOS keeps (moved in from a shelf as any part would be); then the
answer remembered for the machine. **X** is remembered, so a machine with no
separate board is asked once.

**A board named by its tag must be a motherboard.** Any other tag typed for it
is not an answer.

**A new board is named as other new parts are** (ADR-0044): by SMBIOS's board
maker and model where both say something, and otherwise by the make and model
typed at the machine. It carries the board's serial number. It is fitted in the
machine, and in the same survey the BIOS, the chipset, the built-in lines and
the BIOS's ROM go on it. A board made later, from the survey's page, gets the
same, and the BIOS's ROM moves from the machine to it.

**A loose board known by its serial says this is that board only when nothing
was typed.** With nothing typed it is a bare board on the bench being surveyed.
With a machine's tag, or **N**, it is a board being put in that machine, and it
disagrees with nothing.

## Consequences

- A new PC surveyed with somebody at the keyboard comes out as a machine with
  its motherboard fitted and filled in, which is how the register describes a
  PC.
- One more question for a machine with no board on record, asked once. A
  survey with nobody at the keyboard waits on the Surveys page for it.
- A board's serial number is the board's once it is a part, rather than the
  machine's, in what surveys have seen.
