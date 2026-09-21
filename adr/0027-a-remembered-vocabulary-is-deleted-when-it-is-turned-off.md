# 0027 — A remembered vocabulary is deleted when it is turned off

**Status:** Accepted
**Date:** 2026-09-21

## Context

Every pick list on these forms has so far been derived: `_answers_given` reads a
column, counts the spellings and offers the commonest back. Nothing is stored,
because nothing needs to be — the list *is* the register, asked a question.

Where a thing is kept breaks that, and it is the first field that does. A source
is written once and stays true forever; a location is true until the thing is
moved, and the last item to leave a crate takes the crate's spelling out of the
register with it. Empty `Loft, blue crate 3`, fill it again a month later, and
the derived list has nothing to offer — so it is typed again, as `loft crate3`,
and one crate is now two. That is exactly the drift the pick lists were built to
stop, arriving through the one door they do not cover.

Fixing it means the register keeping a word it is no longer using: a vocabulary
table, which it has never had. And a vocabulary table is a list of places
somebody lives or works, accumulated silently over years, which is a different
kind of thing from a column on a machine — so "remembered" has to be something
the owner can switch off, and switching it off has to mean something honest.

## Decision

**A `location` table: one row per location ever saved, while remembering is on.**
Written on save, nowhere else; read only to pad the pick list out with places
nothing is kept in now. The suggestions are the union — what is in use, commonest
first, then what is only remembered, most recently used first. The in-use half is
still derived, so the table can be empty or deleted and the forms still work.

**`remember_locations`, on by default.** Off, nothing is written and the pick
list is only what is in use — which is the behaviour every other pick list on the
site already has, so off is not a broken mode, it is the old one.

**Off means deleted, not ignored.** Turning the switch off purges the table. The
alternative — keep the rows, stop reading them — is the one that looks kinder and
is worse: the owner has asked the register to stop remembering where their things
are, and a register that answers by hiding the list while keeping it has answered
a different question. The purge runs on every save while the switch is off rather
than only on the transition, because an idempotent delete needs no memory of what
the switch was a moment ago, and "it only purged if you flipped it in one go" is
the kind of condition nobody can test by looking at the page. Switching back on
starts afresh from what is in use; what it knew before does not come back, and
the manual says so.

**`public_locations`, off by default.** Who may see something is decided rather
than defaulted (`security-standards`), and this one decides itself: a public page
saying which loft the rare machine is in is an address as much as a description.
Off, the item page omits the row and — the half that is easy to miss — the
visitor's haystack omits the column, exactly as ADR-0018 requires of `for_sale`.

`OWNER_ONLY` could not carry it. That set is the decision made once and for all,
and this one is a switch, so `_haystack` asks for the hidden columns for *this*
reader and the set is one answer to that question rather than the whole of it.

## Consequences

- The first stored vocabulary in the register, and the shape the next one copies:
  derived list first, stored rows only to hold what the derivation has lost, and
  a switch whose off state is the derived list on its own.
- A purge is a real delete with no undo. That is the promise, so it is in the
  manual in those words, and the test that holds it turns the switch on, uses a
  location, clears it off its last item, switches off, switches on, and requires
  the location to be gone.
- `_haystack` now asks a setting a question, which is a read per search rather
  than per row — the settings are cached for the process (ADR-0023), so this is a
  dictionary lookup and not a query.
- Two switches for one field is one more than a field usually earns. They answer
  different questions — who may see it, and what the register keeps — and folding
  them into one would tie publishing a location to remembering it, which are not
  the same choice.
- Revisit if a second field wants remembering. The table is named for locations
  and would want a `field` column rather than a second table; nothing here is
  decided for it.
