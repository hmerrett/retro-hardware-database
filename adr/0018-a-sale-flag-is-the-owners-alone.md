# 0018 — A sale flag is the owner's alone

**Status:** Accepted
**Date:** 2026-09-16

## Context

The register records what is owned (ADR-0007), and `disposed` records the end of
that: the machine has gone, here is when and why. What had nowhere to live was the
step before it — *this one could go*. A shelf gets full, two of something turn up,
an itch to thin out the 486s arrives on a Sunday, and by the following Sunday which
machines it was about has been forgotten. The only places to put it were a note on
the item, which is public, and somebody's head, which is worse.

So: a flag. The question `security-standards` insists on asking of anything new
that stores something somebody typed is who may see it, and the request said a
private page, which settles the list. It does not settle the rest, and the rest is
where this kind of thing leaks.

A flag saying a machine might be sold is not a fact about the machine. It is a
statement about the owner's intentions, on a public, crawlable, indexed page about
somebody's collection. Published, it invites offers on things nobody has decided to
sell, and it turns a catalogue into a shop window — which is a different thing from
what ADR-0004 decided to be open about, because a work project is a piece of
writing offered to a reader and this is a half-formed intention. The failure modes
are the asymmetric pair from ADR-0009: a flag kept back is noticed the next time
the owner looks at the list, and one published by mistake is noticed by nobody,
after a search engine has taken a copy.

## Decision

`for_sale` on `computers` and `parts`, boolean, not null, defaulting to false. A
tick on the item's own page sets it, the way `files.public` is ticked — a tick is
an answer, not a draft — and `/for-sale` lists what is ticked.

**Owner-only everywhere, and "everywhere" is the decision.** A column is not made
private by being left off the page it is most obviously on:

- The item page renders the tick and the marker only for a logged-in reader.
- **The search haystack excludes it for a visitor.** This is the one worth writing
  down. `_haystack` reads *every column off the model* — that is what makes "any
  field" true rather than nearly true — so a new column joins the anonymous search
  simply by existing, with nobody deciding that it should. A visitor searching
  `true` would have been handed every flagged item, from a page that shows no such
  thing. Owner-only columns are therefore a named set that `_haystack` reads, not a
  habit of remembering.
- `/for-sale` is not a public page, so the auth gate sends a visitor to the login.
  Not a 404: ADR-0009 answers 404 for an unpublished file because the file's
  existence is itself the disclosure, and that does not transfer — this is a page
  of the software, not a fact about the collection, and every other owner-only page
  behaves this way.
- **It is not in the JSON API.** The flag is set where the decision is made, on the
  item in front of you, so nothing needs to carry it to a caller. That also leaves
  the pinned contract (ADR-0010) untouched, which is worth having for free.

**A flag, and nothing beside it.** No note, no asking price. "Potentially, in
future" invites a condition — *once it is recapped*, *if the other one arrives* —
and a price invites a second one, and at that point this is a sale list rather than
a shortlist, which is a feature with a different shape and a different audience.
The history is already there for anybody who wants to write down why.

## Consequences

- One migration, two columns, no data assumptions: a fresh install gets false
  everywhere, which is what an installation that has never thought about selling
  anything should have (ADR-0002).
- The register now describes three states rather than two — kept, maybe going,
  gone — and only the middle one is private. That asymmetry is the point and will
  look odd in the code until this is read.
- The named owner-only set is a place for the next such column to go, and a test
  holds it to the haystack. That is the actual deliverable here: the flag is four
  lines, and the thing that makes it safe is knowing that adding a column to a
  model quietly adds it to what a stranger can search.
- Revisit if the tick starts meaning "listed" rather than "considering". A thing
  actually for sale wants a price, a photograph chosen to sell it and somewhere
  public to put it, and none of that should be bolted to this.
