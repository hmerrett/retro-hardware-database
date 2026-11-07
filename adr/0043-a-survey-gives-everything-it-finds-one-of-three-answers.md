# 0043 — A survey gives everything it finds one of three answers

**Status:** Accepted — amended by [ADR-0044](0044-a-survey-asks-the-make-and-model-of-what-nobody-can-name.md), [ADR-0045](0045-a-machine-with-no-motherboard-on-record-is-asked-about-one.md), [ADR-0046](0046-only-what-is-directly-on-a-bench-is-the-benchs.md), [ADR-0048](0048-a-survey-asks-about-every-drive-it-finds.md), [ADR-0049](0049-a-survey-offers-to-print-the-labels-of-what-it-makes.md) and [ADR-0050](0050-a-survey-asks-about-what-it-could-not-see.md)
**Date:** 2026-11-06
**Amends:** [ADR-0034](0034-a-location-is-a-record-in-the-register.md)

## Context

Everything in the register is typed in by hand, from the label on the case and
what can be seen with the lid off. A PC can say a great deal of that about
itself: its BIOS and the date in it, its processor and speed, its memory, each
IDE disk's model and serial number, the Ethernet address of the card it was
started from, and on a later PC the maker, model and serial numbers its BIOS
keeps (SMBIOS) and every card on its PCI bus. Its ROMs can be copied, and they
are full of text that names chips and makers.

The old route was a boot floppy running HWiNFO or MSD, carried back to a
computer and read by `tools/import_report.py`. That proposes fills, cannot
recognise anything it has seen before, and makes a new storage part for every
drive in every report, so importing the same machine twice adds its disk twice.

The owner's machines now start from a boot network, through a network card that
goes into every machine on the bench in turn, and a diagnostic of their own
already ends its report with a `[RHDB]` block of `KEY=VALUE` lines. What is
wanted is close to no touch at all: start the machine, walk away, and find its
record filled in. The touches the owner will accept are typing a tag that is on
a label, and asking for a new tag where there is none.

The forces:

- A record somebody typed is the authority on that machine. A survey must not
  quietly overwrite it, nor add the same disk twice.
- The register already has rules for what is a tagged part and what is a line
  on a machine's record ("Two ways of describing a machine", and the drives
  rule: hard disks are parts, floppy drives are rows). A survey has to land
  things where those rules put them.
- Hard disks and network cards can say which one they are. Most other things
  (a video card, the ports) can say what model they are and nothing more.
- The machine side runs on an 8088 with no TLS. It cannot talk to the register
  itself.

## Decision

**A survey is a report, and an agent carries it.** The survey program writes a
report ending in an `[RHDB]` block. An agent on a computer that can read the
folder the reports land in sends them, and asks the register questions on a
machine's behalf before its survey starts. This is ADR-0025's shape: the agent
opens every connection, holds a key of its own (`RHDB_SURVEY_AGENTS`), and the
key opens nothing else. It can send surveys, and ask what the register knows
about the identifiers and findings it already holds. It cannot list or read
anything. With no agent named there are no surveys.

**Everything a survey finds gets one of three answers, and the machine is one
the register has or a new one.** A finding is *left out* (nothing is made of
it), *part of the machine* (written into the machine's own record or its
motherboard's), or *a part of its own* (a tagged part fitted in the machine,
existing or new). This is the owner's model. It is also the register's two ways
of describing a machine, applied to what a machine says about itself, so
nothing a survey records is a kind of thing the register did not already hold
(ADR-0007).

**The register's own rules decide which answers fit, and give most of them.**
The processor and its coprocessor, the memory, the operating system, the BIOS,
the chipset, the machine's own maker, model and serial number, and floppy,
CD-ROM and CompactFlash drives are always part of the machine, and nobody is
asked. A hard disk is a part of its own or left out, as the drives rule says.
The network card, the video card, any other card seen through its ROM or on a
PCI bus, and the ports may have any of the three. Those are asked once, at the
machine (a tag, **N** for new, **M** for part of the machine, **X** to leave
out, or later) or on the Surveys page, and the answer is remembered: by serial
number or address wherever the thing turns up, and otherwise by what it says it
is in the machine it was found in.

**Every serial number and Ethernet address is recorded the first time it is
sent, whatever its answer.** This is the owner's requirement. Each is attached
to what it belongs to (a part, a machine), or kept on its own when it was left
out or not yet answered, with where and when it was last seen. So nothing is
new twice, and *left out* is a remembered answer rather than a question asked at
every survey.

