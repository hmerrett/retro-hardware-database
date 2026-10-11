# 0037 — Each label is set up for its job, and the stock decides its shape

**Status:** Accepted — amended by [ADR-0039](0039-every-label-follows-its-list-and-makes-room-before-it-leaves-anything-off.md)
**Date:** 2026-10-10

## Context

There have always been two labels, a small one and a full one, and almost nothing
about either could be changed. One setting chose the codes for both and one the
face. Only the small label had a destination, and what each printed was fixed in
`labels.py`. An installation uses its two labels for two jobs, such as a sticker
for the parts drawers and a card for the shelf, on whatever printers it has, and
issue #154 asked for each to be set up for its own.

The owner settled the open questions on 2026-10-10. The register still has two
labels, and the owner names them. What a label says is one ordered list of
details, which computers, parts and projects fill as far as each can. A location's
label keeps its own shape. A label may carry no code. *This browser* overrules
where either label goes.

## Decision

**A label is a set of settings, and the stock is the printer's.** Each label has a
name, a code, a destination, the stock its PDF is drawn on, an ordered list of
details, a tick for the word up the end, and a face. Its Stock applies to the PDF
alone. Over Bluetooth a label prints on the roll the Bluetooth setting names, and
on a queue on the stock the agent has loaded. One label goes to different printers
from different devices (ADR-0026), and making the stock the label's would lay out
the phone's Niimbot label for the workshop's DYMO tape.

**The stock decides the shape.** A stock with room for the full layout, the 6×4
inch sheet, is drawn as a full label. Anything smaller is drawn as a small one,
whichever of the two labels it is. This generalises the rule the print queue
already used for a machine's label, and it means a label is never drawn in a
layout its stock cannot hold. It amends ADR-0024: the layout is still written once
and drawn twice, but which layout is now chosen by the stock rather than by the
button.

**The first detail is the largest.** The order in the list decides what a label
is headed by. The rest follow it, and where there is no room the last ones go.

**Both buttons answer to a destination, and so does a print job.** This amends
ADR-0026: each label has the site's default and a device's own answer, kept under
its own `localStorage` key. The existing key keeps meaning the first label. A
queued job records which label it is for, and a job that does not say is the
first label's.

## Consequences

- The defaults are today's labels: QR, Tag, Name and Specifications, the word up
  the end, the label face, a PDF on 51×19 mm tape and on a 6×4 sheet. The one
  change an installation can notice is on a 6×4 print agent: a part, a project or
  a location sent there gets the full layout, where before it got the small one
  enlarged.
- Migration 0048 copies the two shared settings to both labels and the small
  label's destination to the first, then removes the old keys. Its downgrade
  copies them back. It also adds `print_job.label`.
- `POST /api/print/jobs` takes an optional `label`, which is a change to the
  published API (ADR-0010).
- The label names are free text, so the manual calls them the first and the second
  label wherever the name could be anything.
