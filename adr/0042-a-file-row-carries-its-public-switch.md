# 0042 — A file's row carries its Public switch, and nothing else

**Status:** Accepted
**Date:** 2026-10-13
**Amends:** [ADR-0028](0028-a-file-is-linked-to-the-things-it-is-for-by-their-ids.md) —
"the lists are read-only rows with a download button". [ADR-0009](0009-a-file-is-published-by-hand.md)
stands unchanged.

## Context

ADR-0028 took every control off the rows of a file list. A row had carried six
forms and nine controls, and on a phone two files filled the screen with boxes.
Everything done to a file moved to its own page, and the row became the way there.

That was right for the note, the links and delete, and it cost something for
publishing. ADR-0029 said so: with the tick gone from the rows, forgetting it means
a trip to each file's page. Publishing is also the one thing the owner checks
across many files at once. `/files` already has a **Private** list for exactly
that, and on that list the answer for each file was one page away.

The item page's design review (finding 34, decided 28 September) asked for a
Public/Private button on each row, pressed when the file is public.

## Decision

**A file's row carries one control: Public, a toggle button, pressed while the file
is published.** Only an account that can change files gets it. A viewer account,
which sees private files without being able to change them, keeps the *Private*
mark. A visitor sees neither, because a visitor is never shown a private file.

The button always reads **Public**, and `aria-pressed` carries the state. A
button whose word swapped between Private and Public would leave it unclear
whether "Private" said what the file is or what pressing it does. It would also
need a name that did not match its words. Its name is "Public, " and the filename,
so a list of them can be told apart, and the name starts with the word on show.

Pressing it posts to the route the file's page uses, `POST /files/{id}/public`. With
script, it sends in place and the list does not move. Without script, the form
posts and comes back to the same row.

The rest of ADR-0028 holds. The note, the links and delete stay on the file's own
page, and the name still opens it.

## Consequences

- Publishing a batch of drivers, or checking the Private list, is one press a file.
- ADR-0009's rules are unchanged: an unpublished file is 404 to a visitor at every
  address and is served `private, no-store`, and unpressing takes it down everywhere
  at once.
- A row has one more thing on it on a phone. The filename keeps the room it needs,
  because the button is one short word.
- Revisit if a second control is asked for on the row. Publishing is on the row
  because it is the one question asked of many files at once. That reasoning does
  not carry to a second control, which should go on the file's page.
