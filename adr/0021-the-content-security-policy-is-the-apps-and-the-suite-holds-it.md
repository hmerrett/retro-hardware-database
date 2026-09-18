# 0021 — The Content-Security-Policy is the app's, and the suite holds it

**Status:** Accepted
**Date:** 2026-09-18

## Context

A Content-Security-Policy is the strongest single control this app can put in
front of cross-site scripting, and it has been waiting on a refactor rather than
on a decision. `base.html` carried 1,526 lines of inline JavaScript, so any policy
worth sending would have had to allow `'unsafe-inline'` on scripts, which is the
one thing a policy is for. That work is done: the JavaScript is in eight static
files, the seventeen values the templates used to write into it are JSON data
islands and `data-` attributes, and the eight `onsubmit` handlers are one
delegated listener. Nothing inline is left to allow.

Three questions were open, and the answers are not the obvious ones.

**Where the header comes from.** Every other security header — HSTS, `nosniff`,
the referrer policy, `X-Frame-Options` — is sent by Caddy, so the edge is where a
new one would go by habit. But those four are facts about *transport and framing*,
true whatever the app happens to render. A content policy is a fact about *this
app's own markup and static files*: which scripts it loads, which origins it
reaches, whether its templates carry style attributes. It changes when a template
changes, and the thing that knows a template changed is the test suite. A policy
in the Caddyfile is a policy no test can see — CI could never prove the header
ships, nor that the markup still fits it, and a dev stack or any install not
behind Caddy would have no policy at all.

**Whether to soak it report-only first.** The standard advice is to send
`Content-Security-Policy-Report-Only` for a week and read what real traffic would
have broken. That advice assumes real traffic. This is a self-hosted register for
one collection; a quiet week would be quiet because nobody visited, and reading
that silence as proof would be the same mistake as a monitor that only greps for
success. A browser driven across every page and every scripted interaction
exercises more of the site in ten minutes than a week here would, and it says what
broke rather than what did not report.

**What stops it rotting.** A policy proved once is proved for the markup that
existed that day. The failure that matters is the inline handler somebody adds in
six months, which breaks a page for every visitor and nothing catches.

## Decision

**The app sends the policy, and the suite holds both halves of it.**

A `content_security_policy` middleware in `main.py`, beside `no_stale_pages`,
registered last so it is outermost and therefore covers the responses the auth
gate makes itself — a login redirect is a response too. The policy:

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self';
frame-ancestors 'self'; base-uri 'none'; object-src 'none'
```

`form-action`, `frame-ancestors` and `base-uri` are stated because they do not
fall back to `default-src`; `frame-ancestors 'self'` says what the existing
`X-Frame-Options: SAMEORIGIN` says, to the browsers that read the newer one.
Everything the app loads is its own: `img_url` always yields `/images/...`,
reference photographs are fetched server-side into that volume rather than hot-
linked, and the QR decoder is vendored under `/static/vendor/`. So `'self'`
everywhere is not an aspiration, it is a description.

**`style-src` keeps `'unsafe-inline'`, and the suite knows why.** There are 69
`style` attributes across 19 templates and two small `<style>` blocks. Removing
them is a real piece of work and an independent one, and `'unsafe-inline'` on
styles is a much smaller hole than on scripts — it buys an attacker who already
has injection the ability to restyle a page, not to run code. Taking it out is a
later change, and a test ties the two together so it cannot be taken out while the
attributes are still there.

**Three `javascript:` links go.** `project_form.html`, `part_form.html` and
`computer_form.html` each carried `<a href="javascript:history.back()">`, which
`script-src 'self'` blocks. They become a `<button type="button" data-back>` read
by the same delegated listener that reads `data-confirm` — which is also the
honest markup, because going back is an action and not a destination.
`security-standards` already forbids `javascript:` in link-building filters; these
were hand-written and never met it.

**No report-only phase.** What replaces it is a browser, in Docker, driven across
every page and every scripted interaction with a `securitypolicyviolation`
listener attached, run once before the change ships. That is a one-off and is not
in CI — a browser and a full stack are too much to ask of every pull request — so
the durable half is a suite test that reads the policy and asserts the rendered
pages cannot violate it: no inline script the policy forbids, no inline handler,
nothing loaded off-site, and style attributes tied to the `'unsafe-inline'` token.

## Consequences

- CI proves, on every pull request, that the header ships and that the markup
  still fits it. A template that grows an inline handler fails a test instead of
  breaking a page.
- The policy applies wherever the app runs, not only behind Caddy. The Caddyfile
  keeps the four transport headers and says where the content policy now lives, so
  a reader who looks in the obvious place is told the non-obvious answer.
- A second source of truth is refused: Caddy does not also assert a fallback
  policy, because two policies drift apart and the tighter one wins in a way
  nobody predicted.
- `'unsafe-inline'` on `style-src` is a stated, tested compromise with a named
  exit, not an oversight — and the exit is cheap to check, because the test that
  permits it fails the moment it is removed without the attributes going too.
- The proof that it works in a browser is a one-off. It is repeatable — the
  overlay and the crawl script are in `tools/` — but nothing runs it for you, so a
  change that only a browser could catch is caught only if somebody runs it.
