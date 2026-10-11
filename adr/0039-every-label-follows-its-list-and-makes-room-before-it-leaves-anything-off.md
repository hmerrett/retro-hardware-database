# 0039 — Every label follows its list, and makes room before it leaves anything off

**Status:** Accepted
**Date:** 2026-10-10
**Amends:** [ADR-0037](0037-each-label-is-set-up-for-its-job-and-the-stock-decides-its-shape.md)

## Context

ADR-0037 gave each label an ordered list of details and kept one exception: a
location's label kept its own shape. That shape was the name largest, the path above
it and the tag under it, whatever the list said. On 2026-10-10 the owner set up a
label for locations, unticked every detail, and expected the code alone. The picture
on the settings page didn't change, because nothing on that list could change it.

The same day the owner set Code 128 on an 89×36 mm label with five details ticked.
Only three were printed. A small label's type grows with the label's height, and the
layout dropped whatever did not fit at that size rather than give any of the growth
back. So ticking or moving the fourth and fifth details changed nothing, and the
page did not say why.

The owner settled both on 2026-10-10:

- A location follows the list like everything else.
- A crowded label shrinks its type to fit first.
- The page says what is still left off.

## Decision

**Every kind reads the list.** A location's Tag is its tag, its Name is its name,
and its Where it's kept is the path of the locations it is inside. On a full label
its Specifications are its kind and notes, and on a small label there are none, as
with a machine. It has no make and model and no serial number. The first detail
ticked is printed largest. The word up the end appears only if it is ticked.
Nothing ticked leaves a label with its code alone. Location labels change for an
installation that does nothing: with the starting ticks a location prints its tag
largest, then its name, and its path only once Where it's kept is ticked. The owner
accepted that.

**A small label gives its growth back before it drops a line.** The layout tries
the label at the size it grows to. If any detail's lines do not all fit, it tries
again at a smaller scale, step by step, down to the 51×19 mm tape's own sizes and no
further. Past that the last ones go, as before. A label with room to spare is
unchanged. So is the tape, which has no growth to give back, and so is the full
layout, whose sizes are fixed. A corpus of item labels on every stock with every code
was byte-identical to before, except the crowded barcode labels this was for.

**The renderers say what they printed.** Each line of a label carries the detail it
came from. Both layouts report, for each line, whether it was printed whole, in part
(a line wrapped over two with room for one), or not at all. `labels.fit` turns that
into the details left off and the details only partly printed. The settings page
asks for it beside the picture, at `/settings/labels/preview.json`, read the same
way as the picture and kept nowhere, and puts it in a line under the picture.

## Consequences

- The old location shape is gone. That includes its line of small type over the
  head, and the path that kept to one line by losing its far end first. A path is a
  line like any other now, and wraps.
- `locations.label_row` names the path `kept`, as an item's row does.
- A crowded label's report can be wrong only if the renderer is: the test for it
  draws every detail and checks the report against what is actually on the label.
