# 0003 — Work is noted at check-in

**Status:** Accepted
**Date:** 2026-09-05

## Context

Migration 0031 replaced the per-item `project` / `project_note` flag with a real
`Project`, and put a quick box on `/projects` and on every item page: a tag, a
sentence, and you have a private project with the item on it and the sentence as
its first job.

Both of those boxes need an asset tag, so both can only be used once the item
exists. But the moment a fault is noticed is the moment the thing is unpacked —
and at that moment the form that files it is on screen and it has no tag yet. So
the note waited for a second visit to a page that did not exist when the thought
did, which is exactly how the second fault noticed gets forgotten. The same is
true of a part bought for a build already in hand: what it is for is known while
it is being entered, and speaking for it afterwards meant finding the project and
retyping the tag.

## Decision

The entry and edit forms for a computer and a part carry a **work box**: free text,
one job to a line, and a picker of the projects still in hand.

- Empty makes nothing. Most things arrive with nothing wrong, and a project per
  arrival would turn `/projects` into a second copy of the register.
- Text with no project picked raises a **private, planned** project called
  **`Work required by item: RH-XXXX`**, with the item on it and each line a job.
  Private for the reason the quick box's projects are: a sentence typed while
  unpacking has not been considered for publication.
- A picked project takes the item and the jobs instead, so nothing is retyped.
- The same two fields (`work_needed`, `work_project`) are on the create endpoints
  of the JSON API and on the MCP `create_computer` / `create_part` tools, because
  check-in happens by dictation as often as by typing. `ComputerOut` / `PartOut`
  gained a `projects` list of tags so a caller can reach what it just made.
- Everything above runs through one function (`main._take_on_work`), which is what
  keeps the history, the membership and the privacy rule identical wherever the
  sentence was typed.

A bad project tag is treated differently on the two sides on purpose: the API
**refuses** it (404, before anything is written), because a caller that named a
project meant that project; a form **falls back** to raising a project of its own,
because the menu cannot produce a bad tag, only a hand-made post can, and throwing
away an entry — photographs and all — over the convenience half of the gesture is
the worse failure.

## Consequences

- There is now one more door onto the same feature rather than a new feature: the
  work box, the quick box on `/projects` and the box on an item page all make the
  same thing, and only their defaults differ (the entry forms have no name to
  offer, so the item's tag names the project).
- Projects raised this way all read `Work required by item: …` until they are
  renamed, which is a flat-sounding list — accepted deliberately: the tag is what
  is in your hand at the bench, and a project worth a better name gets one on its
  own form.
- The work box is **write-only** — never filled in with what the project already
  says — so an ordinary save cannot add the same job twice. That also means the
  edit form is not a way to *read* what a thing needs; the item's own page is.
- Revisit if the projects list fills with one-job projects that would have been
  better as tasks on something bigger. The picker is the pressure valve; if it is
  not being used, the default is wrong.
