# 0054 — A survey corrects a memory total an older survey wrote short

**Status:** Accepted
**Date:** 2026-11-20
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

ADR-0043 has a survey fill what is empty and change nothing else, because a record
somebody typed is the authority on the machine. A survey writes a machine's memory
as a plain total, when nothing about its memory is recorded: the conventional memory
and the memory above 1 MiB added up, and rounded up to whole MiB where there is any
above 1 MiB.

tinydiag 0.13.0 and earlier sent no figure for the memory above 1 MiB when HIMEM.SYS
was loaded. The surveys it took wrote the conventional memory alone as the machine's
total: 639 KiB for a 16 MiB PC. 0.14.0 sends the figure, and says where it came from
(`EXTKB_FROM`). Under ADR-0043 every later survey of those machines shows 639 KiB
recorded and 16 MiB found, and the total stays wrong until somebody types the right
one in, machine by machine. The owner was asked, and chose to have surveys correct
these totals.

## Decision

**A survey corrects a memory total only when all three hold:**

- the total recorded is exactly the conventional memory this report gives (`RAMKB`),
  which is what a survey that could not see above 1 MiB wrote;
- this report finds memory above 1 MiB (`EXTKB` more than nothing);
- the record is a bare total, with no modules, no chips and no note, which is how a
  survey writes one.

It then writes the total this survey works out. Its history line says `Corrected
memory from 639 KiB to 16 MiB` rather than `Filled in memory`, and the survey keeps
what it corrected beside what it filled in and what differed, so its page and its
receipt say so too.

**Everything else recorded is still never changed.** A total that is not the
conventional memory found is a difference, shown and left alone. A total with
modules, chips or a note is somebody's account of what is fitted, and is left alone
even where it comes to the conventional memory. A machine with nothing above 1 MiB
(an XT, a 286 with 640 KiB) is never corrected: its conventional memory is its total.

The register cannot tell a total an older survey wrote from the same total typed by
hand: a survey did not mark what it wrote. That was weighed and accepted. On a
machine with memory above 1 MiB, a bare total of its conventional memory alone is
short whoever wrote it, and the three conditions keep everything else out.

## Consequences

- The manual's "it never changes something already recorded" carries this one
  exception, spelled out where a survey's memory is described.
- A survey has a list of what it corrected, beside what it filled in and what
  differed: a column on `surveys`, `corrected`, a JSON list like those two, empty for
  every survey taken before it (migration 0050). Neither existing list would do:
  what was filled in was empty, and what differs was left alone.
- It is one rule for one known fault, not a licence to correct. Another value a
  survey program got wrong needs a decision of its own, held as narrowly: a value the
  register can tell the faulty program wrote, and a reading that shows it wrong.
- Once every machine surveyed under HIMEM.SYS by 0.13.0 or earlier has been surveyed
  again, the rule has nothing left to do. It can stay: wherever it applies, the total
  it corrects is wrong.
