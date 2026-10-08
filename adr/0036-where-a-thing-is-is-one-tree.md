# 0036 — Where a thing is, is one tree

**Status:** Accepted
**Date:** 2026-10-08
**Amends:** [ADR-0034](0034-a-location-is-a-record-in-the-register.md)

## Context

ADR-0034 made a location a record, so that a box could be carried to the workshop
in one write and everything in it would follow. A part fitted in a machine already
followed the machine. Between them, the register says where a thing is with three
different links:

- a location's `parent_id`, the location it is inside;
- `location_id` on a machine and on a part, the location it is kept in;
- on a part, `computer_id`, the machine it is installed in, and `parent_id`, the
  part it is mounted on.

Five columns in three tables, and every one of them says the same thing: what this
is directly inside. Four separate walks read them — the location tree, the walk
that finds a fitted part's location, disposal's walk into a machine, and the plain
`computer_id` filters behind the machine page, the gallery, the search, the
figures and the labels — and at the edges they disagree:

- A part could be fitted in a machine and kept on a shelf at the same time. The
  shelf won, so a card could be in a drawer while its machine still listed it.
- Only locations were checked for loops. A part could be mounted on itself through
  the API, or on the part it was already mounted on through its page.
- Only a change of location was a move. Fitting a card and taking it out again
  were sentences in its history, so *which machines has this card been in?* had no
  answer a page could draw.
- A drive mounted on a controller card in a machine was in the machine for
  disposal and for deletion, and nowhere else: the gallery's count, the search, the
  figures and the labels follow `computer_id`, which the drive does not carry.
- A part could still be in the collection inside a machine that had left it.

A box holds machines, a machine holds cards, a card holds a drive, and carrying the
box carries all of them. That is one relation, and the register should hold it as
one.

## Decision

**Everything is inside at most one thing, and the register holds the tree.** The
pool of tags becomes a table:

    register(asset_id PK, what, inside_id → register.asset_id ON DELETE SET NULL)

Every machine, part, location and project has a row, and its own table's
`asset_id` is a foreign key to it. `inside_id` is the one link: the location a
machine is kept in, the location a loose part is kept in, the machine a card is
fitted in, the card a drive is mounted on, the location a box is in. The five
columns go. In the code the register is the table the four kinds are mapped from,
so `inside_id` belongs to every thing and one lookup answers what a tag is. The
column saying which kind a row is, is `what`, because a location already has a
`kind` -- building, box or bag.

That also puts the rule §3 of the architecture calls the most load-bearing into
the database. Two things cannot share a tag, because the tag is a primary key;
until now `ids.py` checked four tables in turn. And a deleted thing's row stays, its
`what` saying `deleted`, so its tag is never issued again: a label outlives the record it
was printed for, and must never open somebody else's thing.

**What may hold what is one list.** A location may be inside a location. A machine
may be inside a location. A part may be inside a location, a machine or another
part. A project is inside nothing and holds nothing. The list is in one place in
the code, so a pair added later is a deliberate change and not a new column.

**What a link means is read off what holds it.** Inside a location is *kept*,
inside a machine is *fitted*, inside a part is *mounted*. That difference is real
and the code still asks it where it matters: a machine's parts are part of the
machine, and a box's contents are not part of the box.

**A thing is in one place.** A card fitted in a machine is not also on a shelf.
Fitting it takes it off the shelf, and putting it on a shelf takes it out of the
machine. Where one request names both a machine and a location, the machine wins.
A fitted part is wherever its machine is, read up the tree when it is shown and
never written down — ADR-0034's reasoning, which is now the only rule instead of
one of two.

**Every move is one write and one row.** Fitting, taking out, mounting, putting
away and moving a box each set `inside_id` and write a `moves` row, with who did it
and how. What is inside the thing moved comes along by not being touched. A move
into the thing itself, or into anything inside it however far down, is refused: a
shelf cannot go into a box that sits on it, and a card cannot be mounted on the
drive mounted on it. So is a move into anything that has been disposed of.

