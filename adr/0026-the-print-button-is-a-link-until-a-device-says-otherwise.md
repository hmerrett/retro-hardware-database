# 0026 — The print button is a link until a device says otherwise

**Status:** Accepted
**Date:** 2026-09-19

## Context

ADR-0024 made a label a printer can take and ADR-0025 got one to a printer in
another room. Neither of them is reachable from the register: the button on an
item page still does the one thing it has always done, which is hand over a PDF.

The question this answers is what that button should do now that there is more
than one answer, and where the answer is kept.

It is not one answer. The three destinations are not alternatives a project picks
between — they are each right somewhere. A PDF is right for a sheet of labels and
for AirPrint from a phone. A queue is right for the Dymo on the Pi in the
workshop. Bluetooth is right for the Niimbot in your hand, standing at a shelf.
All three will be used by the same person on the same afternoon.

## Decision

**The markup is a link to a PDF, and stays one.** The destination is something a
script does *instead*, on a button that already works without it. A browser
running no JavaScript, or one that has never been told otherwise, gets the file it
has always got. Nothing in the markup promises a destination it might not be able
to reach.

**The site sets a default; a device overrules it.** The default is a setting in
the database, on the settings page, and it is what a browser that has never chosen
gets. The device's own answer is in `localStorage` and never leaves the browser.
This is the line ADR-0023 drew when it was written, named this exact case, and
reserved the shape for it — nothing there had to be revisited.

The device's answer is set on the settings page rather than somewhere of its own,
because that is where somebody goes to change where labels print, and a preference
that can only be found by knowing it exists is a preference nobody finds. It sits
outside the form, so pressing *save* does not look as though it wrote it to the
server, which it did not.

**The list of destinations is worked out, not written down.** The print agents
come from the environment (ADR-0025) and the Niimbot stocks from the label module
(ADR-0024). A list in a template or a static tuple in the settings definitions
would be a third copy, and the third copy is the one that goes stale — so a
`Definition` may say its choices are live, and one function answers for both the
menu that chooses and the button that acts. The two cannot come to disagree about
what exists.

**Where a browser cannot do it, it says so.** Safari has no Web Bluetooth and
Apple has said it will not add it, which makes the Bluetooth destination
unreachable on an iPhone. The button answers by naming Bluefy — the browser that
does have it — rather than by reporting that something is unsupported. An
unreachable destination is a thing a person can act on if they are told what to do
about it and a dead end if they are not.

## Consequences

- `label_destination` and `label_bluetooth_media` are settings; `rhdb.labelDestination`
  is the device's, in `localStorage`. Every read and write of that store is
  wrapped, because it throws in a private window and in a browser told to keep no
  site data, and the register works in both — the fallback is the site's answer.
- A device remembering a printer that has since been taken out of the settings
  falls back to the site's answer rather than failing at the moment somebody
  presses print.
- The default is the PDF, so an installation that upgrades and changes nothing
  notices nothing.
- What this does **not** decide is how the bytes reach a Niimbot. The driver is a
  module loaded when that destination is used and is a decision of its own: the
  reference implementation of the protocol is CommonJS and would need a bundler,
  which this project does not have and has been careful not to need (CLAUDE.md,
  ADR-0013). Until that is settled the destination is offered and reports honestly
  that it cannot connect, which is worse than working and better than a menu that
  pretends the printer is not supported.
