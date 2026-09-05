# Security standards

The rules this app holds to, distilled from the hardening round. British English.
The theme is **defence in depth**: several cheap layers, none relied on alone.

## Secrets & sessions

- Secrets come from the environment; never committed. `.env` gitignored,
  `.env.example` committed.
- The **session-signing key (`RHDB_SECRET_KEY`) must be independent of the
  credentials** and high-entropy (`openssl rand -hex 32`). Never derive it from
  the username/password — the signed cookie's payload is constant, so a
  credential-derived key turns a leaked cookie into an offline password oracle.
  The app requires the key when auth is enabled (fails to start without it).
- Compare credentials with a constant-time compare (`secrets.compare_digest`).
- Session cookies: `HttpOnly`, `SameSite=Lax`, `Secure` behind HTTPS.

## Authentication

- **Rate-limit authentication attempts** (login form and HTTP Basic), keyed by
  the real client IP. Behind Caddy that's the **rightmost** `X-Forwarded-For`
  entry — the one the proxy adds and a client cannot forge.

## Input & output

- **Validate uploads by content, not by filename.** Decode an uploaded image with
  Pillow and check its real format; reject anything else. Do it before the record
  is committed and at the write path.
- Serve user-supplied files as downloads: `Content-Disposition: attachment` and
  `X-Content-Type-Options: nosniff`, opened by id, not by the URL's filename.
- Templates autoescape; keep it on. Any link-building filter uses a strict scheme
  allowlist (no `javascript:`/`data:`).

## Outbound requests (SSRF)

- When the server fetches a user-supplied URL (e.g. reference-image enrichment),
  allow only `http`/`https` and only hosts that resolve to **public** addresses —
  block private/loopback/link-local/metadata ranges. **Validate every redirect
  hop**, not just the first URL.

## Edge headers

- Caddy sends HSTS, `X-Content-Type-Options: nosniff`, a `Referrer-Policy` and
  `X-Frame-Options`.
- *Adopt next:* a **Content-Security-Policy** — possible once `base.html`'s inline
  scripts move to static files (workflow-and-ci). This is the strongest single
  anti-XSS control, so it's the payoff of that refactor.

## Dependencies

- Pinned/locked and scanned (`pip-audit` in CI). Pinning gives control; scanning
  gives awareness — you need both.

## Open decision for the owner

Uploaded files (including anything pinned to an asset as a "receipt") are
currently **public**. If receipts can carry names/addresses/payment details and
should be private, that needs a private-file flag, a gate on the download route,
and a marker in the files UI. Owner's call — don't change it silently.
