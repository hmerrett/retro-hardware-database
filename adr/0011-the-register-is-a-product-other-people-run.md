# 0011 — The register is a product other people run

**Status:** Accepted
**Date:** 2026-09-11

## Context

This began as one person's CSV file and became one person's web app. Every
decision since has been allowed to assume that: one collection, one operator, one
installation, one person who knows why the vocabularies are what they are.

That assumption has quietly stopped being true. The repository takes pull
requests from people who are not the author; the code already carries three
names in its copyright line. It is to be open source and public. The intended
readership is now anyone who wants to catalogue a retro-hardware collection and
the workshop around it.

The distinction matters because it was asked directly in review — *"is the design
intended to be extensible or just configurable? If the former then everything
above is really important"* — and answered "configurable". On that answer a good
deal was reasonably set aside: authoring the API specification rather than
generating it, abstracting the data layer so the database can be something other
than MariaDB, and writing acceptance tests that define intent rather than report
behaviour. Each of those is work whose whole value is that *someone else* depends
on the answer being stable. With one user there is no someone else.

## Decision

**It is a product other people run, and that is now the design intent.** Not a
hosted service with accounts — a thing someone installs for their own collection,
on their own machine, with their own data.

The consequence is that the deferred work is no longer deferred. What changes:

- **The API's shape is a promise to strangers.** The document is pinned
  (ADR-0010), which stops it changing silently, but it is still generated from
  the code. Authoring it, and making the code conform, now buys something real.
- **The database is someone else's choice.** MariaDB-only is defensible as a
  testing decision for one installation (ADR-0008); it is a hardware requirement
  for a product. There is no raw SQL anywhere and the ORM is used throughout, so
  the distance to Postgres or SQLite is probably small — but "probably" is the
  word doing the work, and nothing proves it.
- **Migrations run against data nobody here has seen.** ADR-0002 already forbids
  assuming specific rows. Upgrading a stranger's database raises the cost of
  getting that wrong from "reimport my CSV" to "lost someone's collection".
- **One username and one password out of the environment** is a personal
  shortcut. A workshop is frequently more than one person, and there is no way to
  add a second without sharing the first.
- **The vocabularies encode one collector's model of the hobby**, ported
  faithfully from the flat-file system that preceded this. Another collector's
  shelf has things on it that this data model has no word for.
- **Accessibility becomes an obligation rather than a courtesy.** Contrast and
  touch targets are tested; landmarks and alt text exist on the public pages;
  none of it is a rule anyone is held to yet.
- **The asset-id prefix is fixed at `RH-`.** It stands for Retro Hardware rather
  than for anyone's initials, so it is not wrong for a stranger — but it is not
  theirs either, and it is hard-coded.

## Consequences

- The review that prompted this reads differently now. The parts of it that were
  fairly answered with "this is configurable, not extensible" are live again, and
  the ones that were always overkill for a personal install — Kong, K3S,
  Prometheus, a rewrite — are still overkill for a self-hosted product. The
  dividing line is whether a stranger depends on it, not whether it is more
  professional.
- None of this needs doing at once, and none of it changes what the software does
  today. It changes what a change to the software costs: breaking an interface
  now breaks other people's installations, and the value of pinning a thing rises
  with the number of people standing on it.
- Nothing here commits to multi-user accounts. "More than one person in a
  workshop" is a question to answer deliberately, not a feature assumed by this
  decision.
- This supersedes the answer given in review, not an earlier ADR — the previous
  position was stated in conversation and in `docs/architecture.md`, never
  recorded as a decision. It is recorded now so it does not have to be argued
  again from memory.
