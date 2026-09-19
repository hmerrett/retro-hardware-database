# 0024 — A label is laid out once and drawn twice

**Status:** Accepted
**Date:** 2026-09-19

## Context

A label has been a PDF since there were labels. That was right while the only
printer was a DYMO on the end of a Mac: `lp` takes a PDF, the print dialogue takes
a PDF, and a phone will AirPrint one.

It stops being right at the first printer that is not sent pages. A small thermal
label printer — a Niimbot over Bluetooth, and most of the handheld class — is sent
a bitmap the width of its print head and nothing else. There is no page, no
scaling, no interpreter: a dot is burned or it is not.

Two things follow that a PDF cannot give us.

**The dots have to be ours.** Handing a rasteriser a page and asking for 400
pixels of it gives back grey where the drawing fell between dots, and a thermal
head has no grey — it dithers, and a dithered QR code is a picture of a QR code.
The label has to be drawn at the size it will be printed, in the printer's own
dots, by something that knows they are dots.

**The stock is not a boolean.** The label geometry was `small: bool`, meaning
51×19 mm or 6×4 in, because those were the two tapes in the building. A Niimbot
B1 prints 50×30 mm on a 48 mm head; a D11 prints 12×22 mm on a 12 mm one. "Small"
cannot say which, and the answer is not a size the caller passes either, because a
size alone does not say how many dots it is or how much of the tape the printer
can actually reach.

## Decision

**The layout is written once, against a surface, and there are two surfaces.**
Everything that decides where a line goes — the wrapping, the type size that fits,
the clip with an ellipsis, the word up the end, the squeeze that drops the last
spec — is the label's own logic and has nothing to do with PDFs. It talks to a
`Surface`: measure this string, draw it here, put this image there. `PdfSurface`
is reportlab, as before. `RasterSurface` is Pillow, drawing in device pixels.

The alternative was to keep one renderer and rasterise its PDF. It was rejected
twice over: it needs a PDF rasteriser in the runtime image, which is a new
dependency and a large one for this; and it puts a scaler between the layout and
the dots, which is the exact thing that ruins the code.

**The surface measures in points, and the raster surface converts.** The layout
reasons in points at every size it picks, so a raster label is not a second set of
numbers to keep in step with the first — it is the same numbers, on a surface
where a point is `dpi/72` pixels.

**Media is a named stock, not a size.** `MEDIA` holds each one: what it measures,
how far in from the ends of the tape the body keeps, and what it is for.
`dymo-11355` and `full-6x4` are the two that existed, and `small=True/False`
still resolves to them, so every caller and every URL already printed against
keeps working.

**The QR code is drawn at a whole number of dots to the module.** The raster
surface is given the code as a module grid rather than as a picture to fit into a
box: it takes the largest whole number of pixels per module that fits the space,
draws that, and centres the remainder. A code fitted to the space instead comes
out with modules a pixel wider than their neighbours, which at 8 dots/mm is a
quarter of a module.

## Consequences

- `GET /{computers,parts,projects}/{id}/label.png?media=…&dpi=…`, beside the
  existing `label.pdf`, behind the same login. 1-bit PNG, the printer's dots.
- The PDF is unchanged. Every label's drawing operators were compared against the
  same label rendered before the change and are identical to the byte, which is
  the part of a PDF that reaches paper — the files themselves differ only in the
  document id, which is random per run. What the suite holds from here is the
  thing worth holding: that both surfaces say the same words in the same order
  for the same label. Where the lines break is not asserted across surfaces,
  because reportlab and Pillow measure the same font file a fraction of a point
  apart, and a clip can land a character either side of that.
- A stock the app does not know is a 404 and not a guess. A printer whose head is
  narrower than its tape — every Niimbot — is described by its media entry, so the
  printable width is the app's fact rather than each caller's.
- The small label sized its QR code by the label's height alone, which was right
  while every small label was a 51×19 mm tape. On a 50×30 mm one that took more
  than half the width and clipped "Seagate ST-225" to "Seaga…" on a label two
  thirds empty, so the code is now capped at a share of the width and centred in
  the height. The tape is unaffected: on it the height still binds.
- Pillow is already a dependency, for photographs. Nothing new is added.
- What this does *not* decide is where the bitmap goes. Sending it to a Bluetooth
  printer from the browser, or to a print agent on a Pi, are separate questions,
  and the device setting that chooses between them is ADR-0023's to answer. This
  one only says the bitmap exists and is correct.
