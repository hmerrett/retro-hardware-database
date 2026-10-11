"""What belongs to a location alone (ADR-0034): its kinds, the tree of locations and
the path up it as names, what a Location box offers and finding the location it
names, and emptying, merging and forgetting one -- plus where a thing is, as a
page and a search read it.

Where anything is, a location included, is one link on the register, and moving
anything is tree.py's (ADR-0036). What is here is the part only a location has: a
name somebody reads, a kind, notes on how to find it, and a path made of those
names -- Workshop, Rack 3, Shelf 2, Box 14 -- read up the links when it is wanted
and never stored. There are hundreds of locations, not millions, so reading all of
them is cheaper than being clever about which.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import NamedTuple

from sqlalchemy.orm import Session

from . import settings
from . import tree as _tree
from .history import add_log
from .ids import exact_tag, next_asset_id
from .models import Computer, Gone, Location, Move, Part, Thing
from .web import templates

# What a location can be, in the order the form offers them. The kind describes a
# location and rules on nothing: somebody's shelf is somebody else's drawer, and a
# rule that a bag cannot hold a box would be wrong in the first loft it met.
KINDS: tuple[tuple[str, str], ...] = (
    ("building", "Building"),
    ("room", "Room"),
    ("rack", "Rack"),
    ("shelf", "Shelf"),
    ("box", "Box"),
    ("bag", "Bag"),
    ("other", "Other"),
)
KIND_NAMES = dict(KINDS)
OTHER = "other"

# How a path is written where it has to be typed or read as text -- a form's box,
# the API, a label. A page draws it as links instead (see `Tree.steps`).
SEP = _tree.SEP

# How a move was made, and why one was refused: tree.py's, named here too because
# this is where a caller putting something away already looks.
EDIT, SCAN, API, UNDO = _tree.EDIT, _tree.SCAN, _tree.API, _tree.UNDO
Refused = _tree.Refused

# For a location's page, which says what sort of place each location inside it is.
templates.env.globals["kind_names"] = KIND_NAMES

# What a location holds, and what can be moved into one.
type Held = Computer | Part


def shown(sees_private: bool) -> bool:
    """Whether this reader may open the locations themselves -- a location's page,
    its photographs, its labels, the list of them: anybody signed in, and a visitor
    only while the owner has said so (ADR-0027, ADR-0034). Where a particular thing
    is kept is that thing's own tick (`told`)."""
    return sees_private or settings.on("public_locations")


# The chrome asks the same of the reader it is drawn for: Locations is offered as a
# section only to somebody who may open it, since a section that answers 404 is a
# section saying that something is being kept back.
templates.env.globals["locations_shown"] = shown


def ticks(db: Session) -> dict[str, bool]:
    """Every machine's and part's Visible tick, by tag: two lean queries, for a page
    that asks it of many."""
    out: dict[str, bool] = {}
    for model in (Computer, Part):
        out.update(dict(db.query(model.asset_id, model.location_public).tuples().all()))
    return out


def told(t: _tree.Tree, marks: Mapping[str, bool], tag: str, sees_private: bool) -> bool:
    """Whether this reader is told where the thing `tag` is kept (ADR-0036): anybody
    signed in, and a visitor when the tick of the outermost thing it is in says so --
    a card's machine's, since the machine's is the one that says whether anybody may
    know which shelf it is on."""
    return sees_private or bool(marks.get(t.outermost(tag)))


