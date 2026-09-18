"""Reading what somebody typed into what a column holds.

A form posts strings. The columns are dates, integers and enumerated text, and ""
is not a date -- which is what broke the create path when those columns stopped
being free text. These turn one into the other, and work out what changed, so that
the change log says "year: 1986 -> 1987" rather than that something was edited.
"""

from datetime import datetime

from . import entry
from .history import _short


def _parse_date(raw):
    """A date from a form field. ISO is what <input type="date"> submits; the
    day-first form is accepted too because it is what gets typed by hand.
    Anything else, including blank, means not recorded."""
    v = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def _coerce(field, raw):
    """A form string as the column's type: blank means not recorded."""
    if field in ("year", "topbench"):
        v = (raw or "").strip()
        return int(v) if v.isdigit() else None
    if field in ("acquired_date", "disposed_at", "started_at", "target_date", "finished_at"):
        return _parse_date(raw)
    if field == "disposed":
        return (raw or "").strip() not in ("", "0", "false")
    return raw or ""


def _field_diffs(old, new, keys, semantic_specs=False):
    """A one-change-per-line diff of old vs new field values, for the change log.
    specs is broken down per spec key; re-canonicalising an unchanged specs
    string produces no diff.

    Nothing is skipped here any more. It used to leave out `project` and
    `project_note`, so that a plan could not reach an item's public history; a plan
    is a project of its own now, with a page and a privacy of its own, and there is
    nothing left on a computer or a part that has to be kept out of its own log."""
    lines = []
    for k in keys:
        ov, nv = old.get(k) or "", new.get(k) or ""
        if semantic_specs and k == "specs":
            o, n = dict(entry.parse_specs(ov)), dict(entry.parse_specs(nv))
            for sk in [x for x in n if x not in o or o[x] != n[x]]:
                lines.append(f"{sk or 'spec'}: {_short(o.get(sk))} → {_short(n[sk])}")
            for sk in [x for x in o if x not in n]:
                lines.append(f"{sk or 'spec'}: {_short(o[sk])} → (removed)")
        elif ov != nv:
            lines.append(f"{k}: {_short(ov)} → {_short(nv)}")
    return "\n".join(lines)


# --- JSON API: computers ---------------------------------------------------
