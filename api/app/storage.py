"""The audit: a round of scans, what each one did, and the report at the end
(MANUAL §14, "Audit"; ADR-0034). The code still calls it storage, its first name.

One rule covers putting away, moving and checking: scan a location and it is open,
scan a thing and it is put in the open location -- already there is found, anywhere
else is moved in, there and then. Everything else is a consequence of that rule
meeting the register: a thing scanned with nothing open is held until a location
is; a box scanned while a shelf is open is opened in its turn, or with *moving
boxes* on, put on the shelf; a card scanned into a drawer is taken out of its
machine, because it is not in the machine any more whatever the register said.

A round is rows in two tables, written as each scan arrives, so a phone locking in
the loft loses nothing. Its state is read off its scans rather than kept beside
them: the open location is the one the latest `opened` row names, and a thing
waiting for a location is a last row that says `held`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import entry, locations
from .common import to_dict
from .history import CHECK_ENTRY, add_log
from .ids import tag_in
from .models import (
    Computer,
    Location,
    LogEntry,
    Move,
    Part,
    Project,
    StockCheck,
    StockCheckScan,
)

# What a scan did. `opened` a location; `found` a thing (or a location inside the
# open one) already where it should be; `moved` a thing in, or with moving boxes on
# `nested` a location in; `held` a thing scanned with nothing open; `again` a thing
# already scanned in this round; `refused` everything that moved nothing. `closed`
# is no scan but change location, kept as a row like one because what is open is
# read off the round's rows, and a row is what says it was shut.
OPENED, FOUND, MOVED, NESTED, HELD, AGAIN, REFUSED, CLOSED = (
    "opened",
    "found",
    "moved",
    "nested",
    "held",
    "again",
    "refused",
    "closed",
)

# How each one is shown and heard (MANUAL §14, "Seeing and hearing what happened"):
# ok is one short high beep and a tick, moved two rising beeps and an arrow, refused
# a low buzz and a cross. The words say it as well, so nothing depends on the
# colour or on the sound being on.
TONES = {
    OPENED: "ok",
    FOUND: "ok",
    HELD: "ok",
    AGAIN: "ok",
    CLOSED: "ok",
    MOVED: "moved",
    NESTED: "moved",
    REFUSED: "refused",
}
ICONS = {"ok": "✓", "moved": "→", "refused": "✕"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def current(db: Session, user_id: int) -> StockCheck | None:
    """This person's round still open, if they have one."""
    return (
        db.query(StockCheck)
        .filter(StockCheck.user_id == user_id, StockCheck.finished_at.is_(None))
        .order_by(StockCheck.id.desc())
        .first()
    )


def round_for(db: Session, user_id: int) -> StockCheck:
    """The open round, or a new one: a round starts with its first scan."""
    found = current(db, user_id)
    if found is not None:
        return found
    made = StockCheck(user_id=user_id, started_at=_now())
    db.add(made)
    db.flush()
    return made


def scans(db: Session, check: StockCheck) -> list[StockCheckScan]:
    return (
        db.query(StockCheckScan)
        .filter(StockCheckScan.check_id == check.id)
        .order_by(StockCheckScan.id)
        .all()
    )


def open_location(rows: Sequence[StockCheckScan]) -> str | None:
    """The location a round has open: the one its latest `opened` scan names,
    unless change location has shut it since."""
    for row in reversed(rows):
        if row.result == OPENED:
            return row.at_id
        if row.result == CLOSED:
            return None
    return None


def _held(rows: Sequence[StockCheckScan]) -> StockCheckScan | None:
    """A thing waiting for a location: the round's last scan, when that held one."""
    return rows[-1] if rows and rows[-1].result == HELD else None


@dataclass
class Said:
    """What a scan did, as the panel says it."""

    tone: str
    head: str
    words: str
    open: str | None
    scan: int

    def as_dict(self) -> dict[str, object]:
        return {
            "tone": self.tone,
            "icon": ICONS[self.tone],
            "head": self.head,
            "words": self.words,
            "open": self.open,
            "scan": self.scan,
        }