@dataclass
class Tree:
    """Every location, read once: {tag: (name, kind, inside)}.

    Asked by a page for paths, by the search for the names along them, and by a
    location's form for whether a new place would put a box inside itself. All of it
    is one dict, so a page that wants forty paths asks the database once. A location
    is only ever inside a location, so this is a closed part of the register's tree
    (tree.py), with the names that make a path readable."""

    rows: dict[str, tuple[str, str, str | None]] = field(default_factory=dict)

    def __contains__(self, tag: object) -> bool:
        return tag in self.rows

    def up(self, tag: str | None) -> list[str]:
        """The tags from the top of the tree down to `tag`, inclusive. Safe against a
        loop nothing in the app can build, for the reason _tree.Tree.up is."""
        out: list[str] = []
        seen: set[str] = set()
        at = tag
        while at and at in self.rows and at not in seen:
            seen.add(at)
            out.insert(0, at)
            at = self.rows[at][2]
        return out

    def steps(self, tag: str | None) -> list[tuple[str, str]]:
        """(tag, name) for each step of the path, top first: what a page links."""
        return [(t, self.rows[t][0]) for t in self.up(tag)]

    def names(self, tag: str | None) -> list[str]:
        return [self.rows[t][0] for t in self.up(tag)]

    def text(self, tag: str | None) -> str:
        """The path as words, `Workshop / Rack 3 / Box 14`, or "" for nowhere."""
        return SEP.join(self.names(tag))

    def children(self, tag: str) -> list[str]:
        return sorted(t for t, (_n, _k, parent) in self.rows.items() if parent == tag)

    def within(self, tag: str) -> set[str]:
        """Every location inside this one, however far down; not itself."""
        out: set[str] = set()
        todo = [tag]
        while todo:
            for child in self.children(todo.pop()):
                if child not in out and child != tag:
                    out.add(child)
                    todo.append(child)
        return out

    def would_loop(self, tag: str, parent: str | None) -> bool:
        """Whether putting `tag` inside `parent` would put it inside itself."""
        return parent is not None and (parent == tag or parent in self.within(tag))


def tree(db: Session) -> Tree:
    return Tree(
        {
            aid: (name, kind, inside.upper() if inside else None)
            for aid, name, kind, inside in db.query(
                Location.asset_id, Location.name, Location.kind, Location.inside_id
            )
        }
    )


def choices(t: Tree) -> list[str]:
    """What a Location box offers: every location as its path, in path order, so
    the two `Box 14`s in different rooms are told apart by where they are."""
    return sorted((t.text(tag) for tag in t.rows), key=str.casefold)


_DIGITS = re.compile(r"(\d+)")


def by_name(name: str) -> tuple[tuple[int, int | str], ...]:
    """A name as a list somebody reads is in order: capitals aside, and the numbers
    in it counted as numbers, so Shelf 2 comes before Shelf 10. Splitting on a group
    leaves the runs of digits at the odd places."""
    return tuple(
        (0, int(part)) if i % 2 else (1, part.casefold())
        for i, part in enumerate(_DIGITS.split(name))
        if part
    )


class Node(NamedTuple):
    """A location's line on the list of them all, with the lines of those inside it."""

    tag: str
    name: str
    kind: str
    held: int
    inside: list["Node"]


def outline(t: Tree, held: Mapping[str, int]) -> list[Node]:
    """Every location as the tree it is (MANUAL §14, "Every location"): those at the
    top, each with the locations inside it, in order of name at every level.

    Walked down from the top, so a loop -- which nothing in the app can build -- is
    left off the list rather than holding the page open: nothing in one is at the
    top, and nothing outside one leads into it."""
    inside: dict[str | None, list[str]] = {}
    for tag, (_name, _kind, parent) in t.rows.items():
        inside.setdefault(parent, []).append(tag)

    def branch(parent: str | None) -> list[Node]:
        return [
            Node(tag, t.rows[tag][0], t.rows[tag][1], held.get(tag, 0), branch(tag))
            for tag in sorted(inside.get(parent, []), key=lambda one: by_name(t.rows[one][0]))
        ]

    return branch(None)


# What the Location box calls a tag that names something that is not a location.
_THING_WORDS = {"computer": "a computer", "part": "a part", "project": "a project"}


def find(db: Session, text: str | None, t: Tree) -> Location | None:
    """The location `text` names, or None when it is blank or names none. Raises
    Refused for text that names something that is not a location, or more than one
    location.

    In the order a person would mean it: a tag, then a path written out in full,
    then a name. A name that names nothing is not refused here; whether that makes
    a new location is the caller's to decide (`choose`)."""
    typed = (text or "").strip()
    if not typed:
        return None
    if (tag := exact_tag(typed)) is not None:
        if tag in t:
            return db.get(Location, tag)
        found = db.get(Thing, tag)
        if found is not None and not isinstance(found, Gone):
            raise Refused(
                f"{tag} is {_THING_WORDS.get(found.what, 'something else')}, not a location."
            )
        raise Refused(f"No location has the tag {tag}.")
    folded = typed.casefold()
    hits = [tag for tag in t.rows if t.text(tag).casefold() == folded] or [
        tag for tag, (name, _k, _p) in t.rows.items() if name.casefold() == folded
    ]
    if len(hits) > 1:
        tags = "; ".join(f"{t.text(tag)} ({tag})" for tag in sorted(hits))
        raise Refused(f"More than one location is called {typed}: {tags}.")
    return db.get(Location, hits[0]) if hits else None


