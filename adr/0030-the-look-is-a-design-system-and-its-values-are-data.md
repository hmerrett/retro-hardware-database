# 0030 — The look is a design system, and its values are data

**Status:** Accepted
**Date:** 2026-09-22

## Context

v0.1's stylesheet was written the way a stylesheet is written while there is one
installation: a colour where a colour was wanted. Measured at the end of it,
`app.css` held 16 colour tokens and about thirty literals beside them, twelve
distinct font sizes, twelve radii and seven width breakpoints. None of that was
wrong for a site with one owner. It is wrong for this one: the register is a
product other people run (ADR-0011), and v0.2's whole subject is that an
installation wears its own name, its own logo and its own look.

A look that is somebody else's has to be a *seam*, and a seam has to be narrow
enough to describe. Three things made the v0.1 stylesheet unable to be one.

**There was nowhere a colour lived.** A colour was in whichever rule needed it,
so "what colour is a panel's band" had as many answers as there were rules, and
the contrast tests could only check the pairs somebody had thought to list.

**Every value was stated twice or not at all.** The dark theme is written once for
`prefers-color-scheme` and once for `[data-theme="dark"]`, because a reader can
arrive by either; 0.1 kept the two in step by hand and had a test to catch the day
they drifted, which is a test that exists because a duplicate does.

**Nothing said what a look was allowed to change.** Left undecided, the first
preset to want a narrower column would have got one, and the second would have
been a second stylesheet with its own layout, its own breakpoints and its own
bugs — which is how a theme becomes a fork.

## Decision

**The look is a design system, specified before it is built, and its values are
data in the repository.**

**One seam, and it is the tokens.** Colour, type, spacing, radii, borders,
elevation and motion are token values on the document; the components paint with
the tokens and with nothing else. No colour and no off-scale length is written
outside `tokens.css`, and `test_stylesheet_lint.py` fails one that is — the rule
is enforced rather than remembered, for the reason ADR-0014 gives about care that
lives in whoever last thought about it.

**The values are data, and the stylesheets are generated from them.**
`api/app/design/palettes.json` holds every colour of every preset in both modes,
`scales.json` the scales they share, and `tools/build_presets.py` writes
`tokens.css` and `presets/<id>.css` from them. The suite runs it with `--check`,
so a file on disk that has drifted from the data fails. The contrast tests read
the same two files, which is the point of the arrangement: a colour has one home,
and the test that vouches for it is reading what the browser is served rather than
a second copy that happens to agree today. Both dark blocks are written from one
dictionary and can no longer drift apart.

**A preset is token values and nothing else.** It may state colours, radii, a
border width, a shadow, the three type families and its own ornament. It may not
name a component and it may not move anything: every page keeps its layout, its
columns and its breakpoints whichever preset is chosen, so picking one is a change
of dress and never a change of furniture. `test_presets.py` reads the generated
files and fails a preset that names a component.

**The default preset is no attribute at all.** Its values are the ones
`tokens.css` states on `:root`, so the common case links no second stylesheet and
carries no `data-preset`, and an unknown name resolves to it rather than to a
stylesheet that is not there (`presets.known`).

**The components are macros.** `_ui.html` is one macro to a card of the design
system and `_icons.html` one inline set, so a component's markup is written once
and a page cannot quietly grow a second kind of button. The system's drawn
specification is kept outside the repository — it is a design document, not code —
and what is authoritative *here* is the data, the macros and the tests that hold
them.

## Consequences

- Adding a colour is an edit to `palettes.json`, a run of `build_presets.py`, and
  a row in the contrast parameters. It is not a rule in a stylesheet, and the
  suite says so.
- A new preset is a block of JSON and a name. It ships with no stylesheet of its
  own to review, because its stylesheet is generated.
- The contrast matrix is a sweep rather than a list: every pair the data states,
  in every preset and both modes. That is what makes a preset safe to add — it
  cannot ship a pair nobody computed.
- A look that genuinely needs to move something cannot be a preset, and the ADR is
  where that argument has to be had. This is deliberate: the cost of the rule is
  paid by the one look that wants a narrower column, and the cost of not having it
  is paid by every page of every install.
- The layout is tested once. The reflow, keyboard and stylesheet tests do not run
  per preset, because a preset cannot reach what they check.
- `app.css` keeps only what has not yet been brought over, and shrinks as each
  page moves onto the system's own classes. It is not a second vocabulary; it is
  the remainder of the first one.
- What this does *not* decide is what an installation may choose. Which look, which
  typefaces, which navigation and which accent are settings, and a setting is
  ADR-0023's shape: the environment pins, the owner chooses, the device answers
  only for the theme.
