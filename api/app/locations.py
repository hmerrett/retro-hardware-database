"""Where things are kept: the tree of locations, the path up it, what a Location box
was given, moving something and writing that down, and where a part is when it does
not say for itself (ADR-0034).

A location is a row with a tag from the register's pool and the location it is
inside, and nothing else about where it is. The path -- Workshop, Rack 3, Shelf 2,
Box 14 -- is read up the parents when it is wanted, from one query of the whole
table (`tree`), and never stored: a stored path is a row to rewrite every time
something upstream moves, and getting that wrong is a register that says a card is
in a loft the box left two years ago. There are hundreds of locations, not
millions, so reading all of them is cheaper than being clever about which.

The same reasoning, one level down, is why a part fitted in a machine has no
location of its own unless it is given one: it is wherever the machine is, worked
out at the moment it is shown (`inherited`).

And the rule a tree of anything has to keep, kept here for the parts mounted on
parts as `Tree.would_loop` keeps it for locations: nothing goes on itself, or on
anything on it (`mount_refusal`).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy.orm import Session

from . import settings
from .history import MOVE_ENTRY, add_log
from .ids import exact_tag, next_asset_id
from .models import Computer, Location, Move, Part, Project
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
SEP = " / "

# How a move was made, as the history says it.
EDIT, SCAN, API, UNDO = "edit", "scan", "api", "undo"
HOW_WORDS = {
    EDIT: "by edit",
    SCAN: "by scan",
    API: "through the API",
    UNDO: "undone in the audit",
}

# For the history panel, which draws a move from its row, and for a location's page,
# which says what sort of place each location inside it is.
templates.env.globals["move_how"] = HOW_WORDS
templates.env.globals["kind_names"] = KIND_NAMES

# What a location holds, and what can be moved into one.
type Thing = Computer | Part
type Movable = Computer | Part | Location


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def shown(sees_private: bool) -> bool:
    """Whether this reader is told where things are kept: anybody signed in, and a
    visitor only while the owner has said so (ADR-0027, ADR-0034)."""
    return sees_private or settings.on("public_locations")


# The chrome asks the same of the reader it is drawn for: Locations is offered as a
# section only to somebody who may open it, since a section that answers 404 is a
# section saying that something is being kept back.
templates.env.globals["locations_shown"] = shown


@dataclass
class Tree:
    """Every location, read once: {tag: (name, kind, parent)}.

    Asked by a page for paths, by the search for the names along them, and by a
    move for whether it would put a box inside itself. All of it is one dict, so a
    page that wants forty paths asks the database once."""

    rows: dict[str, tuple[str, str, str | None]] = field(default_factory=dict)

    def __contains__(self, tag: object) -> bool:
        return tag in self.rows

    def up(self, tag: str | None) -> list[str]:
        """The tags from the top of the tree down to `tag`, inclusive.

        Safe against a loop nothing in the app can build: a walk that trusts that is
        a page that never finishes loading if one ever exists, and the cost of not
        trusting it is a set."""
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
            aid: (name, kind, parent)
            for aid, name, kind, parent in db.query(
                Location.asset_id, Location.name, Location.kind, Location.parent_id
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


class Refused(ValueError):
    """What was asked of a location cannot be done, and why, in words for a form.
    Raised rather than returned, so a caller that forgets to check cannot store the
    wrong answer."""


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
        for kind, model in (("a computer", Computer), ("a part", Part), ("a project", Project)):
            if db.get(model, tag) is not None:
                raise Refused(f"{tag} is {kind}, not a location.")
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


def where_of(obj: Movable) -> str | None:
    """The location a thing or a location is kept in, by tag."""
    return obj.parent_id if isinstance(obj, Location) else obj.location_id


def sentence(from_path: str, to_path: str, how: str) -> str:
    """A move as words, for the API's log and anywhere a move is read without its
    row. The page draws the row instead, with a link at each end."""
    was = from_path or "nowhere recorded"
    now = to_path or "nowhere recorded"
    return f"moved from {was} to {now}, {HOW_WORDS[how]}"


def move(
    db: Session, obj: Movable, to: str | None, how: str, who: str, t: Tree | None = None
) -> Move | None:
    """Put a thing, or a location, in the location `to` (None for nowhere), and
    write it down. Nothing when it is already there: the history is of things
    that happened.

    A location moved into itself, or into anything inside it, raises Refused. A
    location moved takes everything in it along by not being asked to: what is in
    Box 14 points at Box 14, so the one write here is the whole of the move, and it
    is recorded once, on the box (ADR-0034)."""
    t = t or tree(db)
    was = where_of(obj)
    if was == to:
        return None
    if isinstance(obj, Location):
        if t.would_loop(obj.asset_id, to):
            raise Refused(f"{obj.name} cannot go inside itself, or inside anything in it.")
        obj.parent_id = to
    else:
        obj.location_id = to
    from_path, to_path = t.text(was), t.text(to)
    if isinstance(obj, Location):
        t.rows[obj.asset_id] = (obj.name, obj.kind, to)
    line = add_log(db, obj.asset_id, sentence(from_path, to_path, how), MOVE_ENTRY)
    db.flush()
    row = Move(
        asset_id=obj.asset_id,
        from_id=was,
        from_path=from_path[:1024],
        to_id=to,
        to_path=to_path[:1024],
        moved_at=_now(),
        who=(who or "")[:64],
        how=how,
        log_id=line.id if line is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def kept_in(db: Session, tag: str) -> list[Thing]:
    """The machines and parts recorded in this location itself -- not in the
    locations inside it, and not the parts fitted in what is here, which go where
    their machine goes. Disposed things are not kept anywhere."""
    computers = (
        db.query(Computer)
        .filter(Computer.location_id == tag, Computer.disposed.is_(False))
        .order_by(Computer.asset_id)
        .all()
    )
    parts = (
        db.query(Part)
        .filter(Part.location_id == tag, Part.disposed.is_(False))
        .order_by(Part.asset_id)
        .all()
    )
    return [*computers, *parts]


def counts(db: Session, t: Tree) -> dict[str, int]:
    """How many things each location holds, all the way down: its own, and those
    of every location inside it. Two queries for the whole tree."""
    own: dict[str, int] = {}
    for model in (Computer, Part):
        for (tag,) in db.query(model.location_id).filter(
            model.location_id.isnot(None), model.disposed.is_(False)
        ):
            own[tag] = own.get(tag, 0) + 1
    return {tag: own.get(tag, 0) + sum(own.get(c, 0) for c in t.within(tag)) for tag in t.rows}


def empty(db: Session, tag: str, t: Tree) -> bool:
    """Nothing kept in it and no location inside it."""
    return not kept_in(db, tag) and not t.children(tag)


class Placed(NamedTuple):
    """Where a part is because of what it is fitted in, and whose answer that is.

    `whose` and `kind` are carried with the location because the page has to say
    where the answer came from. A location shown against a part that does not hold
    one would otherwise read as something somebody chose for it, and the first
    thing anybody would do about a wrong one is edit the part -- which is the one
    record that cannot fix it."""

    where: str
    whose: str
    kind: str


def inherited(db: Session) -> dict[str, Placed]:
    """Where each part is because of what it is fitted in, for the parts that do
    not say for themselves. Keyed by the part's asset id; `where` is a location's
    tag.

    A part's own answer is not in here: it is already in the column, and every
    reader of this map has that to hand. What is here is only the answer the part
    would have no way of giving -- which is why this is worked out and never
    written down. Storing it would mean rewriting a row of the parts table every
    time a machine was carried upstairs.

    Mounted on before installed in: a chip on a board is wherever the board is,
    and the board is the nearer answer even when the machine it is in has one of
    its own. The first location up the chain wins, and a chain that runs out yields
    nothing -- a part in a machine nobody has placed is a part nobody has placed.

    Two lean queries for the whole register rather than a walk per part, because
    every caller wants many at once: the gallery is building a card for each of
    them and the search is matching against each of them."""
    parts = {
        aid: (parent, computer, where)
        for aid, parent, computer, where in db.query(
            Part.asset_id, Part.parent_id, Part.computer_id, Part.location_id
        )
    }
    computers = dict(db.query(Computer.asset_id, Computer.location_id).tuples().all())

    def answer(aid: str, seen: frozenset[str]) -> Placed | None:
        # Nothing in the register should be able to build a part mounted on itself
        # -- the forms do not offer it -- but a walk that trusts that is a page that
        # never finishes loading if one ever exists, and the cost of not trusting it
        # is a set.
        if aid in seen:
            return None
        # One pool of asset ids across the whole register (ADR-0007), so an id is a
        # machine or a part and never both, and asking the two maps in turn cannot
        # land on the wrong thing.
        if aid in computers:
            where = computers[aid]
            return Placed(where, aid, "computers") if where else None
        row = parts.get(aid)
        if row is None:
            return None
        parent, computer, own = row
        if own:
            return Placed(own, aid, "parts")
        for up in (parent, computer):
            if up and (found := answer(up, seen | {aid})) is not None:
                return found
        return None

    out: dict[str, Placed] = {}
    for aid, (parent, computer, own) in parts.items():
        if own or not (parent or computer):
            continue
        if (found := answer(aid, frozenset())) is not None:
            out[aid] = found
    return out


def effective(obj: Thing, placed: Mapping[str, Placed]) -> str | None:
    """The location a thing is in: its own, or for a part with none, the one it
    inherits from what it is fitted in."""
    if obj.location_id:
        return obj.location_id
    found = placed.get(obj.asset_id) if isinstance(obj, Part) else None
    return found.where if found else None


def mounted_on(db: Session, aid: str) -> list[str]:
    """What a part is mounted on, nearest first: the card it is on, what that card
    is on, and so on up. Read upwards, which is the short way -- a part is on one
    thing and may carry many -- and safe against a loop an older version let in,
    for the reason `Tree.up` is. Uppercased, as every tag is compared: the table
    finds a tag in either case, and a link written in lower case is still a link."""
    out: list[str] = []
    at = db.query(Part.parent_id).filter(Part.asset_id == aid).scalar()
    while at and at.upper() != aid.upper() and at.upper() not in out:
        out.append(at.upper())
        at = db.query(Part.parent_id).filter(Part.asset_id == at).scalar()
    return out


def mount_refusal(db: Session, part: Part, host: str | None) -> str | None:
    """Why `part` cannot be mounted on `host`, in words, or None when it can.

    A part on itself, or on anything mounted on it however far down, would be its
    own host: a controller card on the drive that is on it, and two pages each
    saying the other is what it is on. Asked by everything that mounts one -- the
    mount button, the edit form, the API, an undo in the audit -- so that the rule
    is written once (MANUAL §1, "Two tables").

    Only a change is judged. Leaving a part where it is asks nothing new, so a pair
    an older version let mount each on the other can still be saved, and taken
    apart, rather than refusing every save until somebody edits the database."""
    if not host or host.upper() == (part.parent_id or "").upper():
        return None
    tag = part.asset_id.upper()
    if tag in (host.upper(), *mounted_on(db, host)):
        return f"{tag} cannot be mounted on itself, or on anything mounted on it."
    return None


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


def where_row(db: Session, obj: Thing, placed: Mapping[str, Placed], t: Tree) -> Where | None:
    """What the Location row on this item's page says, or None for no row."""
    borrowed = placed.get(obj.asset_id) if isinstance(obj, Part) and not obj.location_id else None
    tag = obj.location_id or (borrowed.where if borrowed else None)
    loc = db.get(Location, tag) if tag and tag in t else None
    if tag is None or loc is None:
        return None
    return Where(
        tag=tag,
        steps=t.steps(tag),
        whose=borrowed.whose if borrowed else "",
        kind=borrowed.kind if borrowed else "",
        notes=loc.notes or "",
        photo=loc.image or "",
        others=len([x for x in kept_in(db, tag) if x.asset_id != obj.asset_id]),
    )