def choose(db: Session, text: str | None, t: Tree) -> Location | None:
    """What a Location box was given, as a location -- made, at the top and of kind
    other, when it names none. That is how putting something away somewhere new
    stays one save rather than an errand to another page first."""
    found = find(db, text, t)
    typed = (text or "").strip()
    if found is not None or not typed:
        return found
    made = Location(asset_id=next_asset_id(db), name=typed[:255], kind=OTHER)
    db.add(made)
    db.flush()
    add_log(db, made.asset_id, "created", "created")
    t.rows[made.asset_id] = (made.name, made.kind, None)
    return made


def kept_in(db: Session, tag: str, marks: Mapping[str, bool] | None = None) -> list[Held]:
    """The machines and parts recorded in this location itself -- not in the
    locations inside it, and not the parts fitted in what is here, which go where
    their machine goes. Disposed things are not kept anywhere.

    `marks`, for a visitor, is every thing's Visible tick: what is here and not
    ticked is not listed, because a public location's page is not a way round the
    tick (ADR-0036)."""
    found: list[Held] = [
        *db.query(Computer)
        .filter(Computer.inside_id == tag, Computer.disposed.is_(False))
        .order_by(Computer.asset_id),
        *db.query(Part)
        .filter(Part.inside_id == tag, Part.disposed.is_(False))
        .order_by(Part.asset_id),
    ]
    if marks is not None:
        found = [x for x in found if marks.get(x.asset_id)]
    return found


def counts(db: Session, t: Tree, marks: Mapping[str, bool] | None = None) -> dict[str, int]:
    """How many things each location holds, all the way down: its own, and those
    of every location inside it -- not the cards in its machines, which are the
    machines' business. Two queries for the whole tree. `marks` as `kept_in`."""
    own: dict[str, int] = {}
    for model in (Computer, Part):
        for tag, aid in db.query(model.inside_id, model.asset_id).filter(
            model.inside_id.isnot(None), model.disposed.is_(False)
        ):
            if tag.upper() in t and (marks is None or marks.get(aid)):
                own[tag.upper()] = own.get(tag.upper(), 0) + 1
    return {tag: own.get(tag, 0) + sum(own.get(c, 0) for c in t.within(tag)) for tag in t.rows}


def empty(db: Session, tag: str, t: Tree) -> bool:
    """Nothing kept in it and no location inside it."""
    return not kept_in(db, tag) and not t.children(tag)


class Placed(NamedTuple):
    """Where a part is because of what it is fitted in, and whose answer that is.

    `whose` and `kind` are carried with the location because the page has to say
    where the answer came from: a location shown against a part without saying it is
    the machine's would read as something somebody chose for the part, and the
    first thing anybody would do about a wrong one is edit the part -- which is the
    one record that cannot fix it."""

    where: str
    whose: str
    kind: str


def inherited(r: _tree.Tree) -> dict[str, Placed]:
    """Where each part fitted in something is kept, because of what it is in: the
    first location up its chain, and the outermost machine or part it is in, whose
    answer that is. Keyed by the part's tag. A part in a machine nobody has placed
    is a part nobody has placed, and is not in here."""
    out: dict[str, Placed] = {}
    for tag, (what, holder) in r.rows.items():
        if what != _tree.PART or r.what(holder) not in (_tree.COMPUTER, _tree.PART):
            continue
        if (where := r.place(tag)) is not None:
            whose = r.outermost(tag)
            out[tag] = Placed(
                where, whose, "computers" if r.what(whose) == _tree.COMPUTER else "parts"
            )
    return out


def effective(r: _tree.Tree, tag: str) -> str | None:
    """The location a thing is in: where it is kept, or for a part fitted in
    something, where that is kept."""
    return r.place(tag)


