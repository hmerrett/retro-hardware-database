"""The one tree everything in the register is in (ADR-0036): what a thing is inside,
what is inside it, the chain up, which kinds may hold which, the loop check, and
moving something and writing the move down.

Every machine, part, location and project is a row of the register, and a row knows
one thing about where it is: `inside_id`, the thing it is directly inside. A box is
on a shelf, a machine is in the box, a card is in the machine, a drive is on the
card, and each knows only the next one up. So carrying the box to the workshop is
one write, to the box, and everything in it is in the workshop at that moment --
which is the reason nothing further down is ever told, and the reason a path is
read up the links when it is shown and never stored.

What a link means is read off what holds it. In a location is *kept*, in a machine
is *fitted*, on a part is *mounted*, and the difference still matters where it
matters: a machine's parts are part of the machine, so they go when it is disposed
of or deleted, and a box's contents are not part of the box (disposal.py,
assets.py). Here a link is a link.

The register is hundreds of rows, not millions, so a request that needs the tree
reads all of it in one query (`load`) and walks it in memory; a move keeps that copy
current, so the next question in the same request is answered from it.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .history import MOVE_ENTRY, add_log
from .models import Computer, Gone, Location, Move, Part, Thing
from .web import templates

COMPUTER, PART, LOCATION, PROJECT, DELETED = "computer", "part", "location", "project", "deleted"

# What may be inside what (ADR-0036): each kind that can hold anything, and the kinds
# it can hold. The one list of pairs, so a pair added later -- a machine inside a
# machine, a carry case that holds things -- is a line here rather than a column.
# A project is work, not an object: it holds nothing and is inside nothing.
HOLDS: dict[str, frozenset[str]] = {
    LOCATION: frozenset({LOCATION, COMPUTER, PART}),
    COMPUTER: frozenset({PART}),
    PART: frozenset({PART}),
}

# What a thing is called when the register explains itself in a refusal.
CALLED = {COMPUTER: "a machine", PART: "a part", LOCATION: "a location", PROJECT: "a project"}

# How a thing is in what holds it.
KEPT, FITTED, MOUNTED = "kept", "fitted", "mounted"
HELD = {LOCATION: KEPT, COMPUTER: FITTED, PART: MOUNTED}

# How a move was made, as the history says it.
EDIT, SCAN, API, UNDO = "edit", "scan", "api", "undo"
HOW_WORDS = {
    EDIT: "by edit",
    SCAN: "by scan",
    API: "through the API",
    UNDO: "undone in the audit",
}

# How a path is written where it is text -- a move's ends, the API, a label.
SEP = " / "

# For the history panel, which draws a move from its row.
templates.env.globals["move_how"] = HOW_WORDS

type Item = Computer | Part
type Movable = Computer | Part | Location


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Refused(ValueError):
    """What was asked cannot be done, and why, in words for a form or a scan.
    Raised rather than returned, so a caller that forgets to check cannot store the
    wrong answer."""


@dataclass
class Tree:
    """Every tag in the register still standing, read once: {tag: (what, inside)}.

    One dict, so a page that wants forty answers asks the database once. A deleted
    thing's row is not in it: its tag is taken, and nothing is inside it."""

    rows: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    _inside: dict[str, list[str]] | None = None

    def __contains__(self, tag: object) -> bool:
        return tag in self.rows

    def what(self, tag: str | None) -> str | None:
        return self.rows[tag][0] if tag in self.rows else None

    def holder(self, tag: str | None) -> str | None:
        """What `tag` is directly inside, or None."""
        return self.rows[tag][1] if tag in self.rows else None

    def up(self, tag: str | None) -> list[str]:
        """Everything `tag` is inside, nearest first, not itself.

        Safe against a loop nothing in the app can build: a walk that trusts that is
        a page that never finishes loading if one ever exists, and the cost of not
        trusting it is a set."""
        out: list[str] = []
        seen = {tag}
        at = self.holder(tag)
        while at and at in self.rows and at not in seen:
            seen.add(at)
            out.append(at)
            at = self.holder(at)
        return out

    def children(self, tag: str) -> list[str]:
        """What is directly inside `tag`, in tag order."""
        if self._inside is None:
            self._inside = {}
            for one, (_what, holder) in self.rows.items():
                if holder:
                    self._inside.setdefault(holder, []).append(one)
        return sorted(self._inside.get(tag, ()))

    def within(self, tag: str) -> list[str]:
        """Everything inside `tag`, however far down, nearest first; not itself."""
        out: list[str] = []
        seen = {tag}
        todo = [tag]
        while todo:
            for child in self.children(todo.pop(0)):
                if child not in seen:
                    seen.add(child)
                    out.append(child)
                    todo.append(child)
        return out

    def place(self, tag: str | None) -> str | None:
        """The location a thing is kept in: the first location up its chain. For a
        location, the one it is inside."""
        return next((up for up in self.up(tag) if self.what(up) == LOCATION), None)

    def machine(self, tag: str | None) -> str | None:
        """The machine a part is in, however far down: the nearest machine up its
        chain, without crossing a location -- a card on a shelf is not in the
        machine on the shelf."""
        for up in self.up(tag):
            what = self.what(up)
            if what == COMPUTER:
                return up
            if what != PART:
                return None
        return None

    def outermost(self, tag: str) -> str:
        """The outermost machine or part `tag` is in, or `tag` itself: the one whose
        Visible tick says whether a visitor is told where it is kept, since a card is
        on whatever shelf its machine is on."""
        out = tag
        for up in self.up(tag):
            if self.what(up) not in (COMPUTER, PART):
                break
            out = up
        return out

    def would_loop(self, tag: str, into: str | None) -> bool:
        """Whether putting `tag` inside `into` would put it inside itself."""
        return into is not None and (into == tag or tag in self.up(into))

    def moved(self, tag: str, into: str | None) -> None:
        """Keep this copy true after a move, for the rest of the request."""
        self.rows[tag] = (self.rows[tag][0] if tag in self.rows else "", into)
        self._inside = None


