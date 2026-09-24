# 0006 — Files are linked to what they are for, not named after it

**Status:** Superseded in part by [ADR-0028](0028-a-file-is-linked-to-the-things-it-is-for-by-their-ids.md)
(the model link and the tags; the unit link stands) — privacy default amended by
[ADR-0009](0009-a-file-is-published-by-hand.md)
**Date:** 2026-09-08

## Context

Files kept beside the register — a driver disk, a manual, a ROM dump, the utility
that came with a card — are associated by name. A file carries tags; an item
answers to its display name, its model, its maker and model together and its own
asset id; and a tag matches when it is contained in one of those, folded for case
and spacing.

The reasoning behind that is sound and worth restating, because this record keeps
it. A Trident 8900 driver is a fact about that card as a model, not about the
particular one on the shelf. A collection holding three of them should not carry
the same download three times, nor lose it the day one of the three is disposed
of. Containment is what lets one tag cover a range: "Creative Labs Sound Blaster"
lands on the AWE32, the 16 and the Pro because each of their names has it inside.
That reasoning lived in `filesdb.py`'s docstring rather than here, which is the
failure ADR-0001 describes, and is part of why this record exists at all.

What the name has cost is threefold. Containment fires on any short tag, so a tag
of "16" or "Pro" reaches further than anyone intended. Renaming an item, or
correcting its manufacturer, silently detaches its files — there is no integrity
to violate and so nothing to report. And there is no way to ask what a file is
attached to and get an answer rather than a recomputation.

The third is what forced the decision. Uploaded files are public, and a receipt or
a photograph of a repair can carry a name, an address or the last four digits of a
card — the open question `security-standards` has been holding for the owner. A
privacy gate has to test a fact. Gating on a substring match means gating on a
computation whose result changes when somebody edits a name, and a leak of that
kind is silent.

## Decision

A file is linked to what it is for, explicitly and by hand. Two relationships,
because there are two kinds of file:

- **to an asset id**, many to many — a receipt, a photograph of a repair, a ROM
  read off one particular board;
- **to a catalogue model**, many to many — a driver, a manual, a utility disk.

An item offers the files linked to it and the files linked to its model.
`machines.yaml`'s `key` is the handle for the second, because it is documented as
the permanent name, which a display name is not; `AssetVariant.model_key` already
stores it for the same reason, so this is a precedent rather than a new idea.
Asset ids are plain columns rather than foreign keys, following `ProjectAsset` and
for its reason: they name something in a register that is two tables.

Tags stay, demoted. A tag describes what a file *is* and remains worth having for
search and browse; it no longer decides what a file *applies to*. The tag says
what a file is, the link says what it is for.

Deleting an asset removes the link and never the bytes. A file left with no links
is unfiled, and is shown as such rather than quietly deleted — the disposal case
the old docstring was right to worry about.

A file may be marked private. The default is public, following ADR-0004: the file
store exists so that a driver or a manual is as readable as the machine it is for,
and a default the other way would be undone by hand on nearly every upload. What
is private is absent from the file index and from item pages, not merely refused
at the point of download. This resolves the open decision in
`security-standards`; explicit association is what makes the gate trustworthy,
and the flag is what makes it a gate.

## Consequences

- A file's reach becomes a fact that can be read, audited and gated, rather than
  a match recomputed per request. Renaming an item no longer moves its files.
- What name-matching got right is kept: one driver still covers three identical
  cards, and the fourth acquired next year, without three ticks to remember.
- More work at upload — a file about one unit has to be pointed at it. The upload
  form already prefills from the item the upload started on, so the common case
  is a confirmation rather than a search.
- Existing behaviour is preserved on the day of the change by running the matcher
  once and writing what it finds as links: a general, data-driven backfill of the
  kind `database-standards` allows in a migration. It preserves what the matcher
  got *wrong* too, so its output is worth reading before it is trusted.
- The two docstrings that argue for name-matching — `StoredFile`'s and
  `filesdb.py`'s — are rewritten as part of the change. Their reasoning is not
  lost; it is above.
- Revisit if ticking items at upload becomes the slow part of filing something,
  or if a third kind of association turns up — a file about a manufacturer, or
  about a platform, rather than about a model or a unit.