**Taking something out leaves it nowhere.** A card taken out of its machine is
inside nothing until it is put somewhere. The register does not assume it is on
the shelf the machine is on: it says what it was told.

**What is inside a machine or a part shares its fate.**

- Disposing of one disposes of everything inside it, all the way down, on the same
  date and for the same reason, and restoring it brings back what went with it. A
  part restored on its own, out of something still disposed of, comes out of it
  and is left nowhere.
- Deleting one deletes everything inside it, all the way down. The page lists all
  of it before it goes, and a thing worth keeping is taken out first. The page
  still deletes only what has been disposed of, and everything inside a disposed
  thing has been disposed of with it, so nothing still in the collection goes this
  way. The API deletes by the same rule: something still in the collection is
  refused until it has been disposed of.
- Deleting a location deletes the location and nothing else. A box is where things
  are, not what they are made of. What is directly inside it — things and smaller
  locations — is left nowhere, so a location no longer has to be emptied before it
  can go.

**In a machine means anywhere in it.** The machine's page, the gallery's counts,
the search, the figures and the labels all follow the tree, so a drive on a
controller in a machine is in the machine. The machine's page shows it under its
card.

**Who is told where a thing is kept is decided for each thing.** A machine and a
loose part each have a **Visible** tick beside their Location. A part fitted in
something follows the outermost thing it is in. **Show locations** is the tick a
new thing starts with, as **New files are public** is for an upload (ADR-0029), and
changing it later changes nothing already in the register. It still decides
whether a visitor can open a location's own page, photographs and labels, and a
location's page shows a visitor only the things whose tick is on, and counts only
those. A visitor reads a ticked thing's path as links where location pages are
public, and as names where they are not. Signed in, you see all of it. What a part
is fitted in is not where it is kept: it stays public, as it always has been.

**The audit is the same rule, scanned.** The first scan opens a location or a
machine. Everything scanned after it goes into it — a part, a machine, a box —
until **next** closes it. Something already anywhere inside it is found; anything
else is moved in, and can be undone; anything the pairs, the loop rule or disposal
forbids is refused. A part scanned with nothing open says where it is and moves
nothing. Holding a thing until a location is scanned, ticking off a box and opening
it with one scan, and the moving-boxes switch all go. Each was a special case of
this rule, and a rule with special cases is one nobody can predict with a scanner
in one hand.

**Fitting is history from now on.** A card fitted last year keeps the sentence it
was given. Turning sentences back into rows would be guessing, and a history that
guesses is worse than one that stops.

## Consequences

- One module, `tree.py`, owns the tree: what a thing is inside, what is inside it,
  the chain up, the pairs, the loop check and the move. `locations.py` keeps what
  belongs to a location alone — kinds, names, a path as words, merging, labels — and
  disposal and deletion walk the tree through `tree.py`.
- Migration 0047 builds `register` from the four tables and sets each `inside_id`
  from the old columns: mounted on, then installed in, then kept in. A part with a
  machine and a shelf keeps the machine, and its history says the shelf was
  dropped. A thing still in the collection inside something disposed of is
  disposed of with it, on that date and for that reason, so a restore brings both
  back. A scan that took a part out of a machine has its move pointed at the
  machine, so undoing it still puts the part back. The downgrade rebuilds the five
  columns from the tree; what it cannot rebuild is the second answer a part used to
  be able to give.
- Each thing's tick is set to what **Show locations** says on the day of the
  upgrade, so a visitor sees exactly what they saw before.
- The API keeps `computer_id`, `parent_id` and `location`, each read off
  `inside_id`, so at most one of them is ever set, and writing one is a move. A
  request naming a machine or a part and a location fits the part. `location_public`
  is new. `DELETE /api/locations/{id}` succeeds with things inside, and leaves them
  nowhere. `DELETE` on a machine or a part still in the collection answers `409`.
- `stock_check_scans.was_computer` and `was_parent` go: a move's `from_id` now
  says what a thing was taken out of, and an undo reads it there.
- An allocation that loses a race for a tag now fails on the primary key instead
  of quietly giving two things one tag.
