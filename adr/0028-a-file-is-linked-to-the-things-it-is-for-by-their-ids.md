# 0028 — A file is linked to the things it is for, by their asset ids

**Status:** Accepted
**Date:** 2026-09-24
**Supersedes:** [ADR-0020](0020-a-model-link-names-a-maker-and-a-model.md), and the
model link and the tags of [ADR-0006](0006-files-are-linked-to-what-they-are-for.md).
[ADR-0009](0009-a-file-is-published-by-hand.md) stands unchanged.

## Context

ADR-0006 gave a file two kinds of link, to one unit or to every item of a model,
and kept tags as labels that decided nothing. ADR-0020 let a model be named by its
maker and model as written, since the catalogue names machines and not cards.

The register the owner actually has shows what that became. Twelve files carried
twelve model links and not one unit link; ten of the twelve links reached exactly
one item. Every tag was a maker and model left behind by the name matcher that
0039 retired, so each file named its model twice, once as a tag and once as
"every Acorn AKF18". And a row of the files list carried six forms and nine
controls, three of them for tags that did nothing and one asking "its model, or
that one?", a question that only makes sense once you know how the mechanism
works.

Model links cost more than the screen space. A file's reach was a computation: the
page said "every Polpo PicoGUS" and did not say which five cards that was.
Correcting a part's model moved its files, which ADR-0020 was honest about and
could not avoid. And two kinds of handle, a folding rule and a label cache were
load-bearing, for a case — the card bought next year — that one tick answers.

## Decision

**A file is linked to asset ids, as many as it needs, by hand, and to nothing
else.** `file_asset` is the only link. `file_model` and `file_tag` go. The ids are
the register's, so a project can have files as a machine or a part does: the
receipt for what was ordered, the schematic the work was done from. A visitor is
never told that a file is linked to a private project, on the file's page, in the
list or by the list's search, since the file's own tick decides whether the file
is seen and the project's decides whether the project is.

**The model suggests and never decides.** Two places use it, and both only offer:

- uploading on an item's page offers the other units of the same model still held,
  as one tick;
- an item whose same-model units have files it has not is offered them, on its
  own page, to the owner alone.

"The same model" is the catalogue key where the catalogue names the machine, and
the maker and model folded as `filesdb.fold` folds them otherwise, as before.
Nothing is matched from a filename.

**Everything done to a file is done on its own page**, `/files/<id>`: the note,
the public tick, the links, delete. The lists on `/files` and on item pages are
read-only rows with a download button. A visitor is shown a published file's page
without its controls, and is told an unpublished one is not there, as its download
already did (ADR-0009).

**What a file is, is read from its name.** The drawing and the kind filters come
from the extension, and a disk image's size says which disk it is. This is
presentation only: it decides nothing about where a file appears or who sees it.

**The migration keeps every file where it was.** Each model link becomes a link to
each item that answers to that model on the day, held or disposed, since a
disposed item's page shows its files today. A tag that only repeated the model a
file was linked to, as the name matcher read tags, is dropped; any other tag is
kept, written into the file's note. On a fresh install nothing moves.

## Consequences

- What a file is linked to can be read off the page: the chips name the units.
  Renaming an item or correcting its model moves nothing.
- The card bought next year costs a tick instead of arriving on its own. That is
  the price, paid on purpose: a driver no longer reaches a unit nobody has looked
  at, and neither does a receipt.
- Five identical cards are five links. The list folds them into one chip; the
  file's page lists all five.
- `fold` stays in `filesdb`, for the suggestions only, and nothing folded is
  stored any more.
- `/api/files` loses `tags`, `models` and the `tag` parameter. That is a change a
  caller could see (ADR-0010), and it is in `openapi.json`.
- Of ADR-0006, the unit link stands, and so does its rule that deleting an item
  takes the link and never the bytes. ADR-0020 is superseded entirely.
- Revisit if the offer on a new unit is routinely missed, so that files that
  should have reached a unit did not. That would be the evidence that a rule was
  worth its cost after all.
