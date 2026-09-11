# 0012 — Run alongside an existing reverse proxy

**Status:** Proposed
**Date:** 2026-09-07

## Context

The stack ships batteries-included: Caddy binds host `80`/`443` and terminates TLS
via Let's Encrypt, on the assumption of a dedicated instance (or at least its own
IP). Community feedback shows people want to run it on a **shared host behind an
existing proxy**, where `80`/`443` already clash — one runs an nginx proxy
already, another changed the ports in the compose file by hand.

An admin panel to change ports was floated and rejected. Host port bindings are
set by Docker/Compose at container start, from *outside* the app; a web panel
served *through* those ports cannot rebind them without restarting the whole
stack, and giving the app the docker-socket/host access to do so would undo the
deliberate non-root, no-host-access posture of a public-facing service.
Port/proxy topology is deployment configuration — which this project reads from
the environment at startup (backend-standards) — not runtime admin state.

## Decision

Offer **two deployment modes from one codebase and one image**; the only
difference is a compose layer, never the app or the image:

- **Bundled proxy (default):** core services **+ Caddy**, Let's Encrypt TLS. The
  "works on a fresh box" experience we have today.
- **Bring-your-own-proxy:** the core stack **without Caddy**, the app exposed on a
  localhost port for an existing nginx/traefik to sit in front of and terminate
  TLS.

Caddy's host ports become environment-driven (e.g. `RHDB_HTTP_PORT`/
`RHDB_HTTPS_PORT`) so bundled mode can move off `80`/`443` without editing compose.
Deliver as compose layers (base + a Caddy layer, or a behind-proxy layer),
documented as two modes — **not** as two separately maintained versions, which
would drift.

Two things Caddy does today have to survive its absence, or bring-your-own-proxy
mode would be quietly less safe than the default:

- **The app trusts forwarded headers from any address** (`--forwarded-allow-ips`
  in `entrypoint.sh`), so that a request which reached Caddy over HTTPS is known to
  have done so. That is sound only while the proxy is the sole route to the app.
  In this mode the app's port stays bound to `127.0.0.1` (or to a network only the
  proxy is on), and the proxy must set `X-Forwarded-Proto` and *append* the client
  to `X-Forwarded-For` (nginx's `$proxy_add_x_forwarded_for`). An app port anyone
  else can reach would let a client choose the address the login rate limiter sees
  and claim an HTTPS it never used.
- **The edge headers `security-standards` requires** — HSTS, `nosniff`, the
  referrer policy, `X-Frame-Options`, and the Content-Security-Policy once it lands
  — are all sent from the `Caddyfile`. Without Caddy they vanish, and nothing would
  say so. The app sends them itself, from one small middleware, so they hold in
  both modes whatever sits in front; the `Caddyfile` stops carrying them. (The
  alternative — documenting the headers for the operator to add by hand — puts the
  site's XSS defence in a config file this project cannot see or test.)

## Consequences

- A shared-host user runs bring-your-own-proxy mode: no port clash, their proxy
  does TLS; Caddy's redundant TLS is simply not started.
- Non-standard ports become two environment variables, not a compose edit.
- One image and one code path — the choice is which compose file(s) you bring up,
  so there is nothing to keep in sync.
- The non-root, no-docker-access security posture is preserved (no
  admin-panel-rebinds-ports).
- The security headers move from the `Caddyfile` into the app, which also puts
  them under test for the first time: today nothing in the suite would notice one
  going missing.
- A bring-your-own-proxy operator owns TLS, compression and the forwarded headers.
  INSTALL.md gives a known-good nginx block rather than a description of one.
- Revisit if a genuinely different topology appears (e.g. several installs sharing
  one Caddy), or if the two-file split proves confusing enough to warrant Compose
  profiles or a small helper script.
