# 0047 — A computer maker's BIOS names the board and the machine

**Status:** Accepted
**Date:** 2026-11-07
**Amends:** [ADR-0044](0044-a-survey-asks-the-make-and-model-of-what-nobody-can-name.md)

## Context

ADR-0044 named what a survey finds by what the thing says of itself, and asked
the make and model of anything that says nothing. A motherboard was named only by
a later PC's SMBIOS tables, and a machine the same way. Before SMBIOS (most of a
retro collection) every board and every new machine was asked.

The first real survey was a Compaq 286 from 1989. The survey program reported
`BIOSVENDOR=Compaq`, and the register's own reading of the BIOS's copy said
Compaq too, yet the machine was made with no maker and its board would have been
asked its make. A Compaq BIOS is only ever on a Compaq board: Compaq wrote it. So
did IBM, Amstrad, Olivetti, Tandy, Zenith, Toshiba and Commodore. HP and Dell had
Phoenix write theirs and put their own name in it. The rest of the PC world ran
BIOSes from AMI, Award, Phoenix, Quadtel, MR BIOS or Chips and Technologies,
which say nothing about whose board they are on.

## Decision

**A BIOS from a computer maker names the maker of the board and, unless somebody
says otherwise, of the machine.** The makers are those who wrote their own (the
eight above, as the survey program or the BIOS's own text names them) and those
whose name is in a BIOS somebody else wrote (HP and Dell, by their copyright in
the text). The BIOS houses name nobody.

- **The BIOS's copy is believed over the survey program.** The register reads the
  BIOS house first, so a clone BIOS with `COMPAQ` in it for compatibility is a
  BIOS house's and names nobody. The survey program's own reading is used only
  when no copy came.
- **A new board is named by that maker**, where SMBIOS does not name it, so it is
  not asked its make and model at the machine. A board on record with no
  manufacturer has it filled in.
- **A new machine is offered that maker** at the Make prompt, through a new key in
  the answer to the question, `SYSTEM_MAKER`, which is what Enter keeps (SMBIOS's
  maker where it gives one). A machine with no manufacturer recorded has it filled
  in when nothing was typed and SMBIOS gives none.
- **It never changes or contradicts a manufacturer already recorded.** A badge can
  differ from the BIOS: an AT&T 6300 is an Olivetti inside, and a Sinclair PC200
  an Amstrad. So a BIOS's maker fills an empty field and is never shown as a
  difference from a full one, as SMBIOS's strings are.

The board's model is left empty. A Compaq system board's model is a part number
on the board that nobody at the keyboard knows, and inventing one (`System
board`) would be a name nobody gave it.

## Consequences

- A Compaq, an IBM or an Amstrad surveyed with somebody at the keyboard comes out
  with its board named and its machine's maker offered, and nobody types either.
- A badge-engineered machine is offered the wrong maker. The person at the
  keyboard types the badge, and a survey with nobody there writes the BIOS's
  maker into an empty field, where it is put right on the form.
- The survey program needs to show `SYSTEM_MAKER` at its Make prompt. One that
  does not ignores the key, and Enter there still leaves the maker to the
  register.
