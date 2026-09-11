# 0010 — Accessibility is a tested standard, not a set of habits

**Status:** Proposed
**Date:** 2026-09-11

## Context

The register is a public, server-rendered catalogue, deliberately so: ADR-0001's
stack note says no framework, because the item pages are meant to be crawlable
and to work as documents. Documents that work as documents are most of the way to
being accessible, and the project has done better than most without ever saying
it would.

What is already true. `api/tests/test_stylesheet.py` computes WCAG 2 relative
luminance and asserts 4.5:1 on primary buttons, danger controls and warning
banners, in both themes. It refuses a rule that fills with the accent without
saying what colour the text on it is, checks that the two dark-theme blocks
agree, and requires every control given its own size to be restated in the
coarse-pointer block so a phone does not zoom on tap. The markup carries 76
labels and 47 `aria-label`s, `lang="en"`, `alt` on all 15 images, focus outlines
that use `:focus-visible` and are suppressed nowhere, and a real combobox in the
autocomplete.

What is also true is that none of that was planned. Every one of those tests was
written after something shipped broken: white-on-accent at 2.4:1, reported by a
contributor (#21); a lightbox button that inherited a fixed white; controls added
after the coarse-pointer block and never listed in it. The pattern is exactly the
one `security-standards` was written to end — real care, applied unevenly,
with the standard living in whoever last looked.

And the gaps are the ones a habit does not catch, because no single change
surfaces them: there is no skip link, so a keyboard user tabs the header on every
page; `scope` is on none of the 43 `<th>`; there is no `prefers-reduced-motion`
block.

0.1's promise is that "nothing in it leaks what it should not or claims what is
not true". An interface that cannot be read at arm's length claims to be readable
and is not, and that is the same kind of untruth the release is being held for.

## Decision

**Proposed, and the reason this is an ADR rather than a rule: the target has a
cost and the cost is the decision.**

Adopt **WCAG 2.2 AA** as the standard the register is built to, and hold 0.1 to
the part of it that can be tested or read off the markup:

- the contrast ratios already asserted, extended to every colour pair the
  stylesheet states, in both themes;
- a name for every control, `alt` on every image, `scope` on every header cell,
  and a skip link — all checkable against the rendered templates in the suite, in
  the way `test_stylesheet.py` already checks the stylesheet;
- a visible focus indicator on everything focusable, which is already true and
  should become a test rather than a habit;
- `prefers-reduced-motion` honoured wherever the stylesheet animates;
- reflow at 320px without a horizontal scrollbar.

What this does **not** commit to is an audit with assistive technology, or a
conformance claim. Neither is something this project can honestly make: a claim
of AA conformance means the whole of AA on the whole of the site, verified, and
nobody here has run a screen reader over the build walk. The register says what
it tests and no more.

## Consequences

- The gaps above become work, and it is small work — a skip link, a `scope`
  attribute, a media query. The roadmap item sizes it at an afternoon.
- New markup acquires a review question it did not have, and new colour pairs
  acquire a test. This is the cost, and it is the same cost the contrast tests
  already impose on anyone touching the accent.
- A conformance claim stays off the README until somebody has actually tested
  with a screen reader. Saying "built to WCAG 2.2 AA" where "audited against" is
  meant is the untruth this record is trying to avoid making.
- Revisit if the target proves to be the wrong altitude — if AA's untestable
  clauses generate more argument than the tested ones prevent. The fallback is
  not "no standard": it is naming the specific success criteria the register
  holds to, which is what the list above really is.