def _name(thing: Computer | Part) -> str:
    return f"{entry.display_name(to_dict(thing))} ({thing.asset_id})"


def _expected(db: Session, tag: str, t: locations.Tree) -> str:
    """What the register expects to find in a location, in words."""
    things = len(locations.kept_in(db, tag))
    inside = len(t.children(tag))
    if not things and not inside:
        return "Empty"
    said = [f"{things} thing{'' if things == 1 else 's'} expected here"]
    if inside:
        said.append(f"{inside} location{'' if inside == 1 else 's'} inside")
    return ", ".join(said)


def _record(
    db: Session,
    check: StockCheck,
    code: str,
    result: str,
    asset_id: str | None = None,
    at_id: str | None = None,
    said: str = "",
    move: Move | None = None,
    was_computer: str | None = None,
    was_parent: str | None = None,
) -> StockCheckScan:
    row = StockCheckScan(
        check_id=check.id,
        scanned_at=_now(),
        code=code[:255],
        asset_id=asset_id,
        at_id=at_id,
        result=result,
        said=said[:255],
        move_id=move.id if move is not None else None,
        was_computer=was_computer,
        was_parent=was_parent,
    )
    db.add(row)
    db.flush()
    return row


def _refuse(db: Session, check: StockCheck, code: str, reason: str, opened: str | None) -> Said:
    row = _record(db, check, code, REFUSED, said=reason, at_id=opened)
    return Said("refused", "Not recognised", reason, opened, row.id)


def _say(row: StockCheckScan, head: str, words: str, opened: str | None) -> Said:
    """What a scan said, written on its row as well as answered."""
    row.said = words[:255]
    return Said(TONES[row.result], head, words, opened, row.id)


def close(db: Session, check: StockCheck, t: locations.Tree) -> Said:
    """Change location: shut the open one without opening another, so that a thing
    scanned before the next location is held rather than moved into the last
    (MANUAL §14). The report is not changed by it: that reads what a round opened,
    and not what it still has open."""
    opened = open_location(scans(db, check))
    row = _record(db, check, "", CLOSED, asset_id=opened, at_id=opened)
    name = t.rows[opened][0] if opened is not None and opened in t else ""
    return _say(row, "Closed", name or "No location was open.", None)


def _put(
    db: Session,
    check: StockCheck,
    code: str,
    thing: Computer | Part,
    to: str,
    who: str,
    t: locations.Tree,
) -> tuple[StockCheckScan, str]:
    """Move a thing into a location by scan, taking a fitted part out of what it is
    fitted in. The scan row it is recorded on, and the words."""
    was_computer = was_parent = None
    taken = ""
    if isinstance(thing, Part) and (thing.computer_id or thing.parent_id):
        was_computer, was_parent = thing.computer_id, thing.parent_id
        host = was_parent or was_computer
        thing.computer_id = None
        thing.parent_id = None
        add_log(db, thing.asset_id, f"taken out of {host}, by scan")
        add_log(db, host, f"{thing.asset_id} taken out, by scan")
        taken = f"; taken out of {host}"
    from_path = t.text(thing.location_id)
    move = locations.move(db, thing, to, locations.SCAN, who, t)
    row = _record(
        db,
        check,
        code,
        MOVED,
        asset_id=thing.asset_id,
        at_id=to,
        move=move,
        was_computer=was_computer,
        was_parent=was_parent,
    )
    return row, f"{_name(thing)} moved in from {from_path or 'nowhere recorded'}{taken}"


