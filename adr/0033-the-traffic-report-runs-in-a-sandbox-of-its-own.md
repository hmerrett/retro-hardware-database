# 0033 — The traffic report runs in a sandbox of its own

**Status:** Accepted
**Date:** 2026-09-27
**Amends:** [ADR-0021](0021-the-content-security-policy-is-the-apps-and-the-suite-holds-it.md)
— a second response carries a policy of its own, and it is the one place script
is allowed inline.

## Context

`/traffic` hands out the report GoAccess writes from the access logs: one
self-contained HTML file, its styles, scripts, fonts and figures all written into
the page. Under the site's policy, `'self'` in every directive (ADR-0021,
ADR-0022), every one of its twenty inline scripts and three style blocks is
refused, and since the policy arrived the page has been GoAccess's bare markup
with nothing drawn in it.

Allowing it is not only a matter of a header. Every path, referrer and user agent
in the report is whatever a stranger's request said, and GoAccess's scripts put
them on the page; keeping them inert is GoAccess's escaping. And `/traffic` is an
administrator's page on the register's own origin, so script allowed there as it
stands would, on a slip in that escaping, run as a signed-in administrator, free
to do whatever the settings and account pages can.

GoAccess also compiles its templates in the browser — Hogan turns each into a
function with `new Function` — so a policy that allows its inline script and not
`eval` still draws nothing: the page stops at its first template. Checked in
Chromium, Firefox and WebKit against a report from GoAccess 1.12.

Three other answers were weighed: Caddy serving the report on a hostname of its
own behind a login of its own, so none of its script runs on the register's
origin (a second hostname, certificate and password outside the register's
accounts, ADR-0032); drawing GoAccess's JSON output in a template of the
register's (a page to design, and a JSON shape to keep up with); and dropping
`/traffic` altogether.

## Decision

**The report is sent with a policy of its own, and that policy puts it in a
sandbox.**

```
default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval';
style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none';
form-action 'none'; frame-ancestors 'self'; base-uri 'none'; sandbox allow-scripts
```

`sandbox allow-scripts`, without `allow-same-origin`, gives the page an origin of
its own that is nobody's: its scripts cannot read the site's storage or cookies,
nothing they send is sent as the site, and the sandbox grants nothing else — no
forms, no pop-ups, no downloads. Nothing is loaded from anywhere either: fonts
and images only as `data:`, which is how GoAccess writes them into the file, and
no requests (`connect-src 'none'`) or form posts (`form-action 'none'`) to reach
anything with.

**`'unsafe-inline'` and `'unsafe-eval'` are allowed here and nowhere else.** This
is the one response whose scripts are not the register's, so the one that cannot
be brought to `'self'` short of rewriting GoAccess — and the one the sandbox has
taken off the site's origin, where `eval` gives a slip nothing that the inline
script beside it does not already have. The site's policy is unchanged, and the
middleware still sets it wherever a response has not said its own, which is now
two: a PDF (ADR-0030) and this. With no report yet, `/traffic` is the site's own
page, under the site's policy.

**The GoAccess image is pinned to a release** (`allinurl/goaccess:1.12`), so a new
one is read before it runs in an administrator's browser rather than arriving with
the next pull.

## Consequences

- The report draws again: pixel for pixel what it draws with no policy at all, in
  all three engines.
- It has nowhere to keep anything and no way to hand over a file, so a theme or a
  layout chosen in its options is forgotten when the page is left, and its
  **Export as JSON** does nothing. `MANUAL.md` says so.
- Script is still loosened on the one route whose contents strangers write. Inside
  the sandbox a slip can redraw the page, or send the tab elsewhere and take with
  it what the page shows — the visitors' addresses among it. What it cannot do is
  act as the administrator or reach anything else of the site's, which is what the
  sandbox is for.
- A new GoAccess release is a change to review: move the tag, read what the
  release changed, and open its report under this policy in a browser, as was
  done for this one. Nothing runs that check for you.
- The suite holds the policy to the one recorded here and its sandbox to scripts
  alone, and walks the page shown before the first report with the rest of the
  site's (`test_content_security_policy.py`).
- Revisit if GoAccess ships its templates compiled, which would let
  `'unsafe-eval'` go.
