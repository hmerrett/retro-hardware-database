"""The audit: a round of scans, what each one did, and the report at the end
(MANUAL §14, "Audit"; ADR-0034, ADR-0036). The code still calls it storage, its
first name.

One rule covers putting away, moving, fitting and checking: the first scan opens a
location or a machine, and everything scanned after it goes into it -- a part, a
machine, a box -- until **next** closes it. Something already anywhere inside it is
found; anything else is moved in, there and then, by tree.put, which refuses what
the register's pairs, its loop rule or a disposal forbid. A part scanned with
nothing open says where it is and moves nothing. There used to be more -- a thing
held until a location arrived, a box ticked off and opened by one scan, a switch for
moving boxes -- and each was a special case of this rule, which is the reason they
went: a rule with special cases is one nobody can predict with a scanner in one
hand.

A round is rows in two tables, written as each scan arrives, so a phone locking in
the loft loses nothing. Its state is read off its scans rather than kept beside
them: what is open is what the latest `opened` row names, unless a `closed` row --
**next** -- came after it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import entry, tree
from .common import to_dict
from .history import CHECK_ENTRY, add_log
from .ids import tag_in
from .models import (
    Computer,
    Gone,
    Location,
    LogEntry,
    Move,
    Part,
    Project,
    StockCheck,
    StockCheckScan,
    Thing,
)

# What a scan did. `opened` a location or a machine; `found` a thing already inside
# what is open; `moved` a thing in, `nested` a location in; `where` a part scanned
# with nothing open, which says where it is and moves nothing; `again` a thing
# already scanned in this round; `refused` everything that moved nothing. `closed`
# is no scan but **next**, kept as a row like one because what is open is read off
# the round's rows, and a row is what says it was shut. `held` is a round's from
# before ADR-0036, read back and never written.
OPENED, FOUND, MOVED, NESTED, WHERE, HELD, AGAIN, REFUSED, CLOSED = (
    "opened",
    "found",
    "moved",
    "nested",
    "where",
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
    WHERE: "ok",
    HELD: "ok",
    AGAIN: "ok",
    CLOSED: "ok",
    MOVED: "moved",
    NESTED: "moved",
    REFUSED: "refused",
}
ICONS = {"ok": "✓", "moved": "→", "refused": "✕"}

# What can be opened: what holds things a scanner is pointed at -- a place, and a
# machine with its case off. A part holding a drive is mounted on its page.
OPENABLE = (tree.LOCATION, tree.COMPUTER)


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
    """What a round has open -- a location or a machine: what its latest `opened`
    scan names, unless **next** has shut it since."""
    for row in reversed(rows):
        if row.result == OPENED:
            return row.at_id
        if row.result == CLOSED:
            return None
    return None


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


def name_of(thing: Thing) -> str:
    """A thing as the panel names it: a location by its name, a machine or a part by
    its name and its tag."""
    if isinstance(thing, Location):
        return f"{thing.name} ({thing.asset_id})"
    if isinstance(thing, Computer | Part):
        return f"{entry.display_name(to_dict(thing))} ({thing.asset_id})"
    return thing.asset_id


def _inside_now(r: tree.Tree, tag: str) -> list[str]:
    """What is directly inside something, and still in the collection: what a round
    expects to find when it opens it."""
    return r.children(tag)


def _expected(db: Session, r: tree.Tree, tag: str) -> str:
    """What the register expects to find in what was just opened, in words."""
    held = [c for c in _inside_now(r, tag) if _live(db, c)]
    things = [c for c in held if r.what(c) != tree.LOCATION]
    inside = [c for c in held if r.what(c) == tree.LOCATION]
    if not things and not inside:
        return "Empty"
    noun = "part" if r.what(tag) == tree.COMPUTER else "thing"
    said = [f"{len(things)} {noun}{'' if len(things) == 1 else 's'} expected here"]
    if inside:
        said.append(f"{len(inside)} location{'' if len(inside) == 1 else 's'} inside")
    return ", ".join(said)


def _live(db: Session, tag: str) -> bool:
    """Not disposed of: a disposed thing is not kept anywhere, so nobody expects to
    find it."""
    found = tree.item(db, tag)
    return found is None or not found.disposed


def _record(
    db: Session,
    check: StockCheck,
    code: str,
    result: str,
    asset_id: str | None = None,
    at_id: str | None = None,
    said: str = "",
    move: Move | None = None,
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


def close(db: Session, check: StockCheck) -> Said:
    """**next**: shut what is open without opening anything, so the next scan opens
    whatever it is (MANUAL §14). The report is not changed by it: that reads what a
    round opened, and not what it still has open."""
    opened = open_location(scans(db, check))
    row = _record(db, check, "", CLOSED, asset_id=opened, at_id=opened)
    found = db.get(Thing, opened) if opened else None
    return _say(row, "Next", f"{name_of(found)} closed." if found else "Nothing was open.", None)


def _open(db: Session, check: StockCheck, typed: str, thing: Thing, r: tree.Tree) -> Said:
    """A location or a machine scanned with nothing open: it is open now."""
    tag = thing.asset_id.upper()
    row = _record(db, check, typed, OPENED, asset_id=tag, at_id=tag)
    words = f"{tree.words(db, r, tag)} — {_expected(db, r, tag)}"
    head = thing.name if isinstance(thing, Location) else name_of(thing)
    return _say(row, head, words, tag)


def _where(db: Session, check: StockCheck, typed: str, thing: Thing, r: tree.Tree) -> Said:
    """A part scanned with nothing open: where it is, and nothing moves."""
    tag = thing.asset_id.upper()
    here = tree.words(db, r, r.holder(tag))
    row = _record(db, check, typed, WHERE, asset_id=tag)
    said = f"{name_of(thing)} is in {here}." if here else f"{name_of(thing)} is nowhere recorded."
    return _say(
        row, "Where it is", f"{said} Scan a location or a machine first to put it in one.", None
    )


def _put(
    db: Session,
    check: StockCheck,
    typed: str,
    thing: Computer | Part | Location,
    opened: str,
    who: str,
    r: tree.Tree,
) -> Said:
    """Move what was scanned into what is open, taking it out of whatever it was in:
    a card scanned into a drawer is not in its machine any more, whatever the
    register said, and a card scanned into a machine is not in its box."""
    tag = thing.asset_id.upper()
    was = r.holder(tag)
    from_words = tree.words(db, r, was)
    came = [x for x in r.within(tag) if r.what(x) in (tree.COMPUTER, tree.PART)]
    try:
        move = tree.put(db, thing, opened, tree.SCAN, who, r)
    except tree.Refused as err:
        return _refuse(db, check, typed, str(err), opened)
    result = NESTED if isinstance(thing, Location) else MOVED
    row = _record(db, check, typed, result, asset_id=tag, at_id=opened, move=move)
    words = f"{name_of(thing)} moved in from {from_words or 'nowhere recorded'}"
    if r.what(was) in (tree.COMPUTER, tree.PART):
        words += f"; taken out of {was}"
    if came:
        words += f"; {len(came)} thing{'' if len(came) == 1 else 's'} came with it"
    return _say(row, "Moved in", words + ".", opened)


def scan(db: Session, check: StockCheck, code: str, who: str) -> Said:
    """Act on one scan, record it, and say what it did. The caller commits."""
    rows = scans(db, check)
    opened = open_location(rows)
    typed = (code or "").strip()
    tag = tag_in(typed)
    if tag is None:
        return _refuse(db, check, typed, f"Not a tag in this register: {typed}", opened)
    thing = db.get(Thing, tag)
    if thing is None or isinstance(thing, Gone):
        return _refuse(db, check, typed, f"Not a tag in this register: {typed}", opened)
    if isinstance(thing, Project):
        return _refuse(
            db, check, typed, f"{tag} is a project, which is work and is not kept anywhere.", opened
        )
    if isinstance(thing, Computer | Part) and thing.disposed:
        when = f" on {thing.disposed_at}" if thing.disposed_at else ""
        return _refuse(db, check, typed, f"{name_of(thing)} was disposed of{when}.", opened)
    r = tree.load(db)

    if opened is None:
        if thing.what in OPENABLE:
            return _open(db, check, typed, thing, r)
        return _where(db, check, typed, thing, r)

    if tag == opened.upper():
        row = _record(db, check, typed, AGAIN, asset_id=tag, at_id=opened)
        return _say(row, "Already open", f"{name_of(thing)} is open.", opened)
    if any(
        x.asset_id == tag
        and x.at_id == opened
        and x.result in (FOUND, MOVED, NESTED)
        and not x.undone
        for x in rows
    ):
        row = _record(db, check, typed, AGAIN, asset_id=tag, at_id=opened)
        return _say(row, "Already scanned", f"{name_of(thing)} is scanned already.", opened)
    # Anywhere inside what is open is found, however far down: a card in a machine on
    # the shelf is on the shelf, and the machine is where it should be.
    if opened.upper() in r.up(tag):
        row = _record(db, check, typed, FOUND, asset_id=tag, at_id=opened)
        return _say(row, "Found", f"{name_of(thing)} is here.", opened)
    if not isinstance(thing, Computer | Part | Location):
        return _refuse(db, check, typed, f"Not a tag in this register: {typed}", opened)
    return _put(db, check, typed, thing, opened, who, r)


def undo(db: Session, check: StockCheck, scan_id: int, who: str) -> Said | None:
    """Put back what one scan moved -- into the machine it was taken out of as
    readily as onto its shelf, since the move says which -- recorded as a move back
    rather than wiped out. None for a scan that moved nothing, or one already undone;
    a refusal, and nothing moved, where what it came out of has since been deleted
    or disposed of."""
    row = db.get(StockCheckScan, scan_id)
    if row is None or row.check_id != check.id or row.undone or row.result not in (MOVED, NESTED):
        return None
    if row.asset_id is None:
        return None
    obj = db.get(Thing, row.asset_id)
    if not isinstance(obj, Computer | Part | Location):
        return None
    move = db.get(Move, row.move_id) if row.move_id else None
    back = move.from_id.upper() if move is not None and move.from_id else None
    r = tree.load(db)
    opened = open_location(scans(db, check))
    if back is not None and back not in r:
        return Said(
            "refused",
            "Not undone",
            f"{back} has been deleted, so there is nothing to put {row.asset_id} back in.",
            opened,
            row.id,
        )
    try:
        tree.put(db, obj, back, tree.UNDO, who, r)
    except tree.Refused as err:
        return Said("refused", "Not undone", str(err), opened, row.id)
    row.undone = True
    return Said(
        "ok",
        "Undone",
        f"{name_of(obj)} is back in {tree.words(db, r, back) or 'nowhere recorded'}.",
        opened,
        row.id,
    )


def finish(check: StockCheck) -> None:
    check.finished_at = _now()


@dataclass
class Checked:
    """One location's or machine's part of a report."""

    tag: str
    path: str
    found: list[str]
    moved: list[tuple[str, str]]
    unscanned: list[str]


def report(db: Session, check: StockCheck) -> tuple[list[Checked], list[StockCheckScan]]:
    """For each location and machine the round opened: what was found, what moved in
    and from where, and what the register says is directly inside it that was not
    scanned -- and every scan that was not recognised.

    What was not scanned is read from where things are now, less what the round
    scanned: a thing expected on the shelf and scanned into the box beside it is in
    the box, and not missing from the shelf. Only what is directly inside counts as
    expected: nobody checking a shelf is asked to scan every SIMM in every machine on
    it."""
    rows = scans(db, check)
    r = tree.load(db)
    out: list[Checked] = []
    for tag in dict.fromkeys(x.at_id for x in rows if x.result == OPENED and x.at_id):
        here = [x for x in rows if x.at_id == tag and not x.undone]
        found = [x.asset_id for x in here if x.result == FOUND and x.asset_id]
        moved = []
        for x in here:
            if x.result in (MOVED, NESTED) and x.asset_id:
                m = db.get(Move, x.move_id) if x.move_id else None
                moved.append((x.asset_id, (m.from_path if m else "") or "nowhere recorded"))
        scanned = {x.asset_id for x in rows if x.asset_id}
        expected = [c for c in _inside_now(r, tag.upper()) if _live(db, c)]
        out.append(
            Checked(
                tag=tag,
                path=tree.words(db, r, tag.upper()),
                found=list(dict.fromkeys(found)),
                moved=moved,
                unscanned=[a for a in expected if a not in scanned],
            )
        )
    return out, [x for x in rows if x.result == REFUSED]


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