def scan(db: Session, check: StockCheck, code: str, boxes: bool, who: str) -> Said:
    """Act on one scan, record it, and say what it did. The caller commits."""
    rows = scans(db, check)
    opened = open_location(rows)
    t = locations.tree(db)
    typed = (code or "").strip()
    tag = tag_in(typed)
    if tag is None:
        return _refuse(db, check, typed, f"Not a tag in this register: {typed}", opened)

    loc = db.get(Location, tag)
    if loc is not None:
        if boxes and opened and tag != opened:
            return _nest(db, check, typed, loc, opened, who, t)
        return _open(db, check, typed, loc, opened, rows, who, t)

    thing: Computer | Part | None = db.get(Computer, tag) or db.get(Part, tag)
    if thing is None:
        if db.get(Project, tag) is not None:
            return _refuse(
                db,
                check,
                typed,
                f"{tag} is a project, which is work and is not kept anywhere.",
                opened,
            )
        return _refuse(db, check, typed, f"Not a tag in this register: {typed}", opened)
    if thing.disposed:
        when = f" on {thing.disposed_at}" if thing.disposed_at else ""
        return _refuse(db, check, typed, f"{_name(thing)} was disposed of{when}.", opened)

    if opened is None:
        placed = locations.inherited(db)
        now = locations.effective(thing, placed)
        here = f"is in {t.text(now)}" if now else "is nowhere recorded"
        row = _record(db, check, typed, HELD, asset_id=tag)
        return _say(
            row, "Where it is", f"{_name(thing)} {here} — scan a location to move it there.", None
        )

    if any(
        r.asset_id == tag and r.at_id == opened and r.result in (FOUND, MOVED) and not r.undone
        for r in rows
    ):
        row = _record(db, check, typed, AGAIN, asset_id=tag, at_id=opened)
        return _say(row, "Already scanned", f"{_name(thing)} is scanned already.", opened)

    placed = {} if thing.location_id else locations.inherited(db)
    if locations.effective(thing, placed) == opened:
        row = _record(db, check, typed, FOUND, asset_id=tag, at_id=opened)
        return _say(row, "Found", f"{_name(thing)} is here.", opened)

    row, words = _put(db, check, typed, thing, opened, who, t)
    return _say(row, "Moved in", words, opened)


def _open(
    db: Session,
    check: StockCheck,
    typed: str,
    loc: Location,
    opened: str | None,
    rows: Sequence[StockCheckScan],
    who: str,
    t: locations.Tree,
) -> Said:
    """A location scanned with moving boxes off: it becomes the open one -- found on
    the way, if the register has it in the one that was open, and taking with it a
    thing that was held."""
    said = []
    if opened and loc.parent_id == opened and opened != loc.asset_id:
        found = _record(db, check, typed, FOUND, asset_id=loc.asset_id, at_id=opened)
        found.said = f"{loc.name} ({loc.asset_id}) is here."
        said.append(f"Found on {t.rows[opened][0]}.")
    held = _held(rows)
    if held is not None and held.asset_id:
        thing: Computer | Part | None = db.get(Computer, held.asset_id) or db.get(
            Part, held.asset_id
        )
        if thing is not None:
            moved, words = _put(db, check, held.code, thing, loc.asset_id, who, t)
            moved.said = words[:255]
            said.append(words + ".")
    row = _record(db, check, typed, OPENED, asset_id=loc.asset_id, at_id=loc.asset_id)
    words = f"{t.text(loc.asset_id)} — {_expected(db, loc.asset_id, t)}"
    if said:
        words += " " + " ".join(said)
    return _say(row, loc.name, words, loc.asset_id)


def _nest(
    db: Session,
    check: StockCheck,
    typed: str,
    loc: Location,
    opened: str,
    who: str,
    t: locations.Tree,
) -> Said:
    """A location scanned with moving boxes on: it goes inside the open one, with
    everything in it."""
    if loc.parent_id == opened:
        row = _record(db, check, typed, FOUND, asset_id=loc.asset_id, at_id=opened)
        return _say(row, "Found", f"{loc.name} ({loc.asset_id}) is here.", opened)
    from_path = t.text(loc.parent_id)
    try:
        move = locations.move(db, loc, opened, locations.SCAN, who, t)
    except locations.Refused as err:
        return _refuse(db, check, typed, str(err), opened)
    came = locations.counts(db, t).get(loc.asset_id, 0)
    row = _record(db, check, typed, NESTED, asset_id=loc.asset_id, at_id=opened, move=move)
    return _say(
        row,
        "Moved in",
        f"{loc.name} ({loc.asset_id}) moved in from {from_path or 'the top'}; "
        f"{came} thing{'' if came == 1 else 's'} came with it.",
        opened,
    )


