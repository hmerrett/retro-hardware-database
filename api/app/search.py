"""Search over the register: the term parser and the "any field" haystack the
search bar and the suggestion list both match against, the suggestion list
itself, and the catalogue of /browse views that sit behind the figures on
/stats.

Lifted out of main.py. Pure logic over rows the caller has already loaded plus
the queries a view needs to name its asset ids; the /, /suggest, /browse and
projects-list routes stay in main and call in here.
"""

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Literal, NamedTuple, TypedDict, cast

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.query import RowReturningQuery

from . import entry, machines, projects, specdb
from .common import (
    LEGACY_DISK_BUSES,
    OWNER_ONLY,
    _all_years,
    _held,
    _portraits,
    _visible,
    folder_images,
    to_dict,
)
from .models import (
    AssetVariant,
    Computer,
    ComputerDrive,
    ComputerRamChip,
    IoSpec,
    LogEntry,
    MotherboardSpec,
    NetworkSpec,
    Part,
    PartPort,
    PartRamSlot,
    PartSlot,
    Project,
    SoundSpec,
    StorageSpec,
    VideoSpec,
)
from .photos import _storage_placeholder, img_url, pick_images

# The three things the register holds, which is what a search is over: a query, a
# haystack and a suggestion are each asked of all three rather than of any one.
type Asset = Computer | Part | Project


# A card row as the gallery builds it (routers/gallery._catalogue_rows), spelt out
# as a pair rather than left a dict of mixed values: "kind" is what the browse
# tests below turn on, so tagging the two says which model r["obj"] holds on either
# side of that guard, instead of leaving every test to read from `object`.
class _CardFields(TypedDict):
    """What a card carries whichever of the two kinds of thing it is about."""

    cat: str
    cat_label: str
    parent: str
    year: int | str
    name: str
    image: str
    ref_photo: bool
    ref_icon: str
    placeholder: str
    updated: str
    added: str
    maker: str
    acquired: str
    catsort: int
    sub: str
    search: str


class ComputerCard(_CardFields):
    kind: Literal["computer"]
    obj: Computer


class PartCard(_CardFields):
    kind: Literal["part"]
    obj: Part


type Card = ComputerCard | PartCard
type CardTest = Callable[[Card], bool]


class BrowseView(NamedTuple):
    """What _browse_view answers with. Named rather than a bare tuple for the type
    checker's sake: a lambda inside a returned tuple literal is not checked against
    the return type, and one handed to a constructor is -- so a test that reads a
    column only a part has, without first asking whether the row is a part, is an
    error here and would have been silence there."""

    heading: str
    note: str
    crumb: tuple[str, str] | None
    keep: CardTest


def search_terms(query: str | None) -> list[str]:
    """A query as the list of things that must all appear. Bare words are words;
    "a quoted run" is one term, so a phrase can be asked for exactly."""
    terms: list[str] = []
    for i, chunk in enumerate((query or "").lower().split('"')):
        if i % 2:
            if chunk.strip():
                terms.append(chunk.strip())
        else:
            terms.extend(chunk.split())
    return terms


def _haystack(
    db: Session, obj: Asset, history: Mapping[str, list[str]], authed: bool = False
) -> str:
    """Everything written about one item, as one lowercase string: every text
    column, its rendered specs or memory and drives, and its history. This is what
    makes a search over "any field" true rather than nearly true.

    "Any field" means every field the reader is looking at anyway -- so a field the
    reader is not looking at has to come out, and OWNER_ONLY is the list of those.
    Read from a named set rather than written out here, because the failure is
    silent: a column added to a model joins this string without anybody deciding it
    should, and a visitor searching "true" was handed the for-sale shortlist off a
    page that shows no such thing (ADR-0018). The project columns come out the same
    way, via _visible on the queries that reach one."""
    # Blanked rather than dropped, so who is asking changes what the haystack says
    # and never how many fields it has: an item nobody has flagged then reads
    # identically for both, and the seams a quoted phrase must not match across stay
    # where they are either way.
    fields = [
        "" if (not authed and c.name in OWNER_ONLY) else str(getattr(obj, c.name) or "")
        for c in obj.__table__.columns
    ]
    fields += history.get(obj.asset_id, [])
    if isinstance(obj, Part):
        fields.append(entry.type_label(obj.type or "other"))
    if isinstance(obj, Project):
        # The status as it is written on screen as well as the slug it is stored
        # as: "in progress" is what somebody would type, and 'active' is what the
        # column holds. And the jobs and the orders, because a project keeps words
        # in child tables the way a part keeps them in its specs -- see
        # projects.searchable for why the things on order are worth reaching.
        fields.append(projects.status_label(obj.status))
        fields += projects.searchable(db, obj.asset_id)
    # Joined by newline, not by space: with a space, a quoted phrase could match
    # across the seam between two fields -- a part whose model is "Etherlink" and
    # whose name begins "III" would answer to "etherlink iii", which it is not.
    return "\n".join(fields).lower()


