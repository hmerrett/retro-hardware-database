# 0015 — A work project is called what the item is called

**Status:** Accepted
**Date:** 2026-09-13

Amends the naming clause of
[ADR-0003](0003-work-is-noted-at-check-in.md); the rest of that record stands.

## Context

A project raised from the work box is named after the item it is about, because
the form asks for no name and the item is the only thing known at that moment.
ADR-0003 set that name to `Work required by item: <what the item is called>`, and
migration 0033 later moved the variable half from the tag to the item's name.

The prefix has not earned its place. It reads the same on every row it appears on,
so it tells a reader nothing about which row they are looking at, and it puts four
words in front of the only part that varies — which is what a narrow column cuts
off first. What the project is *for* is already carried beside it on every list it
appears in: the item, and the status.

ADR-0003's argument for the prefixed form was never the prefix. It was that the
quick box named projects after the item while the entry forms named them after the
tag, so the same sentence about the same drive made two differently-named projects
depending on which box was to hand. Both now run through one function
(`main._work_project_name`), so dropping the prefix in that one place keeps them in
step and does not reopen it.

## Decision

A project raised from the work box, with no name given, is called **what the item
is called** — its name, or its tag where it has no name yet — and nothing more. A
name typed in the box still wins.

Migration 0036 brings the ones already written into line, under 0033's narrow rule:
only where the name is exactly the generated form for the one item the project is
about, so anything named by hand is left alone.

## Consequences

- A list of work projects reads as the things they are about, and reads that way in
  a column too narrow for the old form.
- **What is given up:** the name no longer says why the project exists, so a fault
  noted at check-in and a deliberate build read alike on `/projects`. The status and
  the item carry part of that and not all of it. This is the cost, accepted with
  eyes open rather than argued away.
- Two of the same model still give two projects called the same thing. That is what
  the project's own tag beside it on every list is for — the same answer ADR-0003
  and migration 0033 gave.
- Revisit if the list ever needs to distinguish a raised-from-an-item project from
  one somebody started deliberately. That is a property of the project, and the
  place to put it is a column, not a prefix on a name somebody can edit.
