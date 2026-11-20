# 0053 — Search engines are given the items as a list, and leave the shuffle alone

**Status:** Accepted
**Date:** 2026-11-13

## Context

The register is meant to be found. **Block search engines** is off by default, and
every item page answers a crawler with `index, follow` and a canonical address of
its own.

In November 2026 Google had indexed 54 of the 1,030 pages the sitemap names.
Search Console filed 743 as "Discovered, currently not indexed" (never fetched,
among them every model page and every project) and 234 as "Crawled, currently not
indexed". Google crawled the site once in earnest, in the last week of July, and
fetched about 30 pages in the 90 days after. Nothing was broken: every page
answered, nothing that should be open was blocked, and the sitemap was read.

Two things kept Google's interest low. No other site links to the register, which
is outside the code. And nothing in the site gave a crawler a stable route to the
items:

- The front page, the only public list of everything, is shuffled for each visit.
  That is deliberate (MANUAL §2: a shelf is more interesting shuffled). A crawler
  saw a different 48 cards every time, and every link back into the gallery
  carries the hand (`deal=`), so each visit offered it new addresses, all of which
  name the front page as their canonical.
- The other lists were closed to it. `/parts` and `/computers` need a login,
  `/browse` is disallowed in `robots.txt` (on the assumption, written beside the
  rule, that its items were indexed already), and a part's page links to no other
  item.

So most items were known to Google only as lines in the sitemap, which it treats
as a hint and fetches last.

## Decision

**Every item is listed on one page, at `/items`.** Every computer and part by name,
with its tag and what kind of thing it is, each leading to its page. It is the same
on every visit, it is linked under the gallery's pages and it is named in the
sitemap. It lists exactly the item pages the sitemap names, and the suite holds the
two to one list. It reads the computers and parts tables rather than the register,
so a private project or a location a visitor is not shown cannot appear on it.

**Crawlers are asked to leave the shuffle alone**, with `Disallow: /*deal=`. Every
link the gallery makes back into itself carries the hand, so the rule matches all
of them and nothing else. The front page stays open, because it carries the link
to `/items`. People are not affected: a shuffle sent to somebody still opens as it
was dealt.

**The shuffle stays the default.** It is what the gallery is for, for people, and
it is not changed to suit a crawler.

## Alternatives

- **A stable order on the front page**, for everybody or for crawlers alone. The
  first gives up the shuffle. The second shows a crawler a different page from the
  one a person gets, which a search engine counts as cloaking.
- **A canonical of its own for each page of the gallery.** Every sort, category and
  layout, times every page, is a large set of near-duplicate addresses, and under
  the shuffle what is at each one still changes on every visit.
- **`rel="nofollow"` on the shuffle's links** in place of the robots rule. Google
  treats it as a hint, and its own advice for a set of addresses like this one
  (faceted navigation) is `robots.txt`.
- **Leaving it to the sitemap.** That is the state that left 743 pages unread.

## Consequences

- A crawler that reads `/items` reaches every item in one step from a page it has
  fetched, which counts for more than a line in a sitemap.
- Some link-preview services honour `robots.txt` (X's does), so a link to a
  shuffled page past the first may arrive there without a preview card. Links to
  the front page and to items are not affected. `/browse` has had the same caveat
  since it was disallowed.
- `<lastmod>` is left as it was. An item page's comes from its own history, and the
  pages without one (the front page, the lists, the models) have no honest date to
  give: an invented one teaches a search engine to ignore the dates that are true.
- No other site links to the register. That is still the largest reason it is
  crawled so little, and no change to the code can fix it.
