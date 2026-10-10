# 0038 — A label is pictured from the page before it is saved

**Status:** Accepted
**Date:** 2026-10-10

## Context

ADR-0037 made each label a set of settings: a code, a stock, an ordered list of
details, a face. The stock decides the label's shape. Whether a given combination
comes out well is something only looking can answer, and the only place to look
was an item's Label panel. That meant saving first, and the item might not carry
the detail just ticked. On 2026-10-10 the owner asked for a picture of each label
on Settings → Labels, redrawn as the settings change.

The owner settled the open questions the same day:

- The picture is of an example, with a menu to say whether the example is a
  machine, a part, a project or a location.
- It is drawn on the stock the label goes to, as the Label panel's picture is.
- It stands beside the label's settings and stays in view on a wide screen.

## Decision

**The server draws the picture from the page's form, and keeps none of it.** The
page's script puts the label's fields in the query of a picture's address,
`/settings/labels/preview.png`. The route reads them with the cleaning Save applies
(`settings.unsaved`) and lays them over what is saved (`settings.value(key, over)`).
It then draws the example with `labels.render_png`, the code that draws every
label. Nothing is written.

- **It is not drawn in the browser.** A second layout in JavaScript would be a
  likeness of the label that could drift away from it. ADR-0024's point is that a
  label is laid out once.
- **It is a GET with the form in the address, not a POST.** The content policy
  takes pictures from this site alone (ADR-0021), so a picture fetched by script
  and shown from a `blob:` address would be refused. The picture's own address has
  to be the request, and a label's fields are a page's worth of short values.
- **It is never cached** (`no-store`). The address with nothing sent is the label
  as saved, and that changes whenever Save is pressed.

**The picture is of an example, not an item.** Each sort of thing has one example
carrying every detail that sort can have, so every tick has something to print,
and a register with nothing in it still has a picture. The example's tag,
`RH-DEMO`, has the shape of a tag but can never be issued: new tags come from an
alphabet with no O, and old ones are digits. So the code in the picture opens
nothing.

**Where the label goes decides the stock.** The same map serves the Label panel
and this picture (`printing.stocks`), so the two cannot draw one label on two
stocks. The map is read from the page's fields. It does not read the browser's
own choice of printer, which says where one browser sends a label rather than what
the label is.

## Consequences

- With no script the picture is the label as saved, for the example each label
  starts on, and the menu is not offered.
- A value the page could not have sent is drawn as saved, just as Save would
  ignore it.
- The picture is behind the login with the rest of `/settings`.
- `settings.value` and `settings.order` take answers not yet saved, and
  `labels.setup` and `labels.render_png` take the label's settings from the caller.