def path_words(t: Tree, tags: Iterable[str | None]) -> str:
    """The names along each path, as one string for a haystack: what a search for
    `loft` has to find a thing three boxes down in the loft by."""
    return " ".join(" ".join(t.names(tag)) for tag in tags)


def empty_into_parent(db: Session, loc: Location, who: str, t: Tree) -> int:
    """Put everything in this location where the location itself is: its things and
    the locations inside it, one level up. Each is a move by edit, because each
    has changed where it is kept. Returns how many went."""
    up = loc.parent_id
    moved = 0
    for thing in kept_in(db, loc.asset_id):
        moved += move(db, thing, up, EDIT, who, t) is not None
    for tag in t.children(loc.asset_id):
        child = db.get(Location, tag)
        if child is not None:
            moved += move(db, child, up, EDIT, who, t) is not None
    return moved


def merge(db: Session, loc: Location, into: Location, who: str, t: Tree) -> list[str]:
    """Put one location's contents into another, which keeps its tag, and delete the
    first: two spellings of one crate made one (MANUAL §14). Refused for a location
    merged into itself or into anything inside it, which would put its own contents
    nowhere. Returns the photographs to delete once the rows are committed."""
    if into.asset_id == loc.asset_id or into.asset_id in t.within(loc.asset_id):
        raise Refused(f"{loc.name} cannot be merged into itself, or into anything in it.")
    for thing in kept_in(db, loc.asset_id):
        move(db, thing, into.asset_id, EDIT, who, t)
    for tag in t.children(loc.asset_id):
        child = db.get(Location, tag)
        if child is not None:
            move(db, child, into.asset_id, EDIT, who, t)
    add_log(db, into.asset_id, f"merged {loc.name} ({loc.asset_id}) into this")
    return forget(db, loc)


def forget(db: Session, loc: Location) -> list[str]:
    """Delete a location that holds nothing, with its own history and photographs.

    Not the moves of things that were once in it: those are on the things'
    histories, and stay there with the path as it read at the time. The photograph
    files are handed back rather than deleted here, because a file cannot be rolled
    back and the caller commits first."""
    from .models import LogEntry
    from .photos import _drop_log_photos, detect_images

    rels = detect_images("locations", loc.asset_id) + _drop_log_photos(db, loc.asset_id)
    db.query(LogEntry).filter(LogEntry.asset_id == loc.asset_id).delete(synchronize_session=False)
    db.query(Move).filter(Move.asset_id == loc.asset_id).delete(synchronize_session=False)
    db.delete(loc)
    db.flush()
    return rels


def label_row(loc: Location, t: Tree) -> dict[str, object]:
    """A location as its label reads it: the name, the path above it -- where the
    box was when the label was printed -- its kind and its notes."""
    return {
        "asset_id": loc.asset_id,
        "name": loc.name,
        "path": t.text(loc.parent_id),
        "kind": KIND_NAMES.get(loc.kind, loc.kind),
        "notes": loc.notes,
    }