def load(db: Session) -> Tree:
    return Tree(
        {
            aid: (what, inside.upper() if inside else None)
            for aid, what, inside in db.query(Thing.asset_id, Thing.what, Thing.inside_id)
            if what != DELETED
        }
    )


def item(db: Session, tag: str | None) -> Item | None:
    """The machine or part a tag names, or None."""
    if not tag:
        return None
    found = db.get(Thing, tag.upper())
    return found if isinstance(found, Computer | Part) else None


def named(db: Session, tag: str) -> str:
    """A thing as a move's end reads it: a location by its name, a machine or a part
    by its name and its tag, since two Amiga 500s are told apart by nothing else."""
    from . import entry
    from .common import to_dict

    found = db.get(Thing, tag)
    if isinstance(found, Location):
        return found.name or tag
    if isinstance(found, Computer | Part):
        return f"{entry.display_name(to_dict(found))} ({tag})"
    return tag


def words(db: Session, t: Tree, tag: str | None) -> str:
    """Where `tag` is, as words from the top down, ending with it: `Workshop / Box 14
    / Amiga 500 (RH-0042)`, or "" for nowhere."""
    if not tag:
        return ""
    return SEP.join(named(db, step) for step in [*reversed(t.up(tag)), tag])


def sentence(from_path: str, to_path: str, how: str) -> str:
    """A move as words, for the API's log and anywhere a move is read without its
    row. The page draws the row instead, with a link at each end."""
    was = from_path or "nowhere recorded"
    now = to_path or "nowhere recorded"
    return f"moved from {was} to {now}, {HOW_WORDS[how]}"


