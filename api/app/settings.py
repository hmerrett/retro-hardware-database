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

from . import accent as accents
from . import presets, typefaces
from .db import SessionLocal
from .models import Setting

if TYPE_CHECKING:
    # Held back to the type checker, the way photos.py holds the same import back
    # and for the same reason: forms reaches history, history reaches web, and web
    # reads these settings on every page it renders. Imported at runtime that is a
    # closed circle, and the module that lost the race would import a half-built
    # one.
    from .forms import Posted

SWITCH, TEXT, CHOICE, SWATCH = "switch", "text", "choice", "swatch"
# A colour of the owner's own, written as `#rrggbb`. Its own kind rather than a
# text box, because what it will take is a narrower question than "some words":
# the value is spent on a colour in a stylesheet, and `clean` is where that is
# settled once rather than at every place the setting is read.
COLOUR = "colour"

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
        key="preset",
        section=APPEARANCE,
        label="Preset",
        note=(
            "The look the whole installation wears: its colours, its corners and its "
            "typefaces, and never its layout. A visitor chooses only light or dark within it."
        ),
        kind=SWATCH,
        default=presets.DEFAULT,
        choices=presets.CHOICES,
        env="RHDB_PRESET",
    ),
    Definition(
        key="accent",
        section=APPEARANCE,
        label="Accent",
        note=(
            "The colour that means press this, this is a link, this is where you are. "
            "It is adjusted for the preset and the mode so that it always reads."
        ),
        kind=SWATCH,
        default=accents.AS_PRESET,
        choices=accents.CHOICES,
    ),
    Definition(
        key="accent_custom",
        section=APPEARANCE,
        label="Custom accent",
        note=(
            "A colour written as #rrggbb, which wins over the eight while it has "
            "something in it. Emptying it hands the answer back to them."
        ),
        kind=COLOUR,
        default="",
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
        key="type",
        section=APPEARANCE,
        label="Type",
        note=(
            "Which face does the writing, the interface and the recorded values. "
            "Catalogue: serif, sans and mono. Plain: sans and mono. Ledger: mono throughout."
        ),
        kind=CHOICE,
        default=typefaces.DEFAULT,
        choices=typefaces.CHOICES,
    ),
    Definition(
        key="nav",
        section=APPEARANCE,
        label="Navigation",
        note=(
            "Where the sections sit on a wide screen: down a rail beside the page, or "
            "across the banner above it. Below 1100px and on a phone, the banner either way."
        ),
        kind=CHOICE,
        default="side",
        choices=(("side", "Side"), ("top", "Top")),
    ),
    Definition(
        key="button_case",
        section=APPEARANCE,
        label="Button text",
        note="Save and Add note, or save and add note. Labels and headings keep their capitals.",
        kind=CHOICE,
        default="cap",
        choices=(("cap", "Capitalised"), ("lower", "Lower case")),
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
    Definition(
        key="public_locations",
        section=SERVER,
        label="Show locations",
        note=(
            "Whether somebody who is not signed in is told where a thing is kept. Off, "
            "the row is not on their page and their search does not match on it. You "
            "always see it."
        ),
        kind=SWITCH,
        default="0",
    ),
    Definition(
        key="files_public",
        section=SERVER,
        label="New files are public",
        note=(
            "Starts the Public tick in the upload box ticked, so a file is published as "
            "it arrives unless you untick it first. Off, every upload is kept back until "
            "it is ticked. A private project's uploads always start unticked."
        ),
        kind=SWITCH,
        default="0",
    ),
    Definition(
        key="remember_locations",
        section=SERVER,
        label="Remember old locations",
        note=(
            "Keeps a place on the pick list after the last thing in it has moved out, so "
            "an emptied crate is still offered by name. Turning this off deletes what it "
            "has remembered rather than hiding it."
        ),
        kind=SWITCH,
        default="1",
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
        (BLUETOOTH, "a Niimbot over Bluetooth"),
        *(
            (AGENT + a.name, f"{a.name} {labels.MEDIA[a.media]['short']}")
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


def preset() -> str:
    """The look in force, and always one there is a stylesheet for.

    Checked rather than returned, because this is the one setting whose value
    becomes part of a URL the page then asks the browser to fetch. `presets.known`
    is where that check lives; this is the only way in to it.
    """
    return presets.known(value("preset"))


def typeface() -> str:
    """The pairing in force, and always one the stylesheet has a block for.

    Checked on the way out like `preset` above it, for the milder version of the
    same reason: this one is spent on an attribute rather than on a path, so an
    unknown value would not fetch the wrong file -- it would leave the page saying
    it wears a face that nothing paints."""
    return typefaces.known(value("type"))


def navigation() -> str:
    """Where the sections sit: side or top, and never anything else.

    Read against the definition's own answers rather than a second list, and
    checked because this one is written into a class name on every page: a value
    from a row nobody on this page wrote would otherwise arrive in the markup.
    """
    d = BY_KEY["nav"]
    chosen = value("nav")
    return chosen if chosen in dict(d.choices) else d.default


def accent_brand() -> str:
    """The colour the page is accented with, or empty for the preset's own.

    Two settings and one answer. The box wins while it has something in it and the
    named choice is still underneath when it is emptied, so changing your mind
    about a colour of your own does not cost you the one you had chosen before it.
    Both are checked here rather than trusted: either can have been written by a
    row this page did not put there, and the value is spent on a colour in a
    stylesheet (`accent.known`, `accent.custom`).
    """
    own = accents.custom(value("accent_custom"))
    if own:
        return own
    chosen = accents.known(value("accent"))
    return "" if chosen == accents.AS_PRESET else accents.BRANDS[chosen]


def accent_css() -> str:
    """The accent's stylesheet for the look in force, and the stamp it is asked for
    by. Both come from the same call so a page can never link one and serve the
    other."""
    return accents.stylesheet(preset(), accent_brand())


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
    if d.kind == COLOUR:
        # Blank is an answer -- it is how the box is given back to the eight above
        # it. Anything that is not a colour is not, and `None` here is what leaves
        # the stored value alone rather than overwriting it with a typo.
        return "" if not text else (accents.custom(text) or None)
    if d.kind in (CHOICE, SWATCH):
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