**Which machine it is, is worked out and never guessed.** The tag answered at
the machine comes first, then what is inside it (a disk or a card the register
has in a machine, or a BIOS serial number it holds). Where those disagree, or
point at two machines, or name something that is not a machine, the survey does
nothing and waits. A tag the register never issued is a typing mistake, so a
survey never makes a record under one.

**Nothing new is made without an answer.** A new machine or part comes only from
**N** at the machine, or **New computer** or **New part** on the survey's page.
Unattended, the question waits. Making a part the first time its identifier is
seen was considered, as the owner first suggested for network cards, and
rejected for two reasons. A bench card made into the first machine it starts
would then claim that machine's identity in every later survey taken through
it, and nobody would see the surveys going astray. And a disk catalogued by
hand, whose serial number was never typed in, would be added a second time.
Waiting costs one answer for each new thing, once.

**A survey fills what is empty and changes nothing else.** Where it read
something different from the record, it shows the two side by side. It moves a
known part kept on a shelf, or nowhere, into the machine, as a scan in the audit
does, and records the move as made by survey. It never takes a part out of
another machine, and never moves the machine it is surveying.

**A bench is a kind of location, and what is kept on one is never the
machine's.** This amends ADR-0034, which gave a location's kind no rules at all.
A part kept on a bench, or in something on a bench, is never fitted in the
machine being surveyed, never counted when working out which machine it is, and
never moved. A place was chosen over a tick on the part because it is the
owner's own way of saying it (the card is a bench card because it lives on the
bench) and because it covers a bench disk or a bench video card with no new
field. A machine standing on a bench keeps its own parts, because what is fitted
in something is not kept on the bench.

**Working comes from a full pass, and only over blank or Untested.** The manual
holds that a condition is never guessed. A pass is not a guess: it is the tests,
run. A test that does not apply to the machine does not count against it, and a
skipped one does. A survey never writes **Faulty**, never changes a condition
somebody chose, and leaves the parts' conditions alone, since the tests are of
the machine.

**A ROM is a file: private, one per content, linked to what it belongs to.**
The BIOS goes to the machine or its board, and a card's ROM to the card
(ADR-0028). The same bytes read again are the same file, linked to one more
thing. They start private whatever **New files are public** says (ADR-0009,
ADR-0029): a BIOS is somebody's copyright, and publishing one should be a
decision. The ROM of something left out is not kept.

**The report stays with the survey, and is not a file.** A report for every
survey of every machine would bury the private files list, which is the list of
files that want attention.

**Who sees what.** Surveys, their reports, the list of what surveys have seen,
and the text in ROMs are for people signed in. Ethernet addresses are for people
signed in alone, by the owner's decision: they are kept out of a visitor's
search, page, label and history. A hard disk's serial number, once the disk is a
part, is its public serial number like any other. The history line a survey
writes is public, and carries nothing that is not.

## Consequences

- New records: a survey (its report, what it found and the answer each got, the
  machine, the agent, when), a recorded identifier (its kind and value, what it
  belongs to or that it belongs to nothing, its answer, where and when it was
  last seen), and a machine's remembered answers for findings with no
  identifier. Each is a migration.
- An Ethernet address cannot go in the network card's spec table. That table is
  rendered into `parts.specs`, which is public on the part's page, feeds the
  search and is printed on labels. It needs a place of its own, listed in
  `common.OWNER_ONLY` (ADR-0018), with tests that a visitor's page, search and
  label never carry one, and that no history line does.
- The agent's routes sit under one prefix let through the login gate, with the
  key checked in the route, as `/api/print/agent/` is. `/surveys` is listed for
  viewers to read. The published API shape changes, and is recorded on purpose
  (ADR-0010).
- A location's `kind` gains `bench` in the form and the API, and a move gains
  *by survey* beside edit, scan and the API.
- Naming what a survey finds needs a table of PCI identifiers and a list of the
  placeholders BIOSes write in place of a serial number.
- `tools/survey_agent.py` and its unit file, beside the print agent's. Its
  folder exchange with a DOS machine (`.ASK`, `.ANS`, `.RCT`, `SENT`,
  `REFUSED`, every name 8.3) is its contract with survey programs, and is
  written down in the manual.
- The survey programs (the owner's diagnostic, and the boot network that
  starts it) need the new keys and the question-and-answer exchange. That work
  is in their own repositories.
- `tools/import_report.py` stays for HWiNFO and MSD reports. Where a machine can
  run a survey, a survey does the same job and recognises what it saw last time.
  Retire it if it goes unused.
- Revisit the remembered answers for things with no identifier if they prove
  fragile (two identical cards, a card swapped for its twin). When one no longer
  holds, it is asked again, which is the safe direction.
