# 0005 — The photo tuneup is conservative, and takes exactly one step back

**Status:** Accepted
**Date:** 2026-09-06

## Context

Photographs go into the register straight off a phone, in whatever light the bench
had. A phone's own auto-enhance — one button, levels and colour fixed — is the
obvious thing to want, and Pillow, which is already a pinned dependency, can do
the global part of it: white point, black and white points, a midtone gamma, a
little saturation. The local, region-aware part (shadow and highlight recovery,
subject detection) would need numpy or OpenCV, and for an object on a bench under
one light it is not where the improvement is. So the capability was never in
question. Two things about *this* catalogue were.

**A catalogue photograph is evidence.** The machines here are frequently yellowed
by decades of sunlight, and how yellow is a fact about the item — the thing a
retrobrighting project is about. An automatic white balance assumes the brightest
thing in frame ought to be neutral; on a photograph filled with a sun-yellowed
beige case, the brightest thing is legitimately yellow, and a confident correction
quietly erases the evidence. The same argument applies to exposure: a pale machine
on a pale bench has nothing dark in it, and an unrestrained stretch reads that as a
fault. Trialling it, a clean, well-exposed frame averaging 192 came out at 127 —
the fix made a good photograph look underexposed.

**The edit is destructive.** `_edit_image` keeps no originals, which is defensible
for the two edits that had it: a rotate is its own inverse, and a crop is a
deliberate act on a region you chose. A tone change is neither. It is one press,
it changes every pixel, and whether you like it is a judgement you may make
differently a minute later.

## Decision

**The fix is damped throughout, and aims at the photograph it was given.** The
white balance moves each channel only 60% of the way to a common white point, so a
warm room stays warm and real yellowing survives. The levels stretch goes 75% of
the way to the ends. The midtone gamma then restores the *original* average
brightness rather than a fixed middle grey, clamped into a band (96–168) that only
catches a frame which was genuinely badly exposed. A well-exposed photograph keeps
its exposure and gains only contrast; that is the whole intent.

**One press, and one step back.** The first tuneup copies the photograph to
`.orig/<rel>` — under a dotted directory, so `serve_image`, which refuses dotted
segments, cannot hand out an unwatermarked copy. While that copy exists the button
reads "revert" instead of "tuneup", so pressing twice cannot stack the fix or cost
another JPEG generation. Any *other* edit — rotate, crop, delete, promote to
primary — drops the kept copy, because after one of those it is no longer the truth
about the photograph and reverting would silently undo that other edit too.

## Consequences

- On real photographs from the collection, contrast rises 10–19% and saturation
  20–40%, while average brightness moves by under 2 points. Colour is where the
  life comes from; the levels stretch is nearly a no-op on a real photograph,
  because one already spans so much of the range that the honest scale works out
  at about 1.02. It earns its place on the genuinely flat frame — a hazy or
  underlit shot — and is capped at ×4 so a photograph of one flat surface does not
  have its sensor noise multiplied sixteenfold.
- Still a tidy-up rather than a transformation: a photograph that needs real work
  needs a real editor.
- Storage grows by one extra copy per photograph *currently* tuned — a slot, not a
  history. It is reclaimed by reverting, by any other edit, or by deleting the
  photo.
- "Revert" is available for a while and then quietly is not. The button's absence
  is the only thing that says so; that is the cost of not keeping a full history.
- Revisit if a full undo stack is ever wanted, or if the strength proves wrong
  again — the constants are named at the top of `api/app/enhance.py` and are the
  only thing that would need to move. `_STRETCH` in particular is now blended
  against doing nothing rather than by moving the ends of the range part of the
  way: the latter reads naturally and is inverted, because pushing the top end
  towards 255 widens the range being mapped onto the full scale and so stretches
  *less*. A larger setting meant a weaker fix, and no test caught it, because they
  all asked only that contrast went up at all. One now asks that the knob turns
  the way it is labelled.
