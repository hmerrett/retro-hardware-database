# Security standards

The rules this app holds to, distilled from the hardening round. British English.
The theme is **defence in depth**: several cheap layers, none relied on alone.

## Secrets & sessions

- Secrets come from the environment; never committed. `.env` gitignored,
  `.env.example` committed.
- **A key handed out is never stored** (ADR-0032). A session cookie and an API
  token are random (`secrets.token_urlsafe(32)`), shown once, and kept as a
  SHA-256 digest; a password is an argon2id hash. Nothing that can be used to sign
  in is written to the log — the setup code is the one exception, because being
  read out of the log is its whole job.
- Sessions are rows, so ending one is deleting it: logging out, switching an
  account off and changing a password all take effect on the next request. Do
  not go back to a signed cookie; it cannot be withdrawn.
- A wrong username costs the same as a wrong password (a decoy hash is verified),
  so the login does not say which usernames exist.
- Compare secrets with a constant-time compare (`secrets.compare_digest`).
- Session cookies: `HttpOnly`, `SameSite=Lax`, `Secure` behind HTTPS.

## Authentication

- **Rate-limit authentication attempts** (login form, setup code, API token and
  HTTP Basic), keyed by the real client IP. Behind Caddy that's the **rightmost**
  `X-Forwarded-For` entry — the one the proxy adds and a client cannot forge.
- **Ask for a permission, never a role.** `can(principal, permission)` in
  `accounts/roles.py` is the only check. `request.state.authed` means *may edit*;
  anything about *reading* what a visitor is not shown asks `sees_private`. A
  page that asks the wrong one hides something from a viewer rather than showing
  it to a stranger, which is the direction to fail in.
- **A new page is an administrator's until it is listed.** The gate lets a viewer
  read public pages, the JSON API's `GET`s and `VIEWER_PAGES`, and nothing else,
  so a page nobody thought about is kept back rather than shown.
- **There is no running without a login** (ADR-0032, superseding ADR-0019). A site
  with no accounts shows only `/setup`, which wants the code from the log, so an
  install is never claimable by whoever finds its address first. A site anybody
  may read is a site with accounts and **Visitors must log in** off.
- **A security-relevant configuration says which state it came up in.** A mode
  that can only be inferred by noticing what is missing from a menu is a mode
  nobody notices for weeks.

## Input & output

- **Validate uploads by content, not by filename.** Decode an uploaded image with
  Pillow and check its real format; reject anything else. Do it before the record
  is committed and at the write path.
- Serve user-supplied files as downloads: `Content-Disposition: attachment` and
  `X-Content-Type-Options: nosniff`, opened by id, not by the URL's filename. The
  one exception is a PDF, which may be shown inline (ADR-0030): named `.pdf`,
  beginning `%PDF-`, served as `application/pdf` by the server's say-so with
  `nosniff` and a policy of its own. Anything failing either check is a download.
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
- **The Content-Security-Policy is the app's, not Caddy's** (ADR-0021). It is a
  fact about these templates and static files rather than about transport, so it
  is sent by a middleware in `main.py`, where the suite can read it and where it
  holds for an install that is not behind Caddy. Caddy does not send a second one:
  two policies drift apart. Everything is `'self'`, with no token anywhere
  (ADR-0022).
- **New markup fits the policy, and the suite says so.** No inline `<script>`
  (a data island carries values instead — `type="application/json"`), no `on*=`
  handler (delegate from a static file, as `data-confirm` and `data-back` do), no
  `style` attribute and no `<style>` block (a class in `app.css`; a value the
  template works out names a rule generated into `/style/data.css` by
  `datacss.py`), no `javascript:` URL, nothing loaded from another origin. `test_content_security_policy.py`
  walks the rendered pages for each of those, because a violation is silent in
  the browser and invisible in review.

## Dependencies

- Pinned/locked and scanned (`pip-audit` in CI). Pinning gives control; scanning
  gives awareness — you need both.

## A column kept off the page is kept out of the search

`search._haystack` builds its string from **every column on the model** — that is
what makes "search any field" true rather than nearly true. So a new column joins
what an anonymous visitor can search by merely existing, with nobody having decided
it should: a boolean reads as `True`, and a search for `true` hands back every row
carrying it. Anything owner-only goes in `common.OWNER_ONLY`, which `_haystack`
reads, and gets a test (ADR-0018). Hiding it in the template is half the job.

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
  already public. Anything uploaded since starts private -- unless the owner has
  turned on **New files are public**, which starts the upload's tick ticked where
  the form shows it, and never on a private project's page (ADR-0029).
- A file may be linked to a project. A visitor is never told a file is linked to a
  private project: the links a visitor is shown, and the list's search, leave it
  out (ADR-0028).
