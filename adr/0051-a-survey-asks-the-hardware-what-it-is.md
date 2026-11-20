# 0051 — A survey asks the hardware what it is

**Status:** Accepted
**Date:** 2026-11-07
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md), [ADR-0050](0050-a-survey-asks-about-what-it-could-not-see.md)

## Context

A survey finds a card by its ROM or on the PCI bus, and since ADR-0050 a Sound
Blaster, an AdLib and expanded memory by asking for them. DOS diagnostic programs
of the time found a great deal more, and the owner asked how, and whether more of
it could be known by something unique, as a network card is by its Ethernet
address. They asked the hardware itself, in four ways:

- **Plug and Play isolation.** Every Plug and Play ISA card gives its maker's
  code, its model, a 32-bit serial number and, nearly always, a name of its own,
  through three ports every Plug and Play BIOS and driver uses.
- **DDC.** A monitor made since about 1994 describes itself (EDID: its maker,
  model, serial number and more) to a video BIOS that can ask, through VESA's
  INT 10h AX=4F15h.
- **The chip's own registers.** A VGA chip has registers no other chip has, so a
  card whose ROM does not name it can be named by its chip, the way whatvga,
  svgalib and XFree86 named them.
- **Port probes.** A serial port's chip, a parallel port's mode, a Gravis
  UltraSound's sound memory, an MPU-401's reset.

The owner chose all four.

## Decision

**The survey program reports what each answers, and the register makes findings
of them.** Each is a thing like a card (a part of its own, built into the
motherboard, or left out), except a monitor.

### Plug and Play cards

