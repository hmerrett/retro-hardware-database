# 0022 — No style attribute, and the rules whose values are data are generated

**Status:** Accepted
**Date:** 2026-09-18

## Context

[ADR-0021](0021-the-content-security-policy-is-the-apps-and-the-suite-holds-it.md)
sent a Content-Security-Policy with `script-src 'self'` and meant it, and kept
`'unsafe-inline'` on `style-src` alone, with the exit named: 69 `style` attributes
across nineteen templates and two `<style>` blocks. This is that exit.

The token on styles is a smaller hole than the same token on scripts — it buys an
attacker who already has an injection the ability to restyle a page rather than to
run code. It is not nothing. A restyled page is a page that can be made to say
something it does not say: a control moved under the pointer, a warning coloured
away, a confirmation page's "this cannot be undone" set to the background colour.
The register is a product other people run
([ADR-0011](0011-the-register-is-a-product-other-people-run.md)), and "a smaller
hole" is a poor answer to give an installer who asked why the policy has a hole in
it at all.

Sixty-seven of the attributes were a margin, a `flex: 1` or a `display: none` on
one element. Those are a mechanical change. Two were not, and they are the
interesting part:

- the swatch that shows a bezel's shade and how far it has yellowed, whose
  background is mixed in Python from the colour vocabulary (`entry.bezel_css`);
- the bar on `/stats`, whose width is a percentage the template works out per row.

Neither value exists when `app.css` is written. Both were the reason to think the
token was permanent.

## Decision

**No style attribute in any template, and no `<style>` block. The policy is
`style-src 'self'`.**

The 67 one-offs are classes at the end of `app.css`, named for what they do, in a
block that says why they are there and why it stays last in the file — several of
them override a rule of equal specificity, and at equal specificity the later rule
wins, which is what an inline style used to do by outranking everything. The two
`<style>` blocks are ordinary rules in the same file.

**The two whose values are data are generated into a stylesheet of their own**,
`app/datacss.py`, served at `/style/data.css` by a route rather than mounted from
disk, with a stamp of its own contents in the query string and the same year-long
cache the static files get. It holds one rule per swatch the colour vocabulary can
produce, and one rule per length a bar can be, in half-percent steps.

What the markup carries is therefore a class — `bz-beige-heavily-yellowed`,
`w-830` — which is a fact about the thing rather than an instruction about how to
paint it.

Three alternatives were weighed and rejected:

- **A nonce on a per-page `<style>` block.** It works, and it is the usual answer.
  But it makes the policy per-request, puts a secret in the markup, and leaves the
  values in the page where they cannot be cached; a class naming a cacheable rule
  is strictly better when the set of values is known in advance.
- **Keeping `'unsafe-inline'` and writing down why**, which the roadmap offered as
  a legitimate outcome. Rejected because the work turned out to be a day rather
  than a project, and a stated compromise that nobody ever retires is how a
  temporary hole becomes a permanent one.
- **Setting the two values from JavaScript**, which the policy does allow —
  CSSOM assignment is not inline styling. Rejected because it makes a colour chart
  and a bar chart depend on scripting to be drawn at all, which
  [ADR-0013](0013-stay-server-rendered-polish-through-design.md) is against.

Half a percent is the granularity of a bar because a track is a few hundred pixels
wide, so half a percent is under two of them: invisible, against a thousand rules
to spare a difference nobody can see.

## Consequences

- The policy now says `'self'` in every directive, with no token anywhere. There
  is no exception left to explain to somebody installing this.
- `test_no_page_carries_a_style_attribute` asserts rather than skips: a style
  attribute added to a template fails CI instead of silently having no effect,
  which is the failure mode that made this worth holding to a test — the markup
  looks right and the page merely comes out wrong.
- One more stylesheet is fetched per page, about 10 KB, cached for a year against
  a stamp of its contents. The alternative was the same bytes in every page, every
  time, uncacheable.
- The mixing still happens once, in `entry.bezel_css`. The chart, the swatch beside
  a menu and the swatch on an item page read the same generated rules, and
  `colours.js` swaps a class rather than computing a colour, so the browser cannot
  disagree with the server about what "heavily yellowed beige" looks like.
- A new vocabulary entry — another shade, another level of yellowing — produces its
  rules automatically. A new *kind* of data-valued rule does not: it has to be
  added to `datacss.py`, and the temptation at that moment will be to reach for a
  style attribute instead. The test is what stops that being possible quietly.