def _history_by_asset(db: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for aid, message in db.query(LogEntry.asset_id, LogEntry.message):
        out.setdefault(aid, []).append(message or "")
    return out


def _search(db: Session, rows: list[Card], query: str | None, authed: bool = False) -> list[Card]:
    """The rows whose text contains every term. Done in Python over the rows the
    page already loaded: at this size it is a few hundred string searches, and it
    matches exactly what a reader would call a match rather than what SQL collation
    would.

    `authed` decides how much of each row there is to match against, and is carried
    all the way down rather than defaulted here, so the two searches on this site
    cannot come to disagree about what is private (see _haystack)."""
    terms = search_terms(query)
    if not terms:
        return rows
    history = _history_by_asset(db)
    kept = []
    for r in rows:
        hay = _haystack(db, r["obj"], history, authed)
        if all(t in hay for t in terms):
            kept.append(r)
    return kept


# --- GUI: what the search bar offers while you are still typing --------------

SUGGEST_LIMIT = 10


def _suggest_tier(obj: Asset, name: str, raw: str) -> int:
    """Which band of the list an item belongs in, lowest first: what was typed is
    its asset tag, or the start of one, or the start of its name, or somewhere in
    what identifies it -- or else it matched on a spec or a history entry, which
    is a real hit but not one to put at the top of a list of ten."""
    aid = (obj.asset_id or "").lower()
    if aid == raw:
        return 0
    if aid.startswith(raw):
        return 1
    if name.lower().startswith(raw):
        return 2
    # getattr rather than attribute access: a project is identified by its name
    # alone -- it is not one of a model and has no maker -- and this is asked of
    # every kind of thing the register holds.
    ident = " ".join(
        [
            obj.asset_id or "",
            name,
            getattr(obj, "manufacturer", "") or "",
            getattr(obj, "model", "") or "",
        ]
    ).lower()
    return 3 if raw in ident else 4


class _Hit(TypedDict):
    """One thing a half-typed query matched, before the list is cut to ten."""

    obj: Asset
    kind: str
    name: str
    tier: int


def _suggest(
    db: Session, query: str | None, limit: int = SUGGEST_LIMIT, authed: bool = False
) -> tuple[list[dict[str, object]], int]:
    """The first few items a query matches, and how many it matches in all.

    Deliberately the same match the search bar itself performs -- every field of
    every item plus its history -- so the list is a preview of the answer Enter
    gives rather than a second, narrower search that disagrees with it. What the
    list adds is an order: a whole-page result can arrive in catalogue order
    because you read it, but ten rows under a half-typed word are being aimed at,
    so the ones that answer to what was typed come first."""
    terms = search_terms(query)
    if not terms:
        return [], 0
    history = _history_by_asset(db)
    latest = dict(
        db.query(LogEntry.asset_id, func.max(LogEntry.created_at))
        .group_by(LogEntry.asset_id)
        .tuples()
        .all()
    )
    raw = " ".join((query or "").lower().split())

    hits: list[_Hit] = []
    # All three kinds the register holds. A project is offered here and not in the
    # gallery grid, and the two are not in tension: the grid is a wall of
    # photographs of things owned, which a plan is not, while this list is a row of
    # names -- and "search anything" ought to reach the thing you are building as
    # well as the parts you are building it from.
    for obj, kind in (
        [(c, "computer") for c in db.query(Computer).all()]
        + [(p, "part") for p in db.query(Part).all()]
        + [(pr, "project") for pr in _visible(db.query(Project), authed).all()]
    ):
        if not all(t in _haystack(db, obj, history, authed) for t in terms):
            continue
        name = entry.display_name(to_dict(obj))
        hits.append({"obj": obj, "kind": kind, "name": name, "tier": _suggest_tier(obj, name, raw)})
    # Two stable sorts rather than one compound key: the second keeps the order of
    # the first within each band, which is how recency settles a tie without the
    # arithmetic of negating a timestamp that may be missing.
    hits.sort(key=lambda h: latest.get(h["obj"].asset_id) or datetime.min, reverse=True)
    # A project is never disposed of -- it has no such flag -- so it sorts with the
    # things that are still here, which is what it is.
    hits.sort(key=lambda h: (h["tier"], bool(getattr(h["obj"], "disposed", False))))

    shown = hits[:limit]
    listings: dict[str, list[tuple[str, str]]] = {}
    kinds: dict[str, str | None] | None = None
    out: list[dict[str, object]] = []
    for h in shown:
        obj = h["obj"]
        # A project has no photograph folder of its own: what is hung on its history
        # is a picture of the work, not a portrait of a thing, and the folder scan
        # below reads portraits. So it is drawn as its icon, always.
        if h["kind"] == "project":
            out.append(
                {
                    "url": f"/projects/{obj.asset_id}",
                    "aid": obj.asset_id,
                    "name": h["name"],
                    "cat": "Project",
                    "year": "",
                    "disposed": False,
                    "img": "",
                    "icon": "/static/placeholders/project.svg",
                }
            )
            continue
        # Past the projects, so what is left is one of the two kinds that are
        # photographed, have a year and can be disposed of. The kind says which; the
        # hit carries the thing itself and cannot narrow what it holds by it.
        held = cast("Computer | Part", obj)
        folder = "computers" if h["kind"] == "computer" else "parts"
        if folder not in listings:
            listings[folder] = folder_images(folder)
        imgs = pick_images(folder, obj.asset_id, listings[folder])
        if h["kind"] == "computer":
            cat, icon = "Computer", entry.placeholder_for("computer")
        else:
            ptype = cast("Part", held).type or "other"
            cat = entry.type_label(ptype)
            icon = entry.placeholder_for(ptype)
            if ptype == "storage":
                # One query, and only when a drive is actually on the list, to tell
                # a floppy from a disc from a disk as the gallery's cards do.
                if kinds is None:
                    kinds = specdb.storage_kinds(db)
                icon = _storage_placeholder(kinds.get(obj.asset_id))
        out.append(
            {
                "url": f"/{folder}/{obj.asset_id}",
                "aid": obj.asset_id,
                "name": h["name"],
                "cat": cat,
                "year": held.year or "",
                "disposed": bool(held.disposed),
                "img": img_url(imgs[0], 300) if imgs else "",
                "icon": f"/static/{icon}",
            }
        )
    return out, len(hits)


# --- GUI: browse, the items behind a figure on /stats -----------------------


def _tagged(query: RowReturningQuery[tuple[str]]) -> CardTest:
    """A row test for the asset ids a single-column query returns. Asset ids are
    unique across the whole register, so the kind needs no separate check."""
    ids = {aid for (aid,) in query}
    return lambda r: r["obj"].asset_id in ids


def _browse_view(db: Session, key: str, val: str) -> BrowseView | None:
    """What /browse?f=<key> means: a heading, a line saying what is on the page, an
    optional link back to the thing it is about, and a test each catalogue row
    passes or fails.

    There is one entry per figure on /stats, which is the point: every number there
    is clickable and lands here on exactly the items it counted. Where a figure adds
    up quantities rather than counting assets -- slots, chips, drives -- the note
    says whose they are, because the count on this page is of items, not of slots.
    Returns None for an unknown view, which the caller turns into a 404."""
    if key == "all":
        return BrowseView(
            "Everything in the register", "computers and parts together", None, lambda r: True
        )
    if key == "computers":
        return BrowseView(
            "Computers",
            "every whole machine in the register",
            None,
            lambda r: r["kind"] == "computer",
        )
    if key == "parts":
        return BrowseView(
            "Parts",
            "everything tagged in its own right rather than as a machine",
            None,
            lambda r: r["kind"] == "part",
        )
    if key == "photos":
        return BrowseView(
            "Photographed",
            "items with at least one photograph on file",
            None,
            lambda r: bool(r["image"]),
        )
    if key == "nophotos":
        # The queue behind the coverage figure, and it reads the same answer the
        # figure did rather than a row test that resembles it: one pass over the two
        # folders, then a set lookup per row, the way _tagged works. Held only, so
        # unlike its opposite above this view excludes the disposed -- a record of
        # something gone can still have its picture, but nobody can go and take one.
        missing = _portraits(db)[1]
        return BrowseView(
            "Not photographed yet",
            "everything still here waiting for a camera",
            None,
            lambda r: r["obj"].asset_id in missing,
        )
    if key == "source":
        return BrowseView(
            f"Came from {val}",
            "as recorded in the source field",
            None,
            lambda r: (r["obj"].source or "") == val,
        )
    if key == "maker":
        return BrowseView(
            f"Parts made by {val}",
            "as recorded in the maker field",
            None,
            lambda r: r["kind"] == "part" and (r["obj"].manufacturer or "") == val,
        )
    if key == "type":
        return BrowseView(
            entry.type_label(val),
            "every one of them in the register",
            None,
            lambda r: r["kind"] == "part" and r["cat"] == val,
        )
    if key == "condition":
        return BrowseView(
            f"Parts recorded as {val}",
            "condition as it was last checked",
            None,
            lambda r: r["kind"] == "part" and (r["obj"].condition or "") == val,
        )
    if key == "year":
        return BrowseView(
            "Items with a year",
            "what the average year is worked out from",
            None,
            lambda r: bool(r["obj"].year),
        )
    if key == "extremes":
        years = _all_years(db)
        ends = {min(years), max(years)} if years else set()
        return BrowseView(
            "The oldest and the newest",
            "the two ends of the range",
            None,
            lambda r: r["obj"].year in ends,
        )
    if key == "ram":
        sizes = sorted({int(x) for x in val.split(",") if x.strip().isdigit()})
        return BrowseView(
            ("Machines with " + " or ".join(entry.fmt_kb(kb) for kb in sizes) + " fitted")
            if sizes
            else "Machines by memory fitted",
            "read from the typed memory column, not from the text",
            None,
            lambda r: r["kind"] == "computer" and r["obj"].installed_ram_kb in sizes,
        )
    if key == "ramfitted":
        return BrowseView(
            "Machines with their memory recorded",
            "the machines the memory total is added up from",
            None,
            lambda r: r["kind"] == "computer" and r["obj"].installed_ram_kb is not None,
        )
    if key == "storage":
        return BrowseView(
            "Storage with a capacity recorded",
            "the parts the storage total is added up from",
            None,
            _tagged(db.query(StorageSpec.part_id).filter(StorageSpec.capacity_kb.isnot(None))),
        )
    if key == "slots":
        return BrowseView(
            "Boards with expansion slots",
            "the boards those slots are on",
            None,
            _tagged(db.query(PartSlot.part_id).distinct()),
        )
    if key == "bus":
        return BrowseView(
            f"Boards with {val} slots",
            "the boards those slots are on",
            None,
            _tagged(db.query(PartSlot.part_id).filter(PartSlot.bus == val)),
        )
    if key == "port":
        return BrowseView(
            f"Fitted with a {val} port",
            "the cards and boards those ports are on",
            None,
            _tagged(db.query(PartPort.part_id).filter(PartPort.port == val)),
        )
    if key == "chips":
        return BrowseView(
            "Machines with memory chips on the board",
            "the machines those chips are soldered or socketed into",
            None,
            _tagged(db.query(ComputerRamChip.computer_id).distinct()),
        )
    if key == "drives":
        return BrowseView(
            "Machines with a drive fitted",
            "the machines those drives are in",
            None,
            _tagged(db.query(ComputerDrive.computer_id).distinct()),
        )
    if key == "gotek":
        return BrowseView(
            "Machines with a Gotek",
            "a floppy emulator standing in for a drive",
            None,
            _tagged(
                db.query(ComputerDrive.computer_id).filter(ComputerDrive.kind == "Gotek").distinct()
            ),
        )
    if key == "fitted":
        return BrowseView(
            "Parts fitted in a machine",
            "installed rather than sitting on a shelf",
            None,
            lambda r: r["kind"] == "part" and bool(r["obj"].computer_id),
        )
    if key == "spares":
        return BrowseView(
            "Spares on the shelf",
            "parts not fitted in anything",
            None,
            lambda r: r["kind"] == "part" and not r["obj"].computer_id,
        )
    if key == "disposed":
        return BrowseView(
            "No longer in the collection",
            "binned, sold or donated",
            None,
            lambda r: bool(r["obj"].disposed),
        )
    if key == "held":
        return BrowseView(
            "Items with an acquisition date",
            "when each of these arrived, as recorded",
            None,
            lambda r: r["obj"].acquired_date is not None,
        )
    if key == "model":
        # Everything filed as one catalogue model, machines and bare boards alike:
        # asset_variant is keyed by a plain asset id and does not care which it has,
        # which is the whole of what stage 1 bought. An unknown key is a 404 rather
        # than an empty page, the same as a machine that is not there.
        m = machines.model(val)
        if m is None:
            return None
        return BrowseView(
            m["full_name"],
            "everything in the register filed as this model",
            None,
            _tagged(db.query(AssetVariant.asset_id).filter(AssetVariant.model_key == val)),
        )
    if key == "in":
        machine = db.get(Computer, (val or "").upper())
        if machine is None:
            return None
        name = entry.display_name(to_dict(machine))
        return BrowseView(
            f"Parts fitted in {name}",
            "everything installed in this machine",
            (f"/computers/{machine.asset_id}", name),
            lambda r: r["kind"] == "part" and r["obj"].computer_id == machine.asset_id,
        )
    # --- the views behind the themed figures ------------------------------
    # One per group in the pool, in the same order. Most are a set of asset ids
    # read straight out of the table the figure was counted from, which is what
    # _tagged is for: the figure and the page behind it then cannot disagree, since
    # both are the same query.
    if key == "boards":
        return BrowseView(
            "Motherboards",
            "everything with a board's specs on file",
            None,
            _tagged(db.query(MotherboardSpec.part_id)),
        )
    if key == "formfactor":
        return BrowseView(
            f"Boards built to {val}",
            "as recorded in the form factor field",
            None,
            _tagged(db.query(MotherboardSpec.part_id).filter(MotherboardSpec.form_factor == val)),
        )
    if key == "bios":
        return BrowseView(
            f"Boards with a {val} BIOS",
            "as recorded in the BIOS field",
            None,
            _tagged(db.query(MotherboardSpec.part_id).filter(MotherboardSpec.bios == val)),
        )
    if key == "family":
        return BrowseView(
            f"Boards for a {val} processor",
            "as recorded in the CPU family field",
            None,
            _tagged(db.query(MotherboardSpec.part_id).filter(MotherboardSpec.cpu_family == val)),
        )
    if key == "cache":
        return BrowseView(
            "Boards with cache on them",
            "the boards the cache total is added up from",
            None,
            _tagged(
                db.query(MotherboardSpec.part_id).filter(
                    MotherboardSpec.cache_kb.isnot(None), MotherboardSpec.cache_kb > 0
                )
            ),
        )
    if key == "onboardvideo":
        return BrowseView(
            "Boards with video on the board",
            "no expansion card required",
            None,
            _tagged(
                db.query(MotherboardSpec.part_id).filter(
                    MotherboardSpec.onboard_video.isnot(None), MotherboardSpec.onboard_video != ""
                )
            ),
        )
    if key == "noslots":
        # The difference between two sets rather than a NOT EXISTS: the figure is
        # worked out that way too, and this page has to show the same boards.
        slotted = {a for (a,) in db.query(PartSlot.part_id).distinct()}
        return BrowseView(
            "Boards with no expansion slots",
            "nothing can be added to these",
            None,
            _tagged(
                db.query(MotherboardSpec.part_id).filter(MotherboardSpec.part_id.notin_(slotted))
                if slotted
                else db.query(MotherboardSpec.part_id)
            ),
        )
    if key == "ramslots":
        return BrowseView(
            "Boards with memory sockets",
            "the boards those sockets are on",
            None,
            _tagged(db.query(PartRamSlot.part_id).distinct()),
        )
    if key == "ramslot":
        return BrowseView(
            f"Boards with {val} sockets",
            "the boards those sockets are on",
            None,
            _tagged(db.query(PartRamSlot.part_id).filter(PartRamSlot.slot_type == val)),
        )
    if key == "cards":
        # Everything with a card's specs on file, of any of the four kinds: the
        # population the figures about cards are counted against, rather than any
        # one of their answers. The four share the shape of most of the questions --
        # which bus, whose chip -- so they share a view.
        ids = set()
        for spec in (VideoSpec, SoundSpec, NetworkSpec, IoSpec):
            ids |= {a for (a,) in db.query(spec.part_id)}
        return BrowseView(
            "Expansion cards",
            "video, sound, network and I/O together",
            None,
            lambda r: r["obj"].asset_id in ids,
        )
    if key == "vram":
        return BrowseView(
            "Graphics cards with their memory recorded",
            "the cards the video memory total is added up from",
            None,
            _tagged(
                db.query(VideoSpec.part_id).filter(
                    VideoSpec.memory_kb.isnot(None), VideoSpec.memory_kb > 0
                )
            ),
        )
    if key == "vramsize":
        sizes = sorted({int(x) for x in val.split(",") if x.strip().isdigit()})
        return BrowseView(
            ("Graphics cards with " + " or ".join(entry.fmt_kb(kb, True) for kb in sizes))
            if sizes
            else "Graphics cards by memory",
            "read from the typed memory column, not from the text",
            None,
            _tagged(
                db.query(VideoSpec.part_id).filter(
                    VideoSpec.memory_kb.in_(sizes) if sizes else VideoSpec.memory_kb.isnot(None)
                )
            ),
        )
    if key == "prevga":
        # The same four LIKEs the figure is counted with, so the page cannot show a
        # different set of cards from the one the number claimed.
        return BrowseView(
            "Graphics cards from before VGA",
            "MDA, CGA, EGA or composite, and nothing later",
            None,
            _tagged(
                db.query(VideoSpec.part_id).filter(
                    VideoSpec.connector.isnot(None),
                    VideoSpec.connector != "",
                    ~VideoSpec.connector.like("%VGA%"),
                    ~VideoSpec.connector.like("%DVI%"),
                )
            ),
        )
    if key == "nochip":
        ids = set()
        for spec in (VideoSpec, SoundSpec, NetworkSpec, IoSpec):
            ids |= {
                a
                for (a,) in db.query(spec.part_id).filter((spec.chip.is_(None)) | (spec.chip == ""))
            }
        return BrowseView(
            "Cards with no chip recorded",
            "nobody has written down what is on them",
            None,
            lambda r: r["obj"].asset_id in ids,
        )
    if key == "ports":
        return BrowseView(
            "Boards and cards with ports",
            "the things those ports are on",
            None,
            _tagged(db.query(PartPort.part_id).distinct()),
        )
    if key == "legacydisk":
        return BrowseView(
            "Drives on a dead interface",
            "MFM, RLL, ESDI and XTA: none of them survived the 1990s",
            None,
            _tagged(
                db.query(StorageSpec.part_id).filter(StorageSpec.interface.in_(LEGACY_DISK_BUSES))
            ),
        )
    if key == "rpm":
        return BrowseView(
            "Drives with a spindle speed recorded",
            "mechanical disks that say",
            None,
            _tagged(
                db.query(StorageSpec.part_id).filter(
                    StorageSpec.speed_rpm.isnot(None), StorageSpec.speed_rpm > 0
                )
            ),
        )
    if key == "optical":
        return BrowseView(
            "Optical drives",
            "everything that takes a disc",
            None,
            _tagged(db.query(StorageSpec.part_id).filter(StorageSpec.kind == entry.OPTICAL_KIND)),
        )
    if key == "geometry":
        return BrowseView(
            "Drives with their geometry on file",
            "cylinders, heads and sectors as the drive reports them",
            None,
            _tagged(
                db.query(StorageSpec.part_id).filter(
                    StorageSpec.chs_c.isnot(None), StorageSpec.chs_c > 0
                )
            ),
        )
    if key == "flash":
        return BrowseView(
            "Machines with a card standing in for a drive",
            "CF or SD where a disk or a floppy used to be",
            None,
            _tagged(
                db.query(ComputerDrive.computer_id)
                .filter(ComputerDrive.kind.in_(("CF", "SD")))
                .distinct()
            ),
        )
    if key == "os":
        return BrowseView(
            "Machines with an operating system recorded",
            "what each of them boots, as last seen",
            None,
            lambda r: r["kind"] == "computer" and bool(r["obj"].os),
        )
    if key == "dos":
        return BrowseView(
            "Machines running DOS",
            "MS-DOS, FreeDOS or the like",
            None,
            lambda r: r["kind"] == "computer" and "DOS" in (r["obj"].os or ""),
        )
    if key == "cpu":
        return BrowseView(
            "Machines with their processor recorded",
            "the machines the processor figures are counted from",
            None,
            lambda r: r["kind"] == "computer" and bool(r["obj"].cpu),
        )
    if key == "chassis":
        return BrowseView(
            f"Machines in a {val} case",
            "as recorded in the chassis field",
            None,
            lambda r: r["kind"] == "computer" and (r["obj"].chassis or "") == val,
        )
    if key == "portable":
        return BrowseView(
            "Machines meant to be carried",
            "laptops and luggables, the second word doing a lot of work",
            None,
            lambda r: (
                r["kind"] == "computer"
                and (r["obj"].chassis or "").lower() in ("laptop", "luggable")
            ),
        )
    if key == "benchmarked":
        return BrowseView(
            "Machines with a TopBench score",
            "the ones it has been run on",
            None,
            lambda r: r["kind"] == "computer" and r["obj"].topbench is not None,
        )
    if key == "variant":
        return BrowseView(
            "Filed as a catalogue model",
            "machines and boards the catalogue can name",
            None,
            _tagged(db.query(AssetVariant.asset_id)),
        )
    if key == "emptymachines":
        fitted = {
            c
            for (c,) in _held(db.query(Part.computer_id).filter(Part.computer_id.isnot(None)), Part)
        }
        return BrowseView(
            "Machines with nothing fitted",
            "no part in the register is installed in these",
            None,
            lambda r: r["kind"] == "computer" and r["obj"].asset_id not in fitted,
        )
    if key == "century":
        return BrowseView(
            "Made in this century",
            "2000 or later, by the year on the record",
            None,
            lambda r: (r["obj"].year or 0) >= 2000,
        )
    if key == "recent":
        cutoff = date.today().year - 10
        return BrowseView(
            "Made in the last ten years",
            f"{cutoff} or later — new parts for old machines",
            None,
            lambda r: (r["obj"].year or 0) >= cutoff,
        )
    if key in ("born", "older"):
        # Both compare a fitted part's year against its machine's, so both are the
        # same join with one operator changed.
        gaps = (
            db.query(Part.asset_id, Part.year - Computer.year)
            .join(Computer, Computer.asset_id == Part.computer_id)
            .filter(Part.year.isnot(None), Computer.year.isnot(None))
            .all()
        )
        if key == "born":
            ids = {a for a, gap in gaps if gap == 0}
            return BrowseView(
                "Fitted to a machine of its own year",
                "part and machine made the same year",
                None,
                lambda r: r["obj"].asset_id in ids,
            )
        ids = {a for a, gap in gaps if gap is not None and gap < 0}
        return BrowseView(
            "Older than the machine it is in",
            "made before the thing it was fitted to",
            None,
            lambda r: r["obj"].asset_id in ids,
        )
    if key == "nosource":
        return BrowseView(
            "Parts with no recorded source",
            "nothing on file about where they came from",
            None,
            lambda r: r["kind"] == "part" and not (r["obj"].source or "").strip(),
        )
    if key == "unwritten":
        return BrowseView(
            "Parts with nothing written about them",
            "no summary and no notes",
            None,
            lambda r: (
                r["kind"] == "part" and not (r["obj"].summary or "") and not (r["obj"].notes or "")
            ),
        )
    if key == "links":
        return BrowseView(
            "Parts with a link out",
            "somebody else's page about the same thing",
            None,
            lambda r: r["kind"] == "part" and bool(r["obj"].url),
        )
    if key == "diskimages":
        return BrowseView(
            "Parts with a disk image kept",
            "the contents as well as the object",
            None,
            lambda r: r["kind"] == "part" and bool(r["obj"].disk_image),
        )
    if key == "subparts":
        return BrowseView(
            "Parts fitted to another part",
            "a daughterboard, a riser, or a chip on a carrier",
            None,
            lambda r: r["kind"] == "part" and bool(r["obj"].parent_id),
        )
    if key == "sourcelike":
        # A prefix, not the whole field: "eBay order no. 19-14922-72542" is one
        # order and there are dozens of them, but "bought on eBay" is one answer.
        # Folded, because the figures behind this are counted with SQL LIKE, which
        # is case-insensitive under both engines the app runs on. A bare
        # str.startswith is not, and would show fewer items than the number claimed.
        fold = val.lower()
        return BrowseView(
            f"Came from {val}",
            "everything whose source starts with this",
            None,
            lambda r: (r["obj"].source or "").lower().startswith(fold),
        )
    if key == "sparetype":
        return BrowseView(
            f"{entry.type_label(val)} on the shelf",
            "not fitted to anything",
            None,
            lambda r: r["kind"] == "part" and r["cat"] == val and not r["obj"].computer_id,
        )
    if key == "dupes":
        # Every maker-and-model held more than once, which is the set the figure
        # counted rather than a resemblance to it.
        repeated = {
            (m or "", mo or "")
            for m, mo, n in _held(
                db.query(Part.manufacturer, Part.model, func.count(Part.asset_id)).filter(
                    Part.model.isnot(None), Part.model != ""
                ),
                Part,
            )
            .group_by(Part.manufacturer, Part.model)
            .all()
            if n > 1
        }
        return BrowseView(
            "Held more than once",
            "the same maker and model, twice or more",
            None,
            lambda r: (
                r["kind"] == "part"
                and ((r["obj"].manufacturer or ""), (r["obj"].model or "")) in repeated
            ),
        )
    return None


def _projects_matching(
    db: Session, rows: list[projects.Summary], query: str | None, authed: bool = False
) -> list[projects.Summary]:
    """The project rows whose text contains every term.

    The same match the gallery makes of a machine -- every column, plus the history
    -- with the jobs and the things on order folded in by _haystack. Done in Python
    over the rows the page has already loaded, for the reason _search is: at this
    size it is a few dozen string searches, and it matches what a reader would call
    a match rather than what SQL collation would.

    `authed` is passed through because the rows handed in were already narrowed by
    it -- see projects.summaries -- and a search that reached further than the list
    it is sifting would be a strange thing to leave lying about."""
    terms = search_terms(query)
    if not terms:
        return rows
    history = _history_by_asset(db)
    return [r for r in rows if all(t in _haystack(db, r["p"], history, authed) for t in terms)]
