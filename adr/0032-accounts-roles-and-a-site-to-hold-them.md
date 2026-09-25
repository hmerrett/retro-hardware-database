# 0032 — Accounts, roles, and a site to hold them

**Status:** Accepted
**Date:** 2026-09-25
**Supersedes:** [ADR-0019](0019-running-open-is-supported-but-never-silent.md)

> Numbered 0032 because `feat/design-system-foundation` also carries a 0030, which
> collides with main's and will become 0031 when it lands. If it lands as
> something else, close the gap.

## Context

The login was one username and password read from the environment. Anybody
holding it could do everything; anybody else could read the public pages. The
architecture document had it as an open question ("there is no user table … a
question the moment it is two"), and it is now two: the owner wants to give
somebody the whole collection to read without giving them the keys, to close a
site entirely, and to add people without editing `.env` and restarting.

Two further things are wanted later, not now: a second factor, and possibly more
than one collection on one installation. Neither is being built. Both should cost
an addition when they come, not a redesign of what is built here.

## Decision

**Accounts live in the database, and the environment stops being the login.**
Four tables: `users`, `memberships`, `sessions`, `api_tokens`.

- A **user** is a username (matched without regard to case), an argon2 password
  hash, and whether it is switched on.
- A **membership** gives a user a **role** on a **site**. There is one site today,
  `SITE = 1`, and no `sites` table. This row is the seam for tenancy: a second
  collection would be a second site id, and a user's role would be looked up for
  the site the request is about rather than for the only one there is.
- A **session** is a random key in the browser's cookie, of which the database keeps
  only a SHA-256 digest. Switching an account off or changing its password ends its
  sessions on the next request, which a signed cookie cannot do. It also means
  `RHDB_SECRET_KEY` signs nothing any more and is not required.
- An **API token** is the same shape, for programs: shown once, kept as a digest,
  acting as its account with that account's role.

**Permissions are asked for by name; roles are lists of them.** `can(principal,
permission)` is the only check, in `accounts/roles.py`:

| role | permissions |
|---|---|
| visitor (nobody signed in) | none |
| viewer | `read_private` |
| admin | `read_private`, `edit`, `manage_settings`, `manage_accounts` |

A third role, or a site-scoped one, is a row in that table. A second factor is a
step between checking the password (`authenticate`) and opening the session
(`open_session`), which are two functions for that reason.

**`request.state.authed` keeps its name and now means *may edit*.** 165 places
ask it, most of them in templates deciding whether to draw an edit control. A new
`request.state.sees_private` answers the places that were really asking whether
the reader may see what a visitor may not — unpublished files, private projects,
locations, the for-sale flag, what an order cost, the time of day on the history.
The split was made by going through every use; the rule for the ones missed is
that a miss hides private data from a viewer, which is the direction that fails
safe (security-standards: least privilege). Renaming `authed` to say what it now
means would have been clearer and would have collided with every template the
design-system branch is rewriting; it is left for when that has landed.

**The gate answers by who is asking.** A visitor asking for something not public
is sent to log in (a browser) or answered 401 (the API). A signed-in account
asking for something its role does not reach is answered 403: sending somebody
who is already signed in to the login page would tell them nothing true.

**A new installation opens on Set up, guarded by a code in the log.** With no
accounts every request but the health check, the static files and the print
agent's door goes to `/setup`, which makes the first administrator. A fresh
install is on the internet before its owner has visited it, so the page asks for a
code the app writes to its log at startup: whoever can read the server's log is
the owner, and whoever merely found the address first is not. The code is held in
memory, renewed on each start while there are no accounts, and compared in
constant time behind the login's rate limiter.

**An installation upgraded from the single login is seeded from it.** On a start
with no accounts and `RHDB_AUTH_USER`/`RHDB_AUTH_PASSWORD` set, the app makes an
administrator from them. Nobody meets Set up who did not need to, and nobody has to
be told a new password. After that the pair is not read by the site; the tool
server still reads it until it is given `RHDB_API_TOKEN`, and HTTP Basic against an
account's password keeps working for tools that have not been moved to a token.

**There is no running open any more.** ADR-0019 existed because blank credentials
meant *every visitor may edit*, and that state was indistinguishable from a
missing `.env`. The state is gone rather than announced: a site with no accounts
is a site that is not set up, and a site anybody may read is a site with
accounts and **Visitors must log in** off, which is the default. `RHDB_OPEN` is
read only to say it does nothing.

**A closed site is a setting, not configuration.** **Visitors must log in** is a
row in the settings table (ADR-0023) for administrators to turn on and off. The
page's other settings are pinned by the environment where they were configuration
first, and this one never was.

**Accounts are managed from the command line in the first cut**
(`python -m app.accounts`, inside the container), because the pages to do it from
belong to the design system being built on another branch. The command stays
afterwards as the way back in for an installation that has lost every
administrator's password: somebody who can run it can read the database already.

## Consequences

- Existing installations sign in exactly as before on their first start.
  Deliberately-open ones meet Set up, which is a one-time price for the state no
  longer existing.
- A request with a session or a token costs a database read. The site is one
  process serving one collection; that is cheap, and it is what makes an account
  switched off stop at once.
- HTTP Basic verifies an argon2 hash per request, tens of milliseconds each. That
  is the reason to move the tool server to a token, not a reason to cache
  passwords.
- The rate limiter and the setup code are in memory, which suits the one uvicorn
  worker the app runs (ADR-0023 has what a second would mean). A second worker would
  have its own code, and its own count of wrong guesses.
- The suite signs in as an administrator by default, by writing a user and a
  session directly rather than hashing a password per test.
- Tenancy, if it comes: a `sites` table, a `site_id` on the collection's tables and
  every query scoped by it, and the membership lookup keyed by the request's site.
  The accounts and the permission check would not change shape.
- Revisit when the account pages land, to rename `authed` and remove what this
  change left in `base.html` for the design branch's sake.