def undo(db: Session, check: StockCheck, scan_id: int, who: str) -> Said | None:
    """Put back what one scan moved -- back in its machine too, if it was taken out
    of one -- recorded as a move back rather than wiped out. None for a scan that
    moved nothing, or one already undone."""
    row = db.get(StockCheckScan, scan_id)
    if row is None or row.check_id != check.id or row.undone or row.result not in (MOVED, NESTED):
        return None
    if row.asset_id is None:
        return None
    move = db.get(Move, row.move_id) if row.move_id else None
    back = move.from_id if move is not None else None
    t = locations.tree(db)
    obj: Computer | Part | Location | None
    if row.result == NESTED:
        obj = db.get(Location, row.asset_id)
    else:
        obj = db.get(Computer, row.asset_id) or db.get(Part, row.asset_id)
    if obj is None:
        return None
    locations.move(db, obj, back, locations.UNDO, who, t)
    if isinstance(obj, Part) and (row.was_computer or row.was_parent):
        obj.computer_id, obj.parent_id = row.was_computer, row.was_parent
        host = row.was_parent or row.was_computer
        add_log(db, obj.asset_id, f"put back in {host}, undoing a scan")
        if host:
            add_log(db, host, f"{obj.asset_id} put back, undoing a scan")
    row.undone = True
    name = obj.name if isinstance(obj, Location) else _name(obj)
    return Said(
        "ok",
        "Undone",
        f"{name} is back in {t.text(back) or 'nowhere recorded'}.",
        open_location(scans(db, check)),
        row.id,
    )


def finish(check: StockCheck) -> None:
    check.finished_at = _now()


@dataclass
class Checked:
    """One location's part of a report."""

    tag: str
    path: str
    found: list[str]
    moved: list[tuple[str, str]]
    unscanned: list[str]


def report(db: Session, check: StockCheck) -> tuple[list[Checked], list[StockCheckScan]]:
    """For each location the round opened: what was found, what moved in and from
    where, and what the register says is there that was not scanned -- and every
    scan that was not recognised.

    What was not scanned is read from where things are now, less what the round
    scanned: a thing expected on the shelf and scanned into the box beside it is in
    the box, and not missing from the shelf."""
    rows = scans(db, check)
    t = locations.tree(db)
    out: list[Checked] = []
    for tag in dict.fromkeys(r.at_id for r in rows if r.result == OPENED and r.at_id):
        here = [r for r in rows if r.at_id == tag and not r.undone]
        found = [r.asset_id for r in here if r.result == FOUND and r.asset_id]
        moved = []
        for r in here:
            if r.result in (MOVED, NESTED) and r.asset_id:
                m = db.get(Move, r.move_id) if r.move_id else None
                moved.append((r.asset_id, (m.from_path if m else "") or "nowhere recorded"))
        scanned = {r.asset_id for r in rows if r.asset_id}
        expected = [x.asset_id for x in locations.kept_in(db, tag)] + t.children(tag)
        out.append(
            Checked(
                tag=tag,
                path=t.text(tag),
                found=list(dict.fromkeys(found)),
                moved=moved,
                unscanned=[a for a in expected if a not in scanned],
            )
        )
    return out, [r for r in rows if r.result == REFUSED]


def record_missing(db: Session, check: StockCheck) -> int:
    """Write on each thing not scanned that it was not found at the check of that
    location on that date. Only when asked: a round that put three things on a shelf
    has not checked the other forty. Returns how many lines were written."""
    checked, _ = report(db, check)
    day = (check.finished_at or _now()).date().isoformat()
    n = 0
    for part in checked:
        for aid in part.unscanned:
            if db.get(Location, aid) is not None:
                continue
            said = f"not found at the check of {part.path} ({part.tag}) on {day}"
            # Pressed twice, it is still one finding: the line is written once.
            already = (
                db.query(LogEntry)
                .filter(
                    LogEntry.asset_id == aid,
                    LogEntry.kind == CHECK_ENTRY,
                    LogEntry.message == said,
                )
                .count()
            )
            if not already:
                add_log(db, aid, said, CHECK_ENTRY)
                n += 1
    return n
