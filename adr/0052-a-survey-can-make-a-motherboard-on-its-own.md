# 0052 — A survey can make a motherboard on its own

**Status:** Accepted
**Date:** 2026-11-08
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md), [ADR-0045](0045-a-machine-with-no-motherboard-on-record-is-asked-about-one.md)

## Context

A board is often tested on the bench before it goes into a case: the bench's own
cards plugged into it, a survey run, and the board put away or built into
something later. ADR-0045 lets a survey file against a bare board, but only one
the register already has: its tag typed at the machine, or a later board's BIOS
serial number on record. **N**, the only way a survey makes something to file
against, always makes a computer, so a board the register did not have yet came
out of the survey as a whole machine. The owner asked for a way to make the board
instead, and chose to have it both at the machine and on the Surveys page.

## Decision

**B at the machine makes a new motherboard, and the survey is filed against it.**
The tag prompt offers it beside **N** (`Machine's tag, N new machine, B new board,
Enter later:`), and the report says `TAG=NEW BOARD`.

- **Named as a new board in a machine is.** By its SMBIOS tables where they name
  it, else by the computer maker whose BIOS it is (ADR-0047), else by the make and
  model typed at the machine, which it asks for as it asks a new machine's
  (`BOARD_MAKER`, `BOARD_MODEL`). Its serial number is its BIOS's, if it keeps one.
- **Filed as a bare board is** (ADR-0045): its BIOS, chipset, serial number and
  condition, its BIOS ROM, and the things found in it answered as they are for a
  bare board typed by its tag. The survey's own motherboard finding is the board
  itself, so it is not asked.
- **Nowhere until it is put away**, as a new machine is. The register does not
  know which bench the survey ran on, and a board put directly on one would be
  the bench's own kit (ADR-0046), which a survey never fits or moves.
- **Enter does not mean N on it.** In a new machine, Enter makes a new part,
  because everything in it arrived with it. What is plugged into a bare board on
  the bench is often there only for the test, so on a new board Enter leaves each
  thing for later, as it does anywhere else.
- **It disagrees where N does, and once more.** Anything inside that the register
  has in a machine stops it, as it stops N. So does a motherboard the register
  already has, known by its serial number: with N that is a board going into the
  new case, but with B it is the board itself, which B would add twice.
- **Its label is offered** as a new machine's is (ADR-0049).

**On the Surveys page, New motherboard** sits beside **New computer** on a survey
waiting for its machine. It opens the form for a new part set to a motherboard,
with what the survey found of the board already in it (its make, model and serial
number), and saving it files the survey against the board, as typing its tag
would have.

The survey program only offers B. The register decides the rest, as it does for
N, so an older register given `TAG=NEW BOARD` takes it for a tag it never issued
and the survey waits rather than making anything.

## Consequences

- A board tested on its own is a board from its first survey, never a machine
  that has to be undone.
- Two words in the report mean something new to make (`NEW`, `NEW BOARD`), and the
  register has to be deployed before the survey program that sends the second.
- A board made by B with something plugged into it that the register has in a
  machine waits for an answer, as a machine would, rather than guessing.
