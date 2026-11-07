# 0048 — A survey asks about every drive it finds

**Status:** Accepted
**Date:** 2026-11-07
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

The manual's section on drives splits them in two. Hard disks and tape drives
are tagged parts, because they have serial numbers and move between machines.
Floppy drives, Goteks, optical drives and SD/CF adapters are rows on the
machine's record, as a property of how it is set up. ADR-0043 followed the split:
a survey wrote floppy drives, CD-ROM drives and CompactFlash cards into the
machine's Drives list (when the list was empty) and never asked about them.

The collection does not follow the split. It holds 65 floppy drives as tagged
parts, 10 of them fitted in machines, beside 33 drive rows on others. A survey of
any of the 8 machines with a fitted floppy drive and no rows would have recorded
that drive a second time, as a row. And a CD-ROM drive or a CompactFlash card
reports a model and a serial number, as a hard disk does, which a survey read and
threw away. The owner asked for floppy drives to be parts, and for CD-ROM drives
and CompactFlash cards to go the same way.

## Decision

**A floppy drive, a CD-ROM drive and a CompactFlash card are things a survey
asks about**, with all three answers: a part of its own (a tag, or **N**), part
of the machine (**M**, which is a row in its Drives list), or left out (**X**).

- **A CD-ROM drive and a CompactFlash card are known by their serial numbers**,
  wherever they turn up, as hard disks are, and say which machine they are in.
- **A floppy drive is known by its size**, in the same machine, as a disk the
  BIOS knows only by its size is. It says nothing about its make or model, so
  **N** asks them at the machine (ADR-0044).
- **What the register already has is not asked.** A row in the machine's Drives
  list of the same kind and size is that drive, as part of the machine, and a
  part fitted in it of the same kind is that part, unless its serial number says
  otherwise. Each row stands for as many drives as it counts. A drive matching
  neither is asked about, which is also how a survey reports a drive that is not
  the one recorded.
- **M writes a row**, unless a row already stands for the drive.

**Only surveys change.** The part form still files a floppy drive, an optical
drive or an SD/CF card added inside a machine as a row, so the register has two
rules side by side: what a survey finds can be a part, and what is typed in is a
row. The owner chose that over changing the form, and the manual says both.

**Rows already recorded stay rows.** Nothing turns the 33 existing rows into
parts; a survey takes each for the drive it describes. A row becomes a part when
somebody tags the drive.

## Consequences

- A new PC surveyed with somebody at the keyboard can come out with its floppy
  and CD-ROM drives tagged and named, with nothing recorded twice.
- More questions at the machine for a machine whose drives were never written
  down: one for each drive, asked once.
- The survey program has to offer floppy drives, CD-ROM drives and CompactFlash
  cards as things to answer; one that does not leaves them waiting on the
  Surveys page.
- Two rules for one kind of drive: the manual's section on drives says which is
  which, and a later decision may bring the part form into line.