class Where(NamedTuple):
    """An item page's Location row: the path to link, whose answer it is when a part
    is borrowing its machine's, and what the location says about finding it."""

    tag: str
    steps: list[tuple[str, str]]
    whose: str
    kind: str
    notes: str
    photo: str
    others: int


def where_row(db: Session, obj: Held, r: _tree.Tree, t: Tree) -> Where | None:
    """What the Location row on this item's page says, or None for no row."""
    tag = r.place(obj.asset_id)
    loc = db.get(Location, tag) if tag and tag in t else None
    if tag is None or loc is None:
        return None
    outer = r.outermost(obj.asset_id)
    whose = outer if outer != obj.asset_id else ""
    return Where(
        tag=tag,
        steps=t.steps(tag),
        whose=whose,
        kind=("computers" if r.what(whose) == _tree.COMPUTER else "parts") if whose else "",
        notes=loc.notes or "",
        photo=loc.image or "",
        others=len([x for x in kept_in(db, tag) if x.asset_id != outer]),
    )


def path_words(t: Tree, tags: Iterable[str | None]) -> str:
    """The names along each path, as one string for a haystack: what a search for
    `loft` has to find a thing three boxes down in the loft by."""
    return " ".join(" ".join(t.names(tag)) for tag in tags)


def empty_into_parent(db: Session, loc: Location, who: str, r: _tree.Tree) -> int:
    """Put everything in this location where the location itself is: its things and
    the locations inside it, one level up. Each is a move by edit, because each
    has changed where it is kept. Returns how many went."""
    up = r.holder(loc.asset_id)
    moved = 0
    for thing in list(_tree.contents(db, r, loc.asset_id)):
        moved += _tree.put(db, thing, up, EDIT, who, r) is not None
    return moved


def merge(db: Session, loc: Location, into: Location, who: str, r: _tree.Tree) -> list[str]:
    """Put one location's contents into another, which keeps its tag, and delete the
    first: two spellings of one crate made one (MANUAL §14). Refused for a location
    merged into itself or into anything inside it, which would put its own contents
    nowhere. Returns the photographs to delete once the rows are committed."""
    if into.asset_id == loc.asset_id or r.would_loop(loc.asset_id, into.asset_id):
        raise Refused(f"{loc.name} cannot be merged into itself, or into anything in it.")
    for thing in list(_tree.contents(db, r, loc.asset_id)):
        _tree.put(db, thing, into.asset_id, EDIT, who, r)
    add_log(db, into.asset_id, f"merged {loc.name} ({loc.asset_id}) into this")
    return forget(db, loc, who, r)


def forget(db: Session, loc: Location, who: str, r: _tree.Tree, how: str = EDIT) -> list[str]:
    """Delete a location, with its own history and photographs, and nothing that is
    in it (ADR-0036): a box is where things are, not what they are made of. What was
    directly inside it is left nowhere, each with a move saying so, and the locations
    inside it go with their contents still in them.

    Not the moves of things that were once in it: those are on the things'
    histories, and stay there with the path as it read at the time. The tag stays
    taken (_tree.bury). The photograph files are handed back rather than deleted
    here, because a file cannot be rolled back and the caller commits first."""
    from .models import LogEntry
    from .photos import _drop_log_photos, detect_images

    for thing in list(_tree.contents(db, r, loc.asset_id)):
        _tree.put(db, thing, None, how, who, r)
    rels = detect_images("locations", loc.asset_id) + _drop_log_photos(db, loc.asset_id)
    db.query(LogEntry).filter(LogEntry.asset_id == loc.asset_id).delete(synchronize_session=False)
    db.query(Move).filter(Move.asset_id == loc.asset_id).delete(synchronize_session=False)
    _tree.bury(db, loc)
    return rels


def label_row(loc: Location, t: Tree) -> dict[str, object]:
    """A location as its label reads it: its tag, its name, where it is kept -- the
    path of the locations it is inside, where the box was when the label was printed
    -- its kind and its notes (MANUAL §13, "What's on it")."""
    return {
        "asset_id": loc.asset_id,
        "name": loc.name,
        "kept": t.text(loc.inside_id.upper() if loc.inside_id else None),
        "kind": KIND_NAMES.get(loc.kind, loc.kind),
        "notes": loc.notes,
    }
