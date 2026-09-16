# 0017 — A page of photographs shares a montage of them

**Status:** Accepted
**Date:** 2026-09-16

## Context

An item's shared link already previews as the item. `_og` takes the first
photograph off a computer or a part, ADR-0015's sibling change gave a project the
first photograph of its members, and only a thing nobody has been round with a
camera for falls back to `SITE_CARD` — the logo on cream.

The pages that are *walls* of photographs never got that far. The gallery, a
`/browse` slice behind a figure on `/stats`, a search, and the projects list all
share as the logo, because none of them has a single photograph to be "the"
photograph. So a link to a search for `sound blaster` and a link to the front page
and a link to `/files` all preview identically, which is to say none of them
previews as anything. The one page of the four that is most worth sending
somebody — the answer to a search — is the one carrying the least about itself.

Open Graph takes one image. "A few images from the results" therefore has to
become one picture made out of several, server-side, before the tag is written.
Pillow is already a pinned dependency doing watermarks, resized copies and the
tuneup, and `thumbs.py` already keeps small copies of every photograph, so the
work is a resize-and-paste of four small JPEGs rather than a new capability.

The awkward part is not the drawing. It is that a search card's URL is derived
from a query string, and a crawler fetching an `og:image` is anonymous, so
whatever is behind that URL is an unauthenticated endpoint that a stranger can
ask to do work and to write a file.

## Decision

**A page that renders the card grid shares a montage of the first four
photographs on it.** The gallery, `/browse`, a search on either, and the projects
list. `/files`, `/stats` and `/machines` keep the site card: they have no
photographs on them, and a picture of four unrelated machines would describe a
page of drivers less well than the logo does.

**Up to four, in a 2×2, on the site card's cream.** Fewer fill the space rather
than leaving a hole — one fills the frame, two sit side by side, three go as one
large left with two stacked right. Four is the ceiling because a preview is
rendered at something like 500px wide in a chat client, where a fifth photograph
stops being a photograph.

**Nothing is written on the card.** No query text, no count. `og:title` and
`og:description` already carry those and every preview shows them beside the
image; drawing words would also need a font file, and an installation's
`branding/` is its own (ADR-0011) and may not ship one.

**One mark, not four.** Every photograph `/images` hands out carries the site's
mark in its corner, so a single-photograph card is watermarked and a montage
should be too. But a montage is one picture, not four, and tiling four
watermarked copies would put four marks on it — each of them cropped to wherever
the tile's corner happened to fall. So the tiles are cut from the photographs
themselves and the finished card is marked once, in its own bottom-right, at the
card's scale. That also keeps `cards` out of the resized-copy cache, which is
keyed on the photograph and the width and holds the watermarked copy the pages
ask for; a second writer with a different idea of what belongs under that key
would quietly serve the wrong thing on the item pages.

**The card is content-addressed.** The key is the chosen photographs and their
modification times, hashed — not the query. Two different searches that land on
the same four machines are one cached card, `?q=c64` and `?q=commodore+64` cost
what one of them costs, and re-photographing an item changes the key rather than
needing anything invalidated. The URL can therefore be served `immutable` for a
year on the same reasoning `img_url`'s `?v=` stamp already earns.

That is also what defuses the endpoint. `/og/{name}` opens a file by hash and
serves it or answers 404; it never sees a query, never searches, and never writes.
The montage is built while the page that names it is being rendered, from rows
that page has already loaded, and only on a cache miss.

**Only photographs that are already public go on a card.** Every photograph under
`/images` is served to anybody who asks, so a montage of computers and parts
discloses nothing that the item pages do not. The projects list is the one place
the question has an edge, and a private project contributes no photograph to it —
the same rule, read off the same `authed` flag, as the rows on the page.

**The cache is bounded and swept.** It lives under `images/.og/b<BUILD>/`, beside
`.wm` and `.sized` and swept the way those are, so a change to how cards are made
misses the old ones rather than serving them. On a miss, once the new card is
written, the oldest are dropped back to a cap. A query string is an unbounded key
space even when the photographs behind it are not, and a cache with no ceiling on
a public endpoint is a disk-filler waiting for somebody bored.

## Consequences

- A shared search is worth sending. That is the whole point, and it is the thing
  that could not be had any other way: a link to thirty floppy drives now looks
  like floppy drives.
- The front page stops being the logo. The logo is still what a page with no
  photographs shows, which is what `SITE_CARD` was added for; it is no longer what
  the collection shows.
- A gallery render on a cache miss pays for one composite — four resizes and a
  JPEG encode, off copies `thumbs` has already made. A hit costs one `stat`.
  Misses are rare by construction, because the key is the photographs.
- `og:image` dimensions are now constant at 1200×630 for these four pages, so a
  preview lays them out without a probe fetch, which `_image_size` has to open the
  file to answer for a single photograph.
- Revisit if the cap is ever reached in anger. It being reached would mean either
  a collection far larger than this one or somebody enumerating queries, and those
  two want different answers — a bigger cap, and a rate limit.
