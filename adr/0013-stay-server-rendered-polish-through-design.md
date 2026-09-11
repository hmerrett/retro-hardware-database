# 0013 — Stay server-rendered; polish comes from design, not a SPA

**Status:** Proposed
**Date:** 2026-09-07

## Context

The app is server-rendered Jinja with a little plain JavaScript, chosen
deliberately for public, crawlable item pages reached by the QR labels. The
question has been asked whether making it *feel* professional rather than
hobbyist needs splitting the frontend from the backend and adopting a client
framework (React) — partly on security grounds.

Two beliefs to settle. **Security:** a SPA plus a public JSON API *widens* the
attack surface, it does not shrink it — a large npm dependency tree, client-side
XSS vectors, and auth tokens in JS-reachable storage — against the current
`HttpOnly`, `SameSite=Lax`, `Secure` signed cookie and autoescaped templates (with
a Content-Security-Policy on the roadmap). A split is at best neutral for security,
usually worse. **Polish:** a professional feel comes from *design* — typography,
spacing, colour, consistency, responsiveness, and small interactions — not from a
framework; substantial server-rendered sites (GitHub, Stripe, GOV.UK) are the
proof.

## Decision

Keep server-side rendering. **Do not split frontend/backend or adopt a SPA for
this app.** Reach a professional look and feel on the current stack by investing
in:

- a coherent **CSS design system** — a utility framework such as Tailwind, or a
  set of design tokens;
- **lightweight progressive-enhancement JS** for app-like interactions without a
  SPA — **htmx** for server-rendered fragment swaps (inline edit, live search, no
  full-page reloads) and/or **Alpine.js** for small client interactivity;
- **reusable Jinja partials/macros** for consistency (buttons, cards, form fields,
  item tiles).

Whatever is picked has to run under the Content-Security-Policy on the roadmap:
no inline script and no `eval`. That rules out Tailwind's play CDN (build it with
the standalone CLI instead, no Node needed at runtime), means htmx with
`allowEval` off, and means Alpine's CSP build rather than its standard one.

The existing `/api/*` routes keep a future SPA or native client possible *without*
a rewrite, so nothing here forecloses one.

## Consequences

- UX improvements become an incremental restyle plus interaction polish on the
  stack we have — no rewrite, no FE/BE split, no security downgrade, crawlable
  pages intact.
- The "a modern feel needs React" assumption is retired for this project; design
  investment, not a framework, is where the effort goes.
- Revisit — with a new ADR that supersedes this one — if the product genuinely
  needs a highly interactive, stateful client (drag-and-drop board, live canvas,
  offline-first native app) or a second distinct client. That is the trigger to
  reconsider a SPA, with eyes open to the added surface.
