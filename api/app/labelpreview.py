"""The picture of each label on Settings → Labels (MANUAL §13, "Seeing it as you
set it up"): the example it is drawn for, and the stock it is drawn on.

The picture is the label, drawn by `labels` as every label is, from the settings
on the page rather than the ones saved: `settings.unsaved` reads the page the way
Save would, and nothing here keeps what it read. It is drawn for an example rather
than for anything in the collection, so a register with nothing in it yet still
has a picture, and so that every tick has something to print: each example carries
every detail its sort of thing can have.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from . import labels, printing, settings

# The example's tag. The shape of a tag, so it is laid out as one; and never issued
# -- a new tag is four of an alphabet with no O in it, and an old one is four digits
# -- so the code in the picture opens nothing if somebody scans the screen.
TAG = "RH-DEMO"

# What the example can be, in the order its menu offers them, in the words the menu
# uses. Each carries the list differently, which is the reason there is a menu.
KINDS: tuple[tuple[str, str], ...] = (
    (labels.COMPUTER, "Machine"),
    (labels.PART, "Part"),
    (labels.PROJECT, "Project"),
    (labels.LOCATION, "Location"),
)

# What each label is pictured for when the page opens: what each is printed for as
# the two start out -- the small one for the parts, the parcels and the boxes, the
# full one for a machine.
STARTS = {labels.LABELS[0]: labels.PART, labels.LABELS[1]: labels.COMPUTER}

# The examples, as an item's label reads it (printing.source_of). A machine and a
# part with a name of their own, so Make and model has something to add; a serial
# number, and somewhere each is kept. A project has none of those three, and a
# location reads none of the list.
EXAMPLES: dict[str, printing.Source] = {
    labels.COMPUTER: printing.Source(
        {
            "asset_id": TAG,
            "name": "Workshop PC",
            "manufacturer": "Amstrad",
            "model": "PC1512",
            "year": 1986,
            "serial": "1512-04187",
            "cpu": "Intel 8086 at 8 MHz",
            "installed_ram": "640 KB",
            "drives": '5.25" 360KB',
            "os": "MS-DOS 3.2",
            "condition": "Working",
            "kept": "Workshop / Rack 3 / Shelf 2",
        },
        [],
        "",
        None,
    ),
    labels.PART: printing.Source(
        {
            "asset_id": TAG,
            "type": "storage",
            "name": "Boot disk",
            "manufacturer": "Seagate",
            "model": "ST-225",
            "year": 1984,
            "serial": "3B4471",
            "condition": "Working",
            "computer_id": "",
            "kept": "Workshop / Drawer 4",
        },
        [],
        "",
        [
            ("Capacity", "20MB"),
            ("CHS", "615/4/17"),
            ("Form factor", '5.25"'),
            ("Interface", "MFM"),
        ],
    ),
    labels.PROJECT: printing.Source(
        {
            "asset_id": TAG,
            "name": "Recap the PC1512",
            "status": "active",
            "started_at": date(2026, 9, 12),
            "target_date": date(2026, 12, 1),
            "summary": "New capacitors throughout, and the clock battery off the board.",
        },
        [],
        "",
        None,
    ),
    labels.LOCATION: printing.Source(
        {
            "asset_id": TAG,
            "name": "Shelf 2",
            "path": "Workshop / Rack 3",
            "kind": "Shelf",
            "notes": "Boxed floppy drives",
        },
        [],
        "",
        None,
    ),
}


def stock_for(key: str, over: Mapping[str, str] | None = None) -> str:
    """The stock one label is drawn on: the one where it goes, as the Label panel's
    picture is (printing.stocks), by the settings on the page. A place there is no
    longer a printer for, or a stock this version does not know, is its own Stock --
    which is what its button hands over."""
    own = labels.setup(key, over).stock
    goes = settings.value(f"label_{key}_destination", over)
    stock = printing.stocks(own, settings.value("label_bluetooth_media", over)).get(goes, own)
    return stock if stock in labels.MEDIA else own


def picture(key: str, kind: str, over: Mapping[str, str] | None = None) -> bytes:
    """One label as it prints, for the example of one sort of thing, set up as `over`
    says where it says anything and as saved where it does not."""
    example = EXAMPLES[kind]
    return labels.render_png(
        example.row,
        example.parts,
        kind,
        labels.MEDIA[stock_for(key, over)],
        small=key == labels.LABELS[0],
        form_factor=example.form_factor,
        spec_pairs=example.spec_pairs,
        label=labels.setup(key, over),
    )


def shown(key: str) -> dict[str, object]:
    """One label's picture as the page draws it before anything is changed: where to
    fetch it, how many dots it is across and down, the stock it is on and the example
    it is for -- all as saved, which is what the address asks for when it sends
    nothing else."""
    stock = stock_for(key)
    across, down = labels.size_dots(labels.MEDIA[stock])
    return {
        "src": f"/settings/labels/preview.png?label={key}&kind={STARTS[key]}",
        "w": across,
        "h": down,
        "what": labels.MEDIA[stock]["what"],
        "kind": STARTS[key],
    }


def script_data() -> dict[str, object]:
    """What the page's script needs to say what the picture is as the settings
    change, without asking: every stock's words and size in dots, the stock each
    agent prints on, and what each example is called in a sentence."""
    media = {}
    for name, stock in labels.MEDIA.items():
        across, down = labels.size_dots(stock)
        media[name] = {"what": stock["what"], "w": across, "h": down}
    return {
        "media": media,
        "agents": {settings.AGENT + a.name: a.media for a in printing.agents().values()},
        "kinds": {kind: words.lower() for kind, words in KINDS},
    }
