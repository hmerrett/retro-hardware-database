# 0044 — A survey asks the make and model of what nobody can name

**Status:** Accepted — amended by [ADR-0047](0047-a-computer-makers-bios-names-the-board-and-the-machine.md)
**Date:** 2026-11-07
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

A survey makes a new machine or a new part when somebody presses **N** at the
machine (ADR-0043). The record is named as the thing names itself: an IDE disk by
the model string IDENTIFY returns, a card on the PCI bus by its chip, a card by
the banner in its ROM, a later PC by what its BIOS keeps (SMBIOS). Plenty of
things name nothing. An XT's MFM disk is known to the BIOS by its size alone. A
multi-I/O card has no ROM. An 8-bit network card's packet driver says NE2000,
which is the protocol it speaks. Most machines older than about 1996 have
no SMBIOS, so a new machine made of one was a bare tag with a CPU and some memory.
Each needed its make and model typed in afterwards, from a label the person had
been looking at when they pressed N.

Two places could decide what has a name. The survey program is on the machine,
and knows only what it read: numbers on the PCI bus, a video class, an address.
The register keeps the PCI table, reads ROM text, and knows which SMBIOS strings
are placeholders. A program deciding alone would ask about every PCI card the
register could have named, which is the touch the survey exists to remove.

The register could not name a card from its ROM before the tests, because the ROM
copies reached it only with the report. A question carried the ROMs' addresses
and sizes, not what was in them. The same gap left netboot 0.8.1's boot ROM, the
one the owner's machines start from, as a card of its own to be answered in every
machine: its only plain text is its author's copyright line, and it carries
neither a PCI class nor a Plug and Play device type for the survey program to
recognise it by.

## Decision

**The agent sends the ROMs with the question.** The question names its ROM
copies (they are written before it), so the agent attaches those files, from the
question's own folder, exactly as it does for a report. An older agent's
plain-text question is still answered. Asking still writes nothing: the ROMs are
read for their text and kept nowhere.

**The register names what it can, in the answer.** `<THING>_NAME` for each thing
it can name, and `SYSTEM_NAME` for a machine whose BIOS names it usably. A name
comes from what the thing says about itself and nothing else: the PCI table where
it knows both maker and chip, a ROM's banner line naming a maker, a disk's own
model string. A thing it can only describe (a card with a ROM at C800, VGA, the
ports, a disk the BIOS knows by size) has no name line. A ROM line naming a maker
that is not a banner is one of the messages the ROM prints, and names nothing.

**The register recognises a network boot ROM by its text** where the survey
program could not, and says which it is (`NIC_ROM=`). The program then counts it
with the network card, as it would one it had recognised itself, so a bench
card's boot ROM is asked about nowhere. Only one such ROM, and only in a machine
whose card a packet driver ran.

**The machine asks the make and model of what will be new and has no name.**
After **N** for a thing with no name, and after **N** for the machine unless its
BIOS names it. Enter leaves either out. Nothing else is asked: a tag typed, M, X
and Enter never lead to it, and with nobody at the keyboard nothing is asked at
all, as before.

**What was typed names the record and nothing else.** It goes in the report as
`<THING>_MAKER` and `<THING>_MODEL` (`SYSTEM_MAKER` and `SYSTEM_MODEL` for the
machine, which are asked only when the BIOS's were unusable). It fills the new
record's **Manufacturer** and **Model**. It is never part of how a thing is known
next time: a thing with no serial number is remembered by what it says about
itself, and a typed name is what a person said.

**A survey does not choose a catalogue model from a typed name.** The catalogue
names models its own way ("PC XT" for a 5160), and adopting one is a choice
`tools/adopt_machines.py` asks a person to confirm. Once the machine has its
model, the next survey fills in the BIOS socket and the rest without asking.

## Consequences

- A machine surveyed for the first time is asked about what it is once, at the
  moment someone is looking at it, and the new records are named when they are
  made.
- The question is now a multipart request when there are ROMs, and the agent and
  the register move together: an agent from before this change sends its
  question as text, and is answered without the names only a ROM could give.
- Names are the register's, so improving them (a device added to the PCI table, a
  maker to the list ROM banners are read for) changes what the machine is asked,
  with nothing to change in the program on the machine.
- A card's name from its ROM now needs a banner line. A ROM whose only words
  naming a maker are a message it prints is a card with no name, and is asked
  about, where before it was named by the message.
