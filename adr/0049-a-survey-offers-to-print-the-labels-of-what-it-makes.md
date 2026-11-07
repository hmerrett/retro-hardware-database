# 0049 — A survey offers to print the labels of what it makes

**Status:** Accepted
**Date:** 2026-11-07
**Amends:** [ADR-0043](0043-a-survey-gives-everything-it-finds-one-of-three-answers.md)

## Context

ADR-0043 printed the label of every tag a survey makes on the survey agent's
printer, where the agent's entry names one (`bench:key:workshop-pi`), and on
nothing otherwise. An installation that prints its labels on a print agent's
queue already says so in Settings: each label's **Goes to** names the printer.
The register this was written for sends its small label to a print agent and
names no printer for its survey agent, so a survey that made a machine and its
drives printed nothing, and the labels had to be printed one page at a time.

The owner asked for the survey to offer the small label of each new part when
the small label goes to a queue, at the machine, and for a new machine too.

## Decision

**Where the small label goes to a print agent's queue, a survey offers to print
the small label of everything it makes.** The register's answer to the
machine's question names that printer (`LABELS=dellski`). The survey program
asks once, after every other question, and only when something is to be made
(**N** for the machine or for anything found): `Print a small label for each
new tag on dellski?`. **Y** goes in the report as `LABELS=YES`, and when the
report is filed the register puts the small label of each tag the survey made
on that printer's queue, the machine's included, and says so in its receipt.

- **One question, not one a part.** The labels come off one printer together,
  and a question for each would be a question too many at a machine being
  tested.
- **The small label, by the setting that already says where it goes.** No new
  setting: an installation that has chosen a queue for its small label has
  said where labels go.
- **A survey agent with a printer of its own is not asked**, and keeps printing
  as ADR-0043 has it, so nothing is printed twice.
- **Only what the report makes.** Something made later, from the survey's page,
  is made by somebody at the register, who has the label's own button.

## Consequences

- A new machine surveyed with somebody at the keyboard can have its label and
  its new parts' labels waiting on the printer before it is switched off.
- A survey program that does not know `LABELS` ignores it, and prints nothing.
- Pressing Enter, or nobody at the keyboard, prints nothing: a label is never
  printed without somebody saying so, or an installation's agent being set to.
