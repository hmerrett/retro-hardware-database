"""What the register keeps because somebody prefers it, rather than because it is
true of the collection (ADR-0023).

Three places a preference can come from, and all three are real. The environment
is the deployment speaking and wins where it speaks at all. The `setting` table is
the owner speaking, and is what the page writes. The browser is the device
speaking, and never reaches this module: a device preference is in `localStorage`
and stays there, which is the whole point of it.

The definitions below are the page. Adding a preference is a row in this tuple and
a control in the template that reads it -- deliberately not a column, because a
migration per preference would be a tax on exactly the thing a settings page is
supposed to make cheap, and because every one of them has a default that makes an
empty table a working site (ADR-0002).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Setting

if TYPE_CHECKING:
    # Held back to the type checker, the way photos.py holds the same import back
    # and for the same reason: forms reaches history, history reaches web, and web
    # reads these settings on every page it renders. Imported at runtime that is a
    # closed circle, and the module that lost the race would import a half-built
    # one.
    from .forms import Posted

SWITCH, TEXT, CHOICE = "switch", "text", "choice"

# The fieldsets, in the order they are shown. Named here so a definition names one
# rather than repeating the words.
APPEARANCE = "Appearance"
LABELS = "Labels"
SERVER = "Server options"

# Where a small label goes when the print button is pressed. The two that need no
# hardware named anywhere; a configured print agent adds one of its own (see
# `choices_for`), because which printers exist is a fact about this installation
# rather than about the software.
PDF, BLUETOOTH, AGENT = "pdf", "bluetooth", "agent:"

DEFAULT_SITE_NAME = "Retro Hardware Database"

# What a switch reads as off, matching RHDB_WATERMARK's own reading of itself from
# before there was a page to set it on -- the variable is public and somebody has
# written `off` in a compose file by now.
OFF = ("0", "false", "no", "off")


@dataclass(frozen=True)
class Definition:
    """One preference: what it is called, what it defaults to, and how it is asked.

    `env` names the variable that pins it. A definition without one is the page's
    alone, which is most of them: a variable exists for a setting that was
    configuration before it was a preference, not for every setting that could
    have one.
    """

    key: str
    # Which fieldset it appears in. Definitions are written in the order they are
    # shown, and `grouped` reads the sections off them rather than keeping a second
    # list to fall out of step with.
    section: str
    # As short as it can be and still be unambiguous. The explanation is `note`,
    # which the page shows on hover rather than printing under the control
    # (interface-text); a control named only by its tooltip is an unnamed control,
    # so the label has to carry the meaning on its own.
    label: str
    note: str
    kind: str
    default: str
    choices: tuple[tuple[str, str], ...] = ()
    env: str = ""
    # Whether the answers to this one are worked out when the page is drawn rather
    # than written here. Only the label destination is: its list holds one entry per
    # print agent, and those are named in the environment (ADR-0025), so a static
    # tuple could only ever be out of date. See `choices_for`.
    live: bool = False


DEFINITIONS: tuple[Definition, ...] = (
    Definition(
        key="site_name",
        section=APPEARANCE,
        label="Name",
        note=(
            "In the banner, the browser's tab, the foot of every page and the preview a "
            "shared link unfolds into. Empty goes back to the name the software ships with."
        ),
        kind=TEXT,
        default=DEFAULT_SITE_NAME,
    ),
    Definition(
        key="watermark",
        section=APPEARANCE,
        label="Watermark photographs",
        note=(
            "Composited into the copy that is served, so a photograph saved elsewhere "
            "still says where it came from. The original on disk is never touched."
        ),
        kind=SWITCH,
        default="1",
        env="RHDB_WATERMARK",
    ),
    Definition(
        key="theme",
        section=APPEARANCE,
        label="Theme",
        note=(
            "What somebody gets who has never chosen a theme. A device that has chosen "
            "one keeps its choice."
        ),
        kind=CHOICE,
        default="system",
        choices=(
            ("system", "browser setting"),
            ("light", "light"),
            ("dark", "dark"),
        ),
    ),
    Definition(
        key="label_destination",
        section=LABELS,
        label="Small label goes to",
        note=(
            "What the small printer button does. A device that has chosen for itself "
            "keeps its choice; this is what everything else does."
        ),
        kind=CHOICE,
        default=PDF,
        live=True,
    ),
    Definition(
        key="label_bluetooth_media",
        section=LABELS,
        label="Bluetooth label size",
        note=(
            "The stock loaded in the Bluetooth printer. A label printed at the wrong "
            "size is discovered by peeling it off something."
        ),
        kind=CHOICE,
        default="niimbot-50x30",
        live=True,
    ),
    Definition(
        key="block_search_engines",
        section=SERVER,
        label="Block search engines",
        note=(
            "Asks every crawler not to file any page of this site. It is a request and "
            "not a lock: anything that must not be read by a stranger belongs behind "
            "the login."
        ),
        kind=SWITCH,
        default="0",
    ),
)

BY_KEY = {d.key: d for d in DEFINITIONS}


def choices_for(d: Definition) -> tuple[tuple[str, str], ...]:
    """The answers a setting offers, now.

    Written out on the definition for every setting but the two about labels. What
    a label may be sent to depends on what printers this installation has -- the
    print agents come from the environment and the Niimbot stocks from the label
    module -- so writing them here would be keeping a third copy of a list that
    already exists twice, and the copy would be the one that went stale.

    Imported inside the function: `printing` reaches the models and `labels` the
    renderer, and both of those are read while a page is being drawn, which is
    exactly when this module is already being read.
    """
    if not d.live:
        return d.choices
    from . import labels, printing

    if d.key == "label_bluetooth_media":
        return tuple(
            (name, media["what"]) for name, media in labels.MEDIA.items() if "niimbot" in name
        )
    return (
        (PDF, "a PDF to download"),
        (BLUETOOTH, "a Niimbot over Bluetooth, from this device"),
        *(
            (AGENT + a.name, f"{a.name} — {labels.MEDIA[a.media]['what']}")
            for a in printing.agents().values()
        ),
    )


def grouped() -> list[tuple[str, list[Definition]]]:
    """The definitions as the page lays them out: a fieldset to a section, in the
    order the sections first appear.

    A dict rather than a filter per section, so a definition written in the wrong
    place joins its own section instead of opening a second fieldset with the same
    legend."""
    out: dict[str, list[Definition]] = {}
    for d in DEFINITIONS:
        out.setdefault(d.section, []).append(d)
    return list(out.items())


# Read once and kept, because these are asked for several times in the rendering of
# every page and change about as often as the site is renamed. `forget` is what
# makes that safe: the page drops it on the way out of a save, so the next render
# reads the row that was just written. One uvicorn process today -- see ADR-0023 on
# what a second one would mean.
_cache: dict[str, str] | None = None


def forget() -> None:
    """Drop the cache. Called after a save, and by the suite between tests."""
    global _cache
    _cache = None


def _stored() -> dict[str, str]:
    global _cache
    if _cache is None:
        with SessionLocal() as db:
            _cache = {row.name: row.value for row in db.query(Setting).all()}
    return _cache


def pinned(d: Definition) -> str | None:
    """The environment's answer for this setting, or None if it has not given one.

    Blank is not an answer. Compose passes variables through as `${VAR:-}`, so an
    unset one arrives as an empty string rather than as nothing at all, and reading
    that as a pin would come up with every setting in the stack frozen on a value
    nobody chose.
    """
    if not d.env:
        return None
    raw = os.getenv(d.env, "")
    return raw if raw.strip() else None


def value(key: str) -> str:
    """What a setting is, from whichever of the three places has an answer."""
    d = BY_KEY[key]
    return pinned(d) or _stored().get(key) or d.default


def on(key: str) -> bool:
    """A switch, as a boolean."""
    return value(key).strip().lower() not in OFF


def site_name() -> str:
    return value("site_name")


def clean(d: Definition, raw: str | None) -> str | None:
    """What was posted, as the definition's own kind, or None if it is not an answer
    this setting has.

    A switch reads its silence: an unticked box posts nothing, which is the same
    reading `files.public` and the for-sale flag already take of the same gesture.
    A choice must come back as one of the words it was offered -- anything else is
    a form that did not come from this page -- and blank text means the default,
    which is how a name is cleared rather than emptied.
    """
    if d.kind == SWITCH:
        return "0" if raw is None else "1"
    text = (raw or "").strip()
    if d.kind == CHOICE:
        return text if text in dict(choices_for(d)) else None
    return text[:200]


def save(db: Session, form: Posted) -> None:
    """Write what the page posted, reading the definitions rather than the form.

    The form is never the list of what to store: a posted name that is not a
    setting cannot make a row, and a setting the environment has pinned is stepped
    over rather than written and ignored -- storing a value that could not take
    effect is how a page comes to disagree with the site it is describing.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    for d in DEFINITIONS:
        if pinned(d) is not None:
            continue
        fresh = clean(d, form.get(d.key))
        if fresh is None:
            continue
        row = db.get(Setting, d.key)
        if row is None:
            db.add(Setting(name=d.key, value=fresh, updated_at=now))
        else:
            row.value = fresh
            row.updated_at = now
    db.commit()
    forget()
