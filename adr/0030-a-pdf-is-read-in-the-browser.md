# 0030 — A PDF is read in the browser, and everything else is still a download

**Status:** Accepted
**Date:** 2026-09-24
**Amends:** [ADR-0021](0021-the-content-security-policy-is-the-apps-and-the-suite-holds-it.md)
— one response carries a policy of its own.

## Context

Every file kept beside the register is handed over as an attachment, as
`application/octet-stream`, with `nosniff`. That is `security-standards`, and it is
right: an upload is whatever somebody sent, and an HTML file or an SVG shown by the
browser would run as this site, with this site's cookies.

It is also why a manual cannot be read without being saved first, and manuals are
most of what the register keeps: eight of the twelve files on the owner's
installation are PDFs. On a phone the difference is a file in the downloads folder
against a page you can read.

A PDF is not a page. Browsers show one in a viewer of their own, which draws it
without the site's scripts or styles. What it needs from the response is to be
told it is a PDF, truthfully, and to be allowed to be shown.

## Decision

**A file named `.pdf` whose bytes begin `%PDF-` within the first KiB is offered at
`/files/<id>/view/<name>`**, served as `application/pdf`, `inline`, with `nosniff`.
The type is the server's: it is never taken from the upload. A file that fails
either check is redirected to its download, so a file called a PDF that is
something else is never shown, whatever it is called.

**That response carries a policy of its own.** The site's says `object-src 'none'`,
which is right for its pages and blanks the viewer in browsers that show a PDF as a
plugin inside a page they make themselves. The PDF's policy allows objects from the
site and nothing else at all: no script, no style of the site's, no frame, no form.

Who may see it, and how long it is kept, are the download's rules exactly
(ADR-0009): an unpublished PDF is not found by a visitor at either address, and is
served `private, no-store`.

## Consequences

- A manual opens where it is tapped, in the viewer the reader already knows.
- A PDF's own scripts are the viewer's business, not the site's. The major
  browsers' viewers run them in a sandbox or not at all, and none of them run a
  PDF as this site. That is a trust placed in the browser, and it is the one this
  decision takes on.
- Some phones' browsers have no viewer and save the file anyway, which is where
  the register was before.
- `security-standards` says "serve user-supplied files as downloads" with this as
  its one exception, and the middleware's docstring stops saying no route has a
  policy of its own.
- Revisit before adding a second kind that is shown rather than saved. An image
  would be the obvious next one, and it would need its bytes checked the way a
  photograph's are: Pillow, not the name.
