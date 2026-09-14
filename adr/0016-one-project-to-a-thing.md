# 0016 — One project to a thing, and a job may name the thing

**Status:** Accepted
**Date:** 2026-09-14

Changes the shape [ADR-0003](0003-work-is-noted-at-check-in.md) and
[ADR-0004](0004-work-projects-are-public.md) were written against; both otherwise
stand.

## Context

`project_asset` was many-to-many, on the argument that the same PSU can be wanted
by two projects. In practice a thing on two projects is a question rather than an
answer — *which of these is it actually on?* — and the work on a thing is the work
on that thing whichever project it was raised from. One machine in the register had
reached that state: a Tandon TM262 drive on both "Tandon PCA" and "Tandon TM262",
which is one piece of work filed twice, not two.

The other half is that a job had nowhere to say what it was about. `project_task`
held a project and a sentence, so an item's page could only ever show the *names of
the projects* it was on. A name is the address of the answer, not the answer:
standing at a shelf with a board in your hand the question is "what does this one
still need?", and "it is on Tandon PCA" makes you open another page to find out.

## Decision

- **A thing is on at most one project; a project is about many things.** The unique
  constraint on `project_asset` moves from the pair to `asset_id` alone, so the rule
  is the database's and not a habit in the code.
- **Putting a thing on a project moves it** off whatever it was on, and says so in
  both histories. Refusing would leave the older answer standing and say nothing.
  The jobs written against the thing move with it — a job naming an asset that is
  not on its own project would surface on that item's page under work it has no
  part in.
- **`project_task` gains an optional `asset_id`**, which must be one of its
  project's own things. Optional because most of a project's list is about the
  project — *order the caps*, *find a service manual* — and a column that insisted
  would turn those into a lie.
- **An item's page lists the jobs written against it**, outstanding first, with the
  project it belongs to named in one line above them.
- **The API reads back `project`, a tag or null**, where it read back `projects`, a
  list. A list that can only hold one entry asks every caller to unpack a question
  that has one answer. This is a caller-visible change and the pinned document
  (ADR-0010) records it.
- Migration 0037 resolves existing duplicates by a general rule — keep the earliest
  membership, log what it drops — because a migration may not make judgements about
  particular rows (ADR-0002). On this installation the one conflict was settled by
  hand first, so it found nothing to do.

## Consequences

- The question an item's page is actually asked is the one it now answers.
- **A privacy rule moved with the content.** ADR-0004's sixth door was that a
  private project must not name itself on the public page of a machine it is about.
  Now that the panel shows jobs rather than names, the jobs are what has to go: what
  a private project keeps back *is* what is wrong with the machine, so showing the
  work while hiding the label would publish the whole of it and withhold the
  wrapper. Tested, not assumed.
- **What is given up:** a thing genuinely wanted by two pieces of work can no longer
  say so. The honest answer is to make it one project, or to note the second as a
  job on the first. If that turns out to be wrong, the trigger to revisit is a real
  case where neither reads true — not the general feeling that many-to-many is more
  flexible, which is what put the drive on two projects in the first place.
- `project_asset` is now a table that holds one row per asset and could be a column
  on the item. It stays a table because the register is two tables, and this is the
  one place that is already handled.
