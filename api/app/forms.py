"""Reading what somebody typed into what a column holds.

A form posts strings. The columns are dates, integers and enumerated text, and ""
is not a date -- which is what broke the create path when those columns stopped
being free text. These turn one into the other, and work out what changed, so that
the change log says "year: 1986 -> 1987" rather than that something was edited.
"""

import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import overload

from starlette.datastructures import FormData, UploadFile
from starlette.requests import Request

from . import entry
from .history import _short


class Posted:
    """A posted form, read as the text its fields were drawn to hold.

    A multipart body lets any field arrive as a file, whatever the page that drew
    the form intended, and Starlette says so: a value is ``UploadFile | str``. The
    handlers read a field and call ``.strip()`` on it, so an upload posted under a
    text field's name was an AttributeError and a 500. Read through this, a file
    where text was expected is the field left blank -- which every handler already
    has an answer for -- and the one place that does want the files asks for them
    by name with ``uploads``.
    """

    def __init__(self, data: FormData) -> None:
        self._data = data

    @overload
    def get(self, name: str) -> str | None: ...
    @overload
    def get(self, name: str, default: str) -> str: ...
    def get(self, name: str, default: str | None = None) -> str | None:
        value = self._data.get(name, default)
        return value if isinstance(value, str) else default

    def getlist(self, name: str) -> list[str]:
        return [v for v in self._data.getlist(name) if isinstance(v, str)]

    def uploads(self, name: str) -> list[UploadFile]:
        return [v for v in self._data.getlist(name) if not isinstance(v, str)]

    def __contains__(self, name: object) -> bool:
        return name in self._data

    def __getitem__(self, name: str) -> str:
        value = self._data[name]
        return value if isinstance(value, str) else ""


async def posted(request: Request) -> Posted:
    return Posted(await request.form())


def _parse_date(raw: str | None) -> date | None:
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


def _coerce(field: str, raw: str | None) -> str | int | bool | date | None:
    """A form string as the column's type: blank means not recorded."""
    if field in ("year", "topbench"):
        v = (raw or "").strip()
        return int(v) if _whole(v) else None
    if field in ("acquired_date", "disposed_at", "started_at", "target_date", "finished_at"):
        return _parse_date(raw)
    if field == "disposed":
        return (raw or "").strip() not in ("", "0", "false")
    return raw or ""


def _whole(v: str) -> bool:
    """A whole number written in the digits int() reads. str.isdigit() alone also
    says yes to superscripts, which int() then refuses -- a server error for a
    typed "²"."""
    return v.isascii() and v.isdigit()


# The boxes that take one shape of answer, each with what it says when given
# another: what is wrong and what would do instead, with an example. Blank is never
# the wrong shape; it means not recorded.
SHAPES: dict[str, tuple[str, str]] = {
    "year": ("Year", "Needs four digits, like 1988."),
    "topbench": ("TopBench score", "Needs a whole number, like 104."),
    "acquired_date": ("Acquired date", "Needs a date, like 14/03/1994."),
    "started_at": ("Started", "Needs a date, like 14/03/2026."),
    "target_date": ("Wanted by", "Needs a date, like 14/03/2026."),
    "finished_at": ("Finished", "Needs a date, like 14/03/2026."),
}

# What stopped a save: the field, its label and the message, as U.error_summary
# reads them.
Refusal = tuple[str, str, str]


def _fits(field: str, v: str) -> bool:
    if field == "year":
        return re.fullmatch(r"[0-9]{4}", v) is not None
    if field == "topbench":
        return _whole(v)
    return _parse_date(v) is not None


def refusals(form: Posted, fields: Iterable[str]) -> list[Refusal]:
    """Each of `fields` the form carries with an answer in the wrong shape.

    These used to be read as blank, and blank means not recorded -- so a mistyped
    date on an edit cleared the one already on file, and nobody was told."""
    out: list[Refusal] = []
    for f in fields:
        v = (form.get(f, "") or "").strip()
        if v and not _fits(f, v):
            label, message = SHAPES[f]
            out.append((f, label, message))
    return out


def _field_diffs(
    old: Mapping[str, object],
    new: Mapping[str, object],
    keys: Iterable[str],
    semantic_specs: bool = False,
) -> str:
    """A one-change-per-line diff of old vs new field values, for the change log.
    specs is broken down per spec key; re-canonicalising an unchanged specs
    string produces no diff.

    Nothing is skipped here any more. It used to leave out `project` and
    `project_note`, so that a plan could not reach an item's public history; a plan
    is a project of its own now, with a page and a privacy of its own, and there is
    nothing left on a computer or a part that has to be kept out of its own log."""
    lines: list[str] = []
    for k in keys:
        ov, nv = old.get(k) or "", new.get(k) or ""
        if semantic_specs and k == "specs":
            # The mapping is a whole row, so its values are typed as widely as the
            # columns are; specs is the text one, and is checked rather than assumed.
            o = dict(entry.parse_specs(ov if isinstance(ov, str) else ""))
            n = dict(entry.parse_specs(nv if isinstance(nv, str) else ""))
            for sk in [x for x in n if x not in o or o[x] != n[x]]:
                lines.append(f"{sk or 'spec'}: {_short(o.get(sk))} → {_short(n[sk])}")
            for sk in [x for x in o if x not in n]:
                lines.append(f"{sk or 'spec'}: {_short(o[sk])} → (removed)")
        elif ov != nv:
            lines.append(f"{k}: {_short(ov)} → {_short(nv)}")
    return "\n".join(lines)


# --- JSON API: computers ---------------------------------------------------
