# Interface text

British English. What is written on the screen, as against what is written in
`MANUAL.md`.

## The rule

**A control says what it is. The explanation goes in a tooltip.**

The label is as short as it can be and still be unambiguous — a few words, not a
sentence. Everything else that was going to be printed under it goes in a
`title` attribute, which the browser shows on hover after its own short delay.

```html
<div class="srow" title="In the banner, the browser's tab, the foot of every
     page and the preview a shared link unfolds into.">
  <label for="site_name">Name</label>
  <input id="site_name" name="site_name">
</div>
```

`title` and not a scripted tooltip: the delay, the placement and the dismissal
are the browser's, it costs no JavaScript, and it does not have to be argued
past the content policy (ADR-0021).

Put it on the row rather than on the control, so hovering the label reaches it
too.

## Capitals

One convention, not two. 0.1 wrote a button in lower case and a field label
capitalised, on the reasoning that one asks for an action and the other names a
thing; v0.2 capitalises both, because that distinction was never one a reader had
to be told about in the shape of the letters, and a page mixing the two reads as a
page that has not decided.

- **A button, a menu item or a tab is capitalised.** `Save`, `Add note`, `Delete`,
  `Browse`, `Settings`, `Log out`, `+ Computer`.
- **A field label, a legend and a heading are capitalised.** `Manufacturer`,
  `Acquired date`, `Serial number`; `Identity`, `Tracking`, `Appearance`.
- **An acronym keeps its capitals wherever it falls** — `API docs`, `CPU family`,
  `RAM slots`. The rule is about case, not about spelling.

Sentence case throughout: only the first word and the proper nouns, never Title
Case On Every Word.

**The case is not the template's to state.** A control's words are written
capitalised at the source and passed through the `ui` filter —
`{{ 'Mark done' | ui }}` — which lower-cases the first word only when the case is
`lower`, and only where that word is written Like This, so `API docs` and `OK` keep
their capitals either way (`web.button_text`). The filter asks the **Button text**
setting on every use, so a save shows in the page the save returns; `cap` is the
default and is what the list above describes, and 0.1's voice is what an
installation gets by answering `lower`. So a new control
writes its words capitalised and leaves the choice to the filter: `{{ 'mark done' }}`
pins it to one answer and cannot be switched back.

## Why

A page of controls each carrying a paragraph is a page nobody reads — the
explanations crowd out the things being explained, and the person who already
knows what a setting is has to scroll past the reason for it every single time.
Moving them to hover keeps the answer one gesture away for whoever wants it and
out of the way of whoever does not.

## What this does not license

- **The label alone must be enough to act on.** A tooltip is not shown on a
  touchscreen, is not reached by the Tab key, and is not read out by every
  screen reader. Anything a person *needs* in order to answer correctly belongs
  in the label, or the control is wrong. The tooltip carries the *why*, the
  detail and the consequence — never the meaning.
- **The accessible name still comes from the `<label>`**, never from `title`.
  A control named only by a tooltip is an unnamed control
  (accessibility-standards).
- **`MANUAL.md` keeps the prose.** This rule moves explanation off the screen,
  not out of the project: the manual is where somebody reads the whole story,
  and it stays as full as it has always been. A tooltip is a reminder; the
  manual is the specification (manual-first).
- **It is not a licence to be curt.** Terse is not the same as cryptic, and
  three clear words beat one clever one.

## Applying it

New work follows this from the start. Existing pages are brought over when they
are next touched for another reason, rather than in one sweep — the settings
page is the first, and is the shape to copy.
