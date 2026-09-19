# 0023 — A preference is not configuration, and the environment still wins

**Status:** Accepted
**Date:** 2026-09-19

## Context

Everything the app is told from outside comes from the environment. That rule is
in `CLAUDE.md`, it is in backend-standards, and it has been right every time it
has been applied: the database URL, the credentials, the signing key, the
branding directory, the public base URL. All of them are facts about a
deployment, decided when the container is started by whoever starts it.

The settings page is the first thing that is not like that. What the collection
is called, whether search engines may list it, whether a photograph is
watermarked,
which theme the site opens in — these are decided by the person who owns the
collection, changed on a whim at four in the afternoon, and changed from a
phone. Putting them in the environment means an SSH session and a restart to
rename a site, which is not a preference, it is a deployment.

Nor are they all the same kind of thing. A theme is a fact about the browser
somebody is reading in; a site's name is a fact about the installation. The
register has never had anywhere to put either, and the roadmap wants the first
one badly — where a label goes, once labels can go to a Bluetooth printer or a
print server, is a fact about *the device holding the label*, and the phone by
the shelf and the machine in the workshop will answer differently.

So there are three places a preference could live, and all three are needed:
the environment, the database, and the browser.

## Decision

**A preference is stored in the database and edited on a page; configuration
stays in the environment.** The two are told apart by who decides: if the person
who owns the collection decides it, it is a preference. If whoever runs the
server decides it — where the database is, what the credentials are, where the
photographs are kept — it is configuration, and nothing about this changes it.

**A device preference is stored in the browser and never travels.** The theme
already worked this way and keeps working that way: the ⋯ toggle chooses for the
browser it is pressed in, and overrules the installation's default. The settings
page does not show or manage that choice — it sets the default the choice
overrules, and the two are deliberately not mixed on one page.

**Where both exist, the environment wins, and the page says so.** A setting may
name an environment variable. If that variable is set, it is the value, the page
shows the control greyed and refusing an answer, and a form post cannot change
it. Which variable holds it is in the manual rather than on the row: the page
says once, at its foot, that greyed means set in `.env`, which is what somebody
looking at a control they cannot move needs to know (interface-text).

That last part is the decision that took the most arguing, because the other way
round is friendlier: let the page overrule the environment and a click is the
last word. It was rejected because of what it does on the next restart. A
deployment that sets `RHDB_WATERMARK=0` in its compose file has said something
deliberate; a click overruling it would be forgotten the moment the container
came back, and the value would flip without anybody touching anything. A setting
that silently reverts is worse than one that cannot be changed from here — the
first is a bug nobody can find, the second is a sentence on a page.

This is the same shape as ADR-0019. Two states that behave identically are the
fault; a state that says which one it is in is the fix.

## Consequences

- One table, `setting`, a key and a value. Not a column per preference: the page
  is expected to grow, and a migration for each new row on it would be a tax on
  exactly the thing this is supposed to make cheap. The definitions — the label,
  the default, the kind of control, the variable that pins it — are in
  `settings.py`, where they can be read by the page and by the suite.
- Every setting has a default that is what a fresh install starts on, so an empty
  table is a working site and no migration has to seed anything (ADR-0002).
- The values are cached per process and the cache is dropped when the page saves.
  The app runs as a single uvicorn process today; if it is ever run as several,
  a change would reach the others at their next restart rather than immediately,
  and this note is where to start when that becomes wrong.
- `RHDB_WATERMARK` is the only variable that pins a setting at the moment, and
  it keeps working exactly as it did. What changed is that it is now the pin on a
  preference rather than the only way to express one.
- The next thing on this page is where a label goes, which is a fact about the
  device rather than about the collection. Nothing here has to be revisited to
  put it there: the storage question is answered, and what that setting needs is
  a group of its own on the page rather than a new decision.
- Accounts, when they come, are the fourth place: a preference belonging to a
  person rather than to the installation or the browser. The table takes a
  nullable owner column and the definitions grow a scope; nothing here has to be
  undone to get there.
