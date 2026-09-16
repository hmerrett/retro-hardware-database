# 0020 — A model link names a maker and a model, not only a catalogue key

**Status:** Accepted
**Date:** 2026-09-17

Amends [ADR-0006](0006-files-are-linked-to-what-they-are-for.md), which invited
this revisit in its last line.

## Context

ADR-0006 links a file either to an asset id or to a catalogue model, and names
`machines.yaml`'s `key` as the handle for the second. That handle exists only for
a machine, or the board out of one: `AssetVariant.model_key` is written for an
asset the catalogue names, and a PC, a custom build or any part has none.

Which leaves the record's own example with nothing to hang off. A Trident
TVGA8900 is a part. Its maker and model are free text on `parts`, there is no
catalogue entry for a video card, and there is unlikely ever to be one — the
catalogue is a catalogue of machines. So "one driver still covers three identical
cards, and the fourth acquired next year", which ADR-0006 lists as what
name-matching got right and the change keeps, could not have been written as that
record describes it.

The same gap swallows a good half of the machines. A Compaq Deskpro 386 is a
computer with a maker and a model and no catalogue key, and a service manual for
it is exactly as much a fact about the model as a Spectrum's is.

## Decision

**A model link names a model. Where the catalogue knows the model, it is named by
the catalogue's key; where it does not, it is named by the maker and the model as
written.** Two kinds in one table rather than two tables, because they answer the
same question and an item asks it once:

- `catalogue` — `machines.yaml`'s stable key, as ADR-0006 says. Immune to editing,
  because nothing an owner types is in it.
- `named` — the maker and the model, folded the way `filesdb.fold` already folds a
  name, joined: `trident|tvga8900`. The label as typed is stored beside it, since
  a folded key is not something to show anybody.

**An item answers to both kinds where it has both.** A Spectrum +2 is a catalogue
machine *and* a Sinclair ZX Spectrum +2, so a file linked either way reaches it.
Without that, identifying a machine in the catalogue after a file was attached to
it by name would take the file away, which is the class of fault this pair of
records exists to end.

**Matching is exact, on the stored key.** This is the whole difference from what
came before: containment is what let a tag of "16" or "Pro" reach across the
collection, and an exact key cannot. A model is named or it is not.

## Consequences

- The case ADR-0006 promised to keep is kept, for parts and for uncatalogued
  machines as well as for the catalogue's own.
- **Correcting a part's model moves it between models, and its files with it.**
  A card whose model is fixed from `TVGA8900` to `TVGA8900C` is a different model
  afterwards and offers a different model's files. This is not the fault ADR-0006
  reports — that was a *display name* silently deciding a file's reach — but it is
  adjacent to it, and worth being plain about: saying what a thing is is how a
  thing gets its files. The files page says what every file is attached to, so a
  link left naming a model nothing answers to any more is visible rather than
  silent, and an item that has lost its manual says so by not showing one.
- A catalogue key is stable, so a machine the catalogue names is immune to the
  above. Identifying a machine is the way to get that.
- `fold` is now load-bearing in a second place. It stays where it is, in
  `filesdb`, and the link table stores what it produced rather than recomputing
  it: a change to the folding must not quietly rewrite what a link means.
- Revisit if a third handle turns up — a file about a maker, or about a platform
  rather than a model. The shape above takes one: another `kind`.