`PNP1=CTL0045 1A2B3C4D` (the card's ID and serial number), `PNP1_ANSI=Creative
SB AWE64 PnP` (its own name) and `PNP1_IO=0220 0330 0388` (the first port of each
of its first four devices that is switched on).

- **Read where they were set up.** Where the BIOS is a Plug and Play BIOS, it says
  which port it reads the cards through and how many it numbered, and each card is
  woken by its number and read, which changes nothing. Without one, the cards are
  isolated as a driver would, which numbers them again (in the same order, which
  their serial numbers decide) and never resets what a driver configured. It
  reads them through 20Bh, else 27Bh, which nothing else common answers at. They
  are put back to waiting for the key either way.
- **Known by its ID and serial number** wherever it turns up, as `pnp` among the
  serial numbers seen, and so says which machine it is in, as a disk does. Many
  cards answer FFFFFFFF or 0, which says nothing, and one of those is known per
  machine by its ID. The serial number is not written into a part's **Serial
  number**: it is printed on no label, so it is not what that field holds.
- **Named** by its maker's code, from a table of the codes that made cards, and
  by its own name with the maker's word taken off (`Creative Labs`, `SB AWE64
  PnP`).
- **One card, not two.** A `SOUND`, `ADLIB`, `MPU` or `GUS` at one of a card's own
  ports is that card and not a finding of its own. A Plug and Play card whose name
  says it is a network card is the network card, where the survey runs through one
  that is not on the PCI bus and only that one says so: it names the card. The
  register's answer tells the machine which (`SOUND_ANSWER=PNP1`, `PNP2_ANSWER=NIC`,
  and `MPU_ANSWER=SOUND` for a Sound Blaster 16's), and the survey program, which
  takes any answer as settled, does not ask about it twice.

### Monitors

`EDID1=` to `EDID4=`: the 128 bytes the monitor gave, in hex, 32 to a line so
that each line of the report fits the machine's screen. The survey program asks
only on a VGA whose BIOS answers VESA's AX=4F00h, and sends the block unread; the
register reads it, and refuses one whose header or checksum is wrong.

- **A part of its own, or left out.** A monitor is never part of a motherboard, so
  M is not offered. A new one is a **Display** part with its maker (from its code,
  through the same table), its model (its name, with the maker's word taken off)
  and its serial number.
- **Known by its serial number**: the one written out in its EDID where it gives
  one, else the number, unless that is 0 or 01010101h, which many give. Recorded as
  `monitor` among the serial numbers seen, with its maker's code and model first,
  since two makers' numbers can be alike. One with neither is known per machine.
- **It does not say which machine it is.** A monitor is moved from machine to
  machine more often than a disk, and a bench's monitor is the bench's (ADR-0046).
  Where it is found in a machine other than the one it is fitted in, it waits, as
  any part does.

### The video card's chip

`VIDEO_CHIP=TSENG 40`: the family whose test answered and the ID it read, in
hex, only on a VGA with no display device on the PCI bus. The register holds the
tables that turn that into a name (`vgachips.py`), since the survey program has
48K to fit in. The tests are SuperProbe's, XFree86's and whatvga's, in the order
they settled on so that one cannot misfire on another family's chip: first what
needs no register written (ATI's BIOS signature, and the Video Seven and Chips
and Technologies BIOS calls), then the tests where a register must refuse a write
while locked and take one unlocked (Western Digital and Paradise, Trident, S3,
Cirrus Logic, Genoa's signature, Compaq), then Tseng Labs, then Oak. Every register
written is saved first and put back, with interrupts off and the index registers
restored. Two cannot be read back: a Trident chip is left in the register mode its
own software uses, and a Tseng Labs chip's extensions are locked again (3D8h=29h,
3BFh=01h), as XFree86 left them. 3BFh is a Hercules card's setting too, so the
Tseng test is not run beside a second display adapter.

The register names the video card by it (`Tseng Labs ET4000`) where neither the
PCI bus nor the ROM does, and makes a new card of it with the chip's maker and the
chip. The chip is never part of what the video card is known by, so an answer
given before it was read still holds.

### Ports

The serial port test already said which chip each port has (`COM1=03F8 16550A
IRQ4 ...`). The parallel port test now says whether a port is an ECP port (its
extended control register answers as one does) or a bidirectional one (its data
lines stop driving when told to), as `LPT1=0378 ECP ...` or `LPT1=0378 BIDIR ...`.
Both go into the ports'
line, a chip or a mode to an entry (`2× Serial (16550A), Parallel (ECP)`), and into
nothing they are known by, so ports answered before are not asked again.

### A Gravis UltraSound and an MPU-401

`GUS=0240 1024` (its port and its sound memory, in K) and `MPU=0330`. The
UltraSound is found as Gravis's own software found one, by resetting it and
writing to its sound memory, at 220h, 240h and 260h; the MPU-401 by its reset at
330h. Those writes go to ports a network
card on the ISA bus can be set to (320h-37Fh), and the survey reports through its
network card, so both are probed only where that card is on the PCI bus. An
MPU-401 beside a Sound Blaster whose DSP is 4 or later is the Sound Blaster 16's
own. An UltraSound is named as itself; an MPU-401, like a Sound Blaster, is asked
its make and model.

### What is not looked for

**A game port.** It reads the same as no port at all until a joystick is plugged
in, and it is the sound card's as often as the I/O card's, so there is nothing to
record that would be true.

## Consequences

- A survey names many more cards without asking, and knows a Plug and Play card
  and a monitor the next time wherever they turn up.
- A sound card answered before as `SOUND` on a Plug and Play card is asked about
  once more, as the card it is. Typing its tag joins the two.
- Isolation renumbers the cards on a machine with no Plug and Play BIOS. Every
  driver isolates or reads the numbers afresh, so nothing that runs after the
  survey depends on them.
- Each chip test writes to the video card and puts it back. A card unlike any
  the tests were written for could misread one, which names it wrongly, and the
  name is only a suggestion until somebody answers.
- QEMU has no Plug and Play card, no MPU-401 and only two of the chips (Cirrus
  Logic's, and the plain VGA that is none of them), so those paths are first
  proved on the owner's machines.
