# 0019 — Running open is supported, but never silent

**Status:** Superseded by [ADR-0032](0032-accounts-roles-and-a-site-to-hold-them.md)
**Date:** 2026-09-16

> Numbered 0019 because 0017 and 0018 are on a branch in flight. If that branch is
> dropped rather than merged, renumber this to close the gap.

## Context

The app has two states and only ever announced one of them.

`AUTH_ENABLED` is `bool(AUTH_USER and AUTH_PASS)`, read from `RHDB_AUTH_USER` and
`RHDB_AUTH_PASSWORD`. Compose passes both as `${RHDB_AUTH_USER:-}`, so a `.env`
that is missing, unreadable, or left behind in the directory the checkout was moved
out of yields two empty strings and a stack that comes up perfectly happily.
`_resolve_secret_key` then reads that as the supported open mode and mints a
throwaway per-process key, which is the right thing to do *if* running open was the
intention.

What follows is invisible. `auth_gate` sets
`request.state.authed = (not AUTH_ENABLED or ...)`, so every anonymous visitor is
the owner and may edit and delete anything. And `base.html` wraps the traffic link
and the **log out** button in `{% if auth_enabled %}`, so the only outward sign is
two controls quietly absent from a menu — which reads as "a feature has gone",
because that is what it looks like. This is not hypothetical: it is how the state
was found, weeks later, by somebody asking where the traffic page went.

Running open is a legitimate configuration. A read-only install on a home network,
or a local development copy, has no use for a login and should not be forced to
invent one. So the fix is not `${VAR:?}` in compose — that would break a supported
configuration to catch a mistake.

The real problem is that two very different situations produce byte-identical
behaviour: *"I run this open on purpose"* and *"my credentials did not arrive"*.
Nothing in the environment distinguishes them, so nothing can.

## Decision

**Add the missing bit of information, then say what it means.** `RHDB_OPEN`,
unset by default, is the operator saying *I know there is no login and I meant it*.
With that, the two situations are different configurations rather than one, and the
app can respond to each properly:

| credentials | `RHDB_OPEN` | what happens |
|---|---|---|
| set | unset | the login is on. Nothing is said. |
| set | set | the login is on; a warning says `RHDB_OPEN` is doing nothing. |
| unset | set | runs open. One `INFO` line saying so. |
| unset | unset | runs open, **loudly**: a `WARNING` at startup and a banner on every page. |

The fourth row is the one this record exists for. A missing `.env` is overwhelmingly
more likely than a deliberate open install that never set the variable, so that is
the reading the app takes, and it is wrong in the harmless direction: an operator
who did mean it sets one variable once and the noise stops for good.

**The banner is on the pages, not only in the log.** A log line only helps somebody
who goes looking, and for weeks nobody did. When the site is open, everybody looking
at it is the owner as far as the code is concerned, so there is no audience to
show it to selectively and no secret being given away — the edit buttons are
already on every page for anyone to see.

**The third row is an `INFO` and not silence.** An operator who has opted in has
said what they want and should not be nagged, but a line saying which of the two
states a process came up in is what makes a log worth reading afterwards.

**The second row warns.** Silently ignoring a variable somebody deliberately set is
the same class of fault as the one this whole record is about.

## Consequences

- One environment variable, documented in `.env.example`, passed through compose
  and explained in the manual next to the login.
- Existing installations that use a login are untouched — the first row is what
  they are in, and it says nothing, as before.
- An existing deliberately-open install starts showing a banner until it sets
  `RHDB_OPEN=1`. That is the intended cost and the one-time price of the two
  states no longer being indistinguishable.
- The announcement is a function taking both flags and returning whether to show
  the banner, called where `AUTH_ENABLED` is decided. A pure function so the suite
  can ask it what it says, rather than a side effect at import that a test has to
  race.
- Revisit if a third state appears — a read-only mode where nobody may edit and
  there is still no login would be a genuinely different answer, and a better one
  than this for the home-network case. That is a feature, not a warning.
