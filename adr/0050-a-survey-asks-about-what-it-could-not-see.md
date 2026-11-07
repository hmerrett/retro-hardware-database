# 0050 — A survey asks about what it could not see

**Status:** Accepted
**Date:** 2026-11-07
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

A survey asks about what it finds. The first Compaq surveyed with drives as parts
had a sound card and an Everex memory card in it, and the survey found neither:
an ISA sound card has no ROM and no PCI number, and a memory card shows itself
only through its driver. Nothing at the machine asked about them, and a part the
register already had in a machine was never mentioned unless the survey found
it.

The owner asked for three things: the survey should ask about the parts the
register has in the machine that it did not find, ask for anything else fitted,
and look for sound cards and expanded memory itself, carefully.

## Decision

**After the things it found, a survey asks about what it could not see.**

- **Parts on record it did not find.** The register's answer to the question
  names each part fitted directly in the machine that no answer accounts for
  (`KEPT1=RH-4K7Q Sound Blaster Pro`). The machine shows each: Enter if it is
  still fitted, **X** if it has been taken out. X comes back as `GONE1=RH-4K7Q`
  and the register takes the part out of the machine, by survey, leaving it with
  no location until somebody puts it away. Only a part directly in this
  machine is taken out.
- **Anything else.** Asked again until Enter: a tag (`EXTRA1_ANSWER=RH-…`),
  which is fitted as a tag typed for anything found is, or **N** with a make
  and model (`EXTRA1_ANSWER=NEW`, `EXTRA1_MAKER`, `EXTRA1_MODEL`), which makes a
  part of type *other*. Nothing about these is remembered: next time a tagged
  one is on record, and so among the parts on record.
- **Sound and expanded memory are looked for.** The survey program resets a
  Sound Blaster's DSP at 220h, 240h, 260h and 280h and reads its version
  (`SOUND=220 3.02`), checks an AdLib's timers at 388h (`ADLIB=388`), and asks an
  EMS driver for its size (`EMS_KB=2048`). Each is a thing like a card: a part of
  its own, built into the motherboard, or left out, remembered per machine. A
  sound card is never named by its DSP, since a clone answers as the original
  does, so **N** asks its make and model. Expanded memory on a 386 or later is
  EMM386's, made by the processor, and is not a finding.

**In a machine being added, Enter is N.** Everything in a new machine is new, so
the survey program takes Enter for a new part there instead of for later.

**M says where it goes.** For a card, the video and the ports it is "on the
motherboard", which is where their lines are written; for a drive it stays
"part of the machine", a row in its Drives list.

## Consequences

- A survey with somebody at the keyboard accounts for what the register has in
  the machine and can add what the program cannot see, at the machine.
- Every survey of a known machine asks once about each part it cannot find, a
  power supply included. Enter is the answer for each that is still there.
- Resetting a Sound Blaster writes to its ports. A card of another kind at those
  addresses could be disturbed; the reset is the one every DOS game used.
