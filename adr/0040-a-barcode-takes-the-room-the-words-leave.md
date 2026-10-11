# 0040 — A barcode takes the room the words leave

**Status:** Accepted
**Date:** 2026-10-11

## Context

A small label's barcode had a fixed band: 36% of the label's height, at the foot,
whatever was written above it. On 11 October 2026 the owner set a location label on
89×36 mm stock to Code 128 with nothing ticked. The picture on the settings page
showed a band of bars across the bottom third and white above it. The owner's words
were "the barcode should take up as much space as it can. with no text, it should be
the entire height of the label."

The 6×4 full label put a barcode alone where the QR code would be: a box 2.1 inches
wide at the right-hand end, with bars 0.9 inches tall.

The owner was asked which gives way when there are words. The answer was the bars:
the words keep the size they print at, and the bars take what is left. The owner was
also asked about the 6×4, and chose to run a barcode alone across the bottom, under
the words, as on the small labels. That choice means a crowded label on that sheet
loses its last lines to the bars, which the owner accepted.

## Decision

**The words are laid out first, and the bars rise to meet them.** The old band is
now the least the bars have: the words are fitted above it, shrinking on a crowded
small label as before. The bars then grow from the foot of the label to just under
the last line: the line's tails and a point on a small label, eight points under its
baseline on a full one. With nothing written they run the label's whole height,
inside its margins. Anything else standing above bars that run across keeps its own
height, and the bars stop under it:

- the QR code, when both codes are carried and the bars run under it;
- the word up the end.

So the QR code is never made smaller for the bars.

**On a 6×4 sheet a barcode alone runs across the foot of the label.** It is as wide
as the sheet allows inside its margin, which at 300 dpi is twelve dots to a module
where the box gave four. Its least height is the 0.9 inches it had in the box, and
the words get the whole width above it. With both codes the bars stay under the
words, beside the QR code, and now stand on the margin rather than a sixth of an
inch above it. Their least height grew by that sixth, so the words stop where they
always did.

## Consequences

- Every label with no barcode is drawn as before. A corpus of item labels on every
  stock with every code was byte-identical to main for QR codes and for none.
- Barcode labels with room to spare change, and that is the point of this decision.
  A crowded small label keeps its type and its lines. Its bars rise only by the
  fraction of a line its words left over.
- A 6×4 label with a barcode alone loses about five listed lines to the bars. A
  machine whose build filled the sheet loses its last lines. The settings page's
  line under the picture names them (ADR-0039).
- The word up the end on a 6×4 with a barcode alone stands in the height above the
  bars rather than in the middle of the sheet.
