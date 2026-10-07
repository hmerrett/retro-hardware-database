# 0035 — A text file is read as a page of the register

**Status:** Accepted
**Date:** 2026-10-07
**Amends:** [ADR-0030](0030-a-pdf-is-read-in-the-browser.md)
— a second kind of file is shown rather than saved.

## Context

ADR-0030 made a PDF the one file shown in the browser, and said to revisit before
adding a second. The owner asked for Markdown files to be read the way a PDF is,
and set in the site's own look rather than somebody else's.

A browser has no viewer for Markdown. Handed one as `text/plain` it shows the
source; handed one as HTML made from the file, it would run whatever the file
wrote, as this site, with this site's cookies. A plain text file the browser will
show, but in its own default face on white whatever the theme, wrapped or not as it
likes, and in whatever encoding it guesses -- and a readme off a driver disk is
code page 437, which a browser guesses as Windows-1252 and draws its box drawing as
a row of accented capitals.

The same handful of plain text names come with old hardware: `README.TXT`,
`READ.ME`, `FILE_ID.DIZ`, an `.NFO`, the `AUTOEXEC.BAT` and `CONFIG.SYS` a machine
was set up with.

## Decision

**A text file is never handed to the browser as itself.** The server reads it and
puts what it says into a page of the register, at the PDF's address,
`/files/<id>/view/<name>`. So it is the site's page under the site's policy
(ADR-0021): the stylesheet, both themes, the banner, the reading column. The file is
only ever words in it.

**Which files.** By the end of the name: `.md` and `.markdown` as Markdown; `.txt`,
`.nfo`, `.diz`, `.me`, `.1st`, `.bat`, `.ini` and `.cfg` as plain text; and
`CONFIG.SYS` by its whole name, since most `.sys` files are drivers. And by the
bytes, when it is asked for: no zero byte anywhere (text has none, and nearly every
binary format has some -- the test git uses), and no more than 1 MiB. Anything else
is redirected to its download, as a PDF that is not one is.

**How it is read.** UTF-8 if it decodes as UTF-8, with a byte-order mark dropped;
otherwise code page 437. Line endings become newlines; the remaining control
characters, a DOS file's closing Ctrl-Z among them, are dropped, since none of them
is a character a page can show.

**Plain text** goes to the template as a string, which autoescapes it, inside a
`<pre>` that keeps every space and scrolls rather than wraps. Its addresses are
linked by the filter a note's are (`entry.linked`). Text that draws boxes is set in
a face that has the characters to draw them (see Consequences).

**Markdown** is parsed by markdown-it-py -- CommonMark, with GitHub's tables and
strikethrough -- with HTML switched off, so anything the file writes as markup
arrives as the characters it is. The tokens are then walked before they are
rendered (`textfiles._for_the_page`), so that nothing drawn asks for what the
policy refuses:

- a link keeps its target only for the schemes a note's links may have (`http`,
  `https`, `ftp`, `ftps`, `sftp`, `mailto`), a heading in the same file, or a page
  of this site. Any other link -- most often to a file that sat beside this one in
  its folder -- is shown as its words. Off-site links open a tab of their own, with
  `noopener noreferrer`, as a note's do;
- a picture is shown as its description, never fetched: the policy loads nothing
  from another site, and a picture in the file's folder is not in the register;
- a heading goes down a level, under the page's own `<h1>`, which is the file's
  name, and gets an anchor prefixed `doc-`, so a contents list works and a file
  cannot give a heading the id of something on the page around it (`main`, `q`);
- a table's header cells carry `scope`, its column alignment is a class rather
  than the `style` attribute the parser writes (ADR-0022), and the table sits in a
  box that scrolls sideways on a narrow screen.

**Who may see it, and how long it is kept**, are the download's rules (ADR-0009):
an unpublished file is "not found" to a visitor here as everywhere, and its page is
sent `private, no-store`. A published one is a page like any other, `no-cache`.

## Alternatives

- **Render it in the browser** with a script. A second Markdown parser in
  `static/`, vendored and audited; the escaping done where the suite cannot read it;
  and nothing at all for a browser running no script. Server-rendering is the
  register's way (ADR-0013), and keeps the whole of the safety argument in Python
  under test.
- **Serve it as `text/plain`.** No theme, no headings, the browser's own wrapping
  and its guess at the encoding.
- **Python-Markdown.** Not CommonMark, and it passes raw HTML through, with no safe
  mode since 3.0, so safety would rest on a sanitiser: `bleach` is deprecated and
  `nh3` is a compiled extension to keep in step. markdown-it-py escapes at the
  source, and was already in the lock, as a dependency of the tools pip-audit uses.
- **Allow some HTML through a sanitiser** -- a centred logo, a `<details>`. A
  sanitiser is an allowlist that has to be right for ever; shown as text is right by
  construction.

## Consequences

- `markdown-it-py` (and `mdurl` with it) is a runtime dependency, pinned, and the
  `pip-audit` of the runtime half of the lock now covers it.
- A README that leans on HTML shows its tags as text, and its pictures as words.
- The 1 MiB ceiling bounds what a visitor can ask the server to parse in one
  request on a public route.
- The register's fixed-width face is a Latin subset with no box drawing. Left to
  itself the browser draws a box's lines in whatever face it finds and its letters
  in this one, and the corners miss: Consolas, the face Windows finds, is nearly a
  tenth narrower. So text that draws with box-drawing characters -- a plain text
  file, or a block of code in Markdown, a folder tree say -- is set wholly in the
  reader's own fixed-width face, which has both at one width. Text that does not
  keeps the register's face.
- The next kind to be shown rather than saved is still the one ADR-0030 named: an
  image, with its bytes checked by Pillow, not its name.
