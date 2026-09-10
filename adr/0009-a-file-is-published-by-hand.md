# 0009 — A file is published by hand

**Status:** Accepted
**Date:** 2026-09-10
**Amends:** [ADR-0006](0006-files-are-linked-to-what-they-are-for.md) (the privacy
default only; the association work it decides stands and is still to do)

## Context

Uploads have been public since migration 0020 gave them a table. `filesdb` matches
a file to an item by name and the auth rules let anybody download one, which was
right for what the box was first for: a driver nobody may fetch is a driver nobody
has, and the manuals are a good part of what the catalogue is *for*.

The same box takes receipts. A receipt carries a name, an address and sometimes
the last four digits of a card, and the way to attach one to a single machine —
tag it with the asset id — is documented in the manual and used. `security-standards`
has carried this as an open decision for the owner ever since, with instructions
not to change it silently, and the roadmap has it as the only open item that risks
exposing something personal.

ADR-0006 decided the flag and decided it public-by-default, following ADR-0004's
reasoning about work projects: a default undone by hand on nearly every upload is
not a default, it is a step. That reasoning holds for projects and does not
transfer here, which is what this record is for.

A project is a piece of writing. Somebody sat down and typed it, about the
collection, for a reader — the argument in ADR-0004 is that such a thing is
interesting and that keeping it back is the exception. An upload is not writing.
It is whatever came out of the drawer, named by the machine it came off, and its
contents are frequently unread: a folder of scans goes up in one gesture, and
which of the eleven is the invoice is a question nobody asks at upload time. The
failure modes are not symmetrical either. A driver left unticked is an
inconvenience the owner notices the next time they look at the page. A receipt
left ticked is a disclosure nobody notices at all, and one that a search engine
may have taken a copy of by the time anybody does.

## Decision

`files.public`, defaulting to false, and a tick beside every file that sets it.
Nothing is published until somebody says it is.

The flag is the wrong way up from `projects.private`, deliberately: the state a
new column starts every row in should be the state an upload should start in, so
that adding a file and forgetting the tick discloses nothing. Ticking is a
decision somebody made; forgetting to tick is not.

A visitor is shown published files alone — on item pages, in `/files`, and
following a tag chip from either. The download route asks the same question of
the same column and answers 404, not 401: there is no account a reader could hold,
so an invitation to log in would only confirm that the file is there, which for a
receipt filed under an asset id is most of what was being kept back. An
unpublished file is served `private, no-store`, because unticking the box has to
stop the copy being handed out.

**What is already on file stays on file.** Migration 0035 backfills `public = 1`.
Everything uploaded before today went up under a rule that said uploads are
public; the drivers and manuals are linked from item pages and from printed QR
labels, and turning all of them off in a deployment would take the site's
downloads away to protect the few of them that are receipts. This is a general,
data-driven backfill of the kind `database-standards` allows — it publishes
whatever the database in front of it holds and, on a fresh install, publishes
nothing. It is the mirror image of ADR-0004's `tools/publish_projects.py`
reasoning and comes out the other way for the same reason: there, "publish
everything" was a breach on somebody else's collection; here, the rows being
published are exactly the rows that were already public on it.

## Consequences

- The open decision in `security-standards` is closed, and the flag half of
  roadmap item 3 is done. The links half — `file_asset`, `file_model`, demoting
  tags — is untouched and still wanted: this gates on a column, but *which* files
  an item offers is still a substring match recomputed per request, and ADR-0006
  is right that a gate is only as trustworthy as the association under it.
- Filing a driver is two gestures now, upload and tick. The tick sends the moment
  it changes rather than waiting for a save, which is the same bargain the photo
  picker makes; the button stays in the markup for a browser running no script.
- An owner looking at `/files` can read what is on the open web in one list. That
  is new, and is the answer to a question that previously had none.
- Two tests changed rather than being added: both were written when downloading
  needed no permission, and both now publish first. That is the change stated as
  plainly as it can be.
- Revisit if the tick becomes the thing always done rather than sometimes — the
  ADR-0004 shape, arriving late. The answer then is probably a default per upload
  form rather than a default per column, since the folder-of-scans case and the
  one-driver case want opposite things and the page knows which is happening.
