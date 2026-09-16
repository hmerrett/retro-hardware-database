# Accessibility standards

Server-rendered HTML, no framework, two themes. British English.

Most of what follows was already being done before it was written down — which is
the problem this file fixes. The contrast tests in `api/tests/test_stylesheet.py`
exist because white-on-accent shipped at 2.4:1 and a contributor reported it
(#21). Care that lives in whoever last thought about it is care that arrives as a
bug report.

## Enforced by the suite

These are tests, not intentions. `api/tests/test_stylesheet.py` reads the
stylesheet's own declarations, because no rendered page can be asked what
contrast a button has against its own fill.

- **4.5:1 on text**, computed with WCAG 2 relative luminance and asserted **in
  both themes**: primary buttons against their fill, danger controls against the
  page, warning banners. Parametrise a new pair the same way rather than eyeing
  it in a browser — the dark theme's accent is a pale blue and reads very
  differently from the light one's.
- **A rule that fills with `--accent` states the text colour on it.** Leaving the
  foreground to be inherited is what broke the lightbox: it picked up a fixed
  white that the dark theme's paler accent could not carry. The fill and the text
  on it are one decision and belong in one rule.
- **The two dark-theme blocks agree.** Dark values are stated twice — once for
  `prefers-color-scheme`, once for `[data-theme="dark"]` — and a reader can land
  on either.
- **Every control that is given its own size is listed in the
  `@media (pointer: coarse)` block.** iOS zooms the page when it focuses a
  control whose text is under 16px and does not zoom back out. A rule naming a
  control through a class outranks the bare `input`, so it has to be restated
  there.

`api/tests/test_keyboard_and_motion.py` holds the three that no rendered page
surfaces on its own, and reads the markup and the stylesheet the same way.

- **The first thing the Tab key reaches is the skip link**, on every page, with
  `<main id="main" tabindex="-1">` to land on. The test opens four pages and an
  item page and asserts what the first focusable element is, because a skip link
  that is second is a skip link nobody uses.
- **Every `<th>` carries `scope`.** All 43 do. The item pages read down the side
  and the lists across the top, so neither direction can be assumed.
- **No motion starts without reading the preference.** The stylesheet answers
  `prefers-reduced-motion` for anything that animates later, and the one scroll
  that asks for motion in JavaScript reads `matchMedia` itself — an explicit
  `behavior` passed to `scrollTo` outranks `scroll-behavior`, so the media query
  alone would leave it moving.

`api/tests/test_reflow.py` holds the promise the manual makes a narrow screen
("On a narrow screen"), which no rendered page surfaces either: a list is only
too wide on the phone it is being read on, and the person who added the column
was looking at a desktop.

- **A table with more columns than a phone holds either stacks or scrolls inside
  its own box.** More than three is the line: 320px less the gutters leaves 74px
  a column, which is five characters and a padding either side. Stacking is the
  answer for a list of things (`.projtable`, `.ordertable`, `.filetable` — cells
  become blocks under a `max-width` block, each carrying the heading it has lost
  in `data-label`); `.hscroll` is the answer where the row has to stay a row, as
  the drives table does. The test walks every list page, so a fourth table gets
  the question asked of it.
- **A stacked cell says what it is.** Stacked, a row loses its headings, and a
  bare date under a filename is a date for no stated reason.
- **A control asks for a width rather than demanding one.** `min-width` on a
  control is a floor the cell around it cannot go below: 200px of it on the
  re-file box held the files list open. `width` is a size a table may compress.
- **Anything unbreakable gets somewhere to break.** `overflow-wrap: break-word`
  on a cell breaks a word that already has its column but leaves the column's
  minimum at the whole word, so one long filename set the width of the table.
  A filename, a URL, a disk-image path: `anywhere`, because nobody reads one as
  a word.

## Expected of new markup

- **Every control has a name**, and the suite reads it off the rendered pages
  rather than trusting a count. A visible `<label>` where there is room for one;
  `aria-label` where the design gives a control only an icon, a tick or a column
  heading. A column heading is not a name: nothing in HTML carries it from the
  `<th>` to the box underneath, which is why the drives grid names each box by
  its row and its column ("drive 2, form factor").
- **Every `<img>` has `alt`.** Describing the item where the image is content,
  `alt=""` where it is decoration — which is an answer, and tells a screen reader
  to pass over a swatch. A missing `alt` is not: the filename is read out instead.
  Also checked against the rendered pages.
- **Never suppress a focus outline.** The three that exist use `:focus-visible`
  with an `outline-offset`, so a keyboard user can see where they are and a mouse
  user is not shouted at. `outline: none` appears nowhere in the stylesheet and
  should stay that way.
- **A widget that behaves like a widget carries the semantics.** The autocomplete
  is a real combobox — `aria-expanded`, `aria-selected`, `aria-activedescendant`
  — rather than a `div` that happens to respond to arrow keys.
- **A table's header cells take `scope`.** `scope="col"` on a column head,
  `scope="row"` on a row's first cell. The suite checks every template, so a new
  table without it fails rather than waiting to be noticed.
- **Keyboard before mouse.** Anything reachable by clicking is reachable by
  tabbing, in an order that matches the page. A tick that submits on change (the
  `data-ticksend` forms) still has its button in the markup for a browser running
  no script, and that button is what a keyboard user without JavaScript presses.

## The target

**WCAG 2.2 AA**, decided in [ADR-0014](../../adr/0014-accessibility-is-a-tested-standard.md)
and accepted with no exception taken. What that means here is narrower than it
sounds, and deliberately so: the register holds to the part of AA that can be
tested or read off the markup, and the tests above are that part. It does not
claim conformance, and it will not until somebody has run a screen reader over
the build walk — "built to" is not "audited against", and writing the second
where the first is meant is exactly the kind of untruth 0.1 is being held for.

So the rule for new work is the one the tests already state: a new colour pair is
parametrised into the contrast tests, a new control carries a name, a new table
says which way it runs and what it does on a phone. What is not tested is not
claimed.
