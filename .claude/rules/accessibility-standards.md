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

## Expected of new markup

- **Every control has a name.** A visible `<label>` where there is room for one;
  `aria-label` where the design gives a control only an icon or a tick. There are
  76 labels and 47 `aria-label`s in the templates — match that, do not thin it.
- **Every `<img>` has `alt`.** Describing the item where the image is content,
  `alt=""` where it is decoration. All 15 currently do.
- **Never suppress a focus outline.** The three that exist use `:focus-visible`
  with an `outline-offset`, so a keyboard user can see where they are and a mouse
  user is not shouted at. `outline: none` appears nowhere in the stylesheet and
  should stay that way.
- **A widget that behaves like a widget carries the semantics.** The autocomplete
  is a real combobox — `aria-expanded`, `aria-selected`, `aria-activedescendant`
  — rather than a `div` that happens to respond to arrow keys.
- **A table's header cells take `scope`.** `scope="col"` on a column head,
  `scope="row"` on a row's first cell.
- **Keyboard before mouse.** Anything reachable by clicking is reachable by
  tabbing, in an order that matches the page. A tick that submits on change (the
  `data-ticksend` forms) still has its button in the markup for a browser running
  no script, and that button is what a keyboard user without JavaScript presses.

## Known gaps

Recorded here rather than left to be rediscovered. See the roadmap item.

- **No skip link.** A keyboard user tabs the whole header on every page.
- **`scope` is on none of the 43 `<th>`** in the templates.
- **No `prefers-reduced-motion` block**, so animation is not reducible.

## The open question

Whether 0.1 commits to **WCAG 2.2 AA** as a target, or carries on as a set of
habits with a few of them tested. That is a decision with a cost attached — AA
asks for things this project has not looked at, reflow at 320px and a visible
focus indicator of a stated size among them — so it belongs in an ADR and not in
this file. Proposed as [ADR-0014](../../adr/0014-accessibility-is-a-tested-standard.md).
