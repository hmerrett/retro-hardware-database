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

Two conventions, and they were already in the code before they were written down
here — this says which is which so that the next control does not have to guess.

- **A button, a menu item or a tab is lower case.** `save`, `add note`, `delete`,
  `browse`, `settings`, `log out`, `+ computer`. It is the register's voice:
  quiet, and not shouting an instruction at you.
- **A field label, a legend and a heading are capitalised.** `Manufacturer`,
  `Acquired date`, `Serial number`; `Identity`, `Tracking`, `Appearance`. These
  name a thing rather than ask for an action, and they read as the column of a
  form.
- **An acronym keeps its capitals wherever it falls** — `API docs`, `CPU family`,
  `RAM slots`. The rule is about case, not about spelling.

Sentence case throughout either way: only the first word and the proper nouns,
never Title Case On Every Word.

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
