# 0034 — A location is a record in the register

**Status:** Accepted — amended by [ADR-0036](0036-where-a-thing-is-is-one-tree.md)
**Date:** 2026-10-01
**Supersedes:** [ADR-0027](0027-a-remembered-vocabulary-is-deleted-when-it-is-turned-off.md)

## Context

Where a thing is kept has been a line of free text on the machine or the part:
`Loft, blue crate 3`. That was enough to answer *where is it?* by reading, and
ADR-0027 added a remembered vocabulary so an emptied crate kept its spelling. It
cannot answer anything else a collection kept in boxes needs:

- **A crate cannot be moved.** Thirty things in `Loft, blue crate 3` are thirty
  strings. Carrying the crate to the workshop is thirty edits, or a register that
  is wrong about thirty things. A part fitted in a machine already follows the
  machine (`locations.inherited`), so the idea works. It just stops at the machine.
- **A crate cannot carry a label.** There is nothing to scan, so there is no
  *what's in here?* and no way to check a shelf against what the register says.
- **A crate has no page.** It has no photograph of where it sits, no note saying
  *third rack on the left*, and no history of what came and went.

A string can only be read. Each of these needs the location to be a thing.

## Decision

**A location is a record, and it takes its tag from the register's pool.** It gets
`RH-` and four characters from `ids.next_asset_id`, like a computer, a part or a
project. `/items/<tag>` then resolves a location as it resolves the others, so one
scan handler, one search by tag and one kind of label cover everything. Two
things can never share a tag, which is the rule §3 of the architecture exists to
hold. A location is the second thing in the pool that is not an object you own;
projects were the first.

**No namespace in the code.** An `L:` or `I:` in front of the tag was proposed,
so that a scanner could tell a location from an item. The shared pool already does
that, by asking which table holds the tag. A prefix would mean every item label
already printed needs reprinting before it scans in the audit. It would also
mean a second spelling of every tag for the search box and the API to accept.

**What is printed is the tag, and nothing that can change.** A Code 128 barcode
carries the seven characters `RH-XXXX`, and nothing else. A QR code carries
`<base_url>/items/<tag>/` as it always has, because a phone's own camera needs a
URL to open. Only the tag is ever read back out of either, so a location renamed,
re-parented or moved to another building keeps its label. One setting decides
whether labels carry a QR code, a barcode, or both. It is the installation's
choice and covers every label, because a collection is scanned with whatever
scanner it has.

**One record covers every size of location.** A building, a room, a rack, a shelf, a
box and a bag are all the same thing: a name, a kind, an optional parent, notes
and photographs. The kind only describes it and gives no rules. Somebody's
"shelf" is somebody else's "drawer", and a rule that a bag cannot hold a box
would be wrong in the first house it met. The only rule is that nothing can be
inside itself, however far down.

**The path is worked out, never stored.** *Workshop → Rack 3 → Shelf 2 → Box 14*
is read up the parents when it is shown. Moving Box 14 is one write to Box 14,
and everything in it is somewhere new at that moment. This is
`locations.inherited`'s reasoning applied one level higher: a stored path is a
row to rewrite every time something upstream moves, and getting that wrong is a
register that says a card is in a loft the box left two years ago. A part fitted
in a machine still has no location of its own unless one is given, and still reads
the machine's.

**A move is a row, with who made it and how.** A `move` table records the thing
or the location that moved, where it was, where it went, when, which user, and
whether it was moved by an edit, a scan or the API. A line of history text
cannot be asked *where was this before?*. The item's history panel reads its
moves in among its other lines, so the record of a thing stays together.
Moving a box records one move, on the box, and not one for each thing inside it,
because that is what happened.

**A scanning sequence is kept on the server.** The audit (☰ → Audit, first called
storage mode) opens a check against a location when its code is scanned. The check
records what was expected there, what was scanned, what moved in, and what was not
recognised. A phone
locks, a page reloads, a battery dies in the loft. A sequence held only in the
browser would lose the half-done shelf every time. It is also the record a later
audit report will be read from, so it is a table from the start.

**Who may see a location is the existing switch.** `public_locations` already
decides whether a visitor sees where a thing is kept. A location's page, its
photographs and its notes are the same information at more length, so they
follow the same switch. Off, which is the default, they are for signed-in people
only. A visitor gets the 404 a private project gives, not a login prompt, and so
does `/items/<tag>` for a location's tag, rather than a redirect whose path would
say what the tag is. That is the register's rule for anything kept back: what a
visitor may not see, it does not mention. Photographs of a room are an address with
pictures.

**The remembered vocabulary goes.** ADR-0027 kept a table of spellings so an
emptied crate could be offered again. A location that is a record stays when it is
empty, so the table has nothing left to do. `remember_locations` is retired, and
its table is folded into locations by the migration.

**The text converts once.** The migration makes a top-level location for each
distinct location string, and for each remembered one. They are named as typed
and of kind *other*. Each item is pointed at its location, and the text column is
dropped. Spellings that differ only in case become one location, which is how the
collation already treated them. Nothing is lost, and the nesting is left to the
owner, by scan or by edit. No rule could guess that `loft crate3` is inside
`Loft`.

## Consequences

- Every reader of `computers.location` and `parts.location` changes: the item
  page, the forms, the search haystack, the gallery card, the API and the tool
  server. The API keeps a `location` field. It accepts a location's tag or its name,
  and a name nothing matches makes a new top-level location, as the form does. A
  response gives the tag, plus the path as text.
- The search still finds everything in the loft with `loft`. The haystack carries
  the name of every location up a thing's path, and only for a reader the switch
  lets see them, as ADR-0027 required of the column.
- `public_locations` now gates page routes as well as a row, so it has a test
  that walks them: a location's page, its photographs, its labels and
  `/items/<tag>`, each asked as a visitor and each answering 404.
- A label set *as the look* needs the look's faces as TrueType. The site serves
  them as WOFF2, which the PDF renderer cannot read, so IBM Plex Sans and Mono are
  added as TTF beside `label_font.ttf`, under the same OFL.
- The pool's allocator reads a fourth table.
- Capacity, dimensions, last-verified dates and audit reports are not part of
  this. The check table is shaped so they can be added without moving anything.