def refusal(db: Session, t: Tree, tag: str, what: str, into: str | None) -> str | None:
    """Why the thing `tag` -- a `what` -- cannot go inside `into`, in words, or None
    when it can. Nowhere is always allowed."""
    if into is None:
        return None
    holder = t.what(into)
    if holder is None:
        return f"Nothing in the register has the tag {into}."
    if what not in HOLDS.get(holder, frozenset()):
        if holder == PROJECT:
            return f"{into} is a project, which is work and holds nothing."
        return f"{CALLED[what].capitalize()} cannot go inside {CALLED[holder]}."
    if t.would_loop(tag, into):
        if holder == PART:
            return f"{tag} cannot be mounted on itself, or on anything mounted on it."
        return f"{tag} cannot go inside itself, or inside anything inside it."
    found = item(db, into)
    if found is not None and found.disposed:
        return f"{into} has been disposed of, so nothing can go inside it."
    return None


def put(
    db: Session, thing: Movable, into: str | None, how: str, who: str, t: Tree | None = None
) -> Move | None:
    """Put a thing inside another, or nowhere, and write it down. Nothing when it is
    already there: the history is of things that happened.

    The one way anything is moved -- kept, fitted, mounted, taken out -- so the pairs,
    the loop and disposal are each checked in one place (`refusal`), and a refusal
    is raised as Refused. What is inside the thing comes with it by not being asked
    to, and the move is recorded once, on the thing (ADR-0034, ADR-0036).

    A machine or a part that something goes into or comes out of gets a line of its
    own, as it always has: its parts are part of it, where a box's contents are not
    the box's business."""
    t = t or load(db)
    tag = thing.asset_id.upper()
    into = into.upper() if into else None
    was = thing.inside_id.upper() if thing.inside_id else None
    if was == into:
        return None
    if (why := refusal(db, t, tag, thing.what, into)) is not None:
        raise Refused(why)
    from_path, to_path = words(db, t, was), words(db, t, into)
    thing.inside_id = into
    t.moved(tag, into)
    line = add_log(db, tag, sentence(from_path, to_path, how), MOVE_ENTRY)
    if t.what(was) in (COMPUTER, PART):
        add_log(db, was, f"{tag} taken out" if t.what(was) == COMPUTER else f"{tag} taken off")
    if t.what(into) in (COMPUTER, PART):
        add_log(db, into, f"{HELD[t.what(into) or PART]} {tag}")
    db.flush()
    row = Move(
        asset_id=tag,
        from_id=was,
        from_path=from_path[:1024],
        to_id=into,
        to_path=to_path[:1024],
        moved_at=_now(),
        who=(who or "")[:64],
        how=how,
        log_id=line.id if line is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def contents(db: Session, t: Tree, tag: str) -> Iterator[Movable]:
    """What is directly inside `tag`, as rows."""
    for child in t.children(tag):
        found = db.get(Thing, child)
        if isinstance(found, Computer | Part | Location):
            yield found


def bury(db: Session, thing: Thing) -> None:
    """Delete a thing and keep its tag (ADR-0036). Its rows go, and its place in the
    register is taken by a `Gone` under the same tag, so the tag is never issued
    again: a label outlives the record it was printed for, and must never open
    somebody else's thing. Whatever was inside it is the caller's to have dealt
    with first; the key would leave it nowhere, without a word in its history."""
    tag = thing.asset_id
    db.delete(thing)
    db.flush()
    db.add(Gone(asset_id=tag))
    db.flush()


def mounted_on(r: Tree, root: str, below: list[Part]) -> dict[str, list[Part]]:
    """{card: [what is directly on it]} for everything inside `root` that is mounted
    on another part rather than fitted in it: what a parts list draws under each
    card, so a drive on its controller is in the machine's list, on its card."""
    out: dict[str, list[Part]] = {}
    for p in below:
        holder = r.holder(p.asset_id.upper())
        if holder and holder != root.upper():
            out.setdefault(holder, []).append(p)
    return out
