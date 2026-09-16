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
- **A public endpoint that generates and keeps a file is keyed by content, not by
  what was typed.** The share-card montage (ADR-0017) hashes the photographs it is
  made of, so `/og/{name}` opens a file by hash rather than searching on a query a
  stranger supplied, and its cache is capped and swept. A query string is an
  unbounded key space; a cache with no ceiling on an anonymous route is a
  disk-filler.
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

## Who may see it is decided, not defaulted

Anything new that stores or shows what somebody supplied -- an upload, a note, a
field, a page -- decides who may see it as part of its design, not afterwards.

- **If the request does not say, ask before building.** This applies with most
  force to work done with an AI or agentic coding tool: a prompt that asks for a
  feature and is silent on visibility has left the question open, and the tool
  asks the owner rather than choosing an answer for them.
- **When it is still unclear, least privilege.** Visible to the owner alone until
  something publishes it. The failure modes are not symmetrical: a thing kept back
  by mistake is noticed the next time the owner looks; a thing published by
  mistake is noticed by nobody, possibly after a search engine has taken a copy.
- **A public default needs its reasoning written down**, as an ADR. ADR-0004 is
  what that looks like when the answer is public; ADR-0009 is what it looks like
  when the same question, asked of uploads, comes out the other way.

## Uploaded files are published by hand

**A file is not public until it is ticked** (`files.public`, default false,
ADR-0009). This was the open decision the owner has now made: the same box that
takes a driver disk takes a receipt with a name, an address and a card's last
four digits on it.

- Gate the **listing and the download alike**. A file kept off an item page and
  still fetchable at its URL is not private, and neither is one kept off the page
  and listed under its own tag at `/files?tag=…`.
- An unpublished file answers **404, not 401**. There is no account a reader could
  hold, so an authentication prompt would only confirm the file exists.
- Serve it `private, no-store`. Unticking the box has to stop the copy being
  handed out, which a cache holding the published `max-age` would not.
- The files already on file when 0035 ran were published by it, because they were
  already public. Anything uploaded since starts private.
