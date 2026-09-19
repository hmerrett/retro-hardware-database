"""The queue of labels waiting for a printer that is somewhere else.

The register is a server and the label printers are on a desk behind a broadband
router, so nothing here ever opens a connection to a printer. An agent on that
desk asks whether there is anything for it, fetches the label and says how it went
(ADR-0025). This module is what it is asking.

Three things live here: who the agents are, which is read from the environment;
the queue itself, which is a handful of operations on one table; and the bytes of
a label, rendered when the agent asks for them rather than when the job was made.
"""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import labels, specdb
from .common import to_dict
from .models import Computer, Part, PrintJob, Project

# How long an agent holds a job before it goes back on the queue. Long enough that
# a label which is simply slow to print is not printed twice, short enough that a
# rebooted Pi does not leave somebody waiting: a claim is a lease, not a receipt.
LEASE_SECONDS = 300

# How long a finished job is kept. The queue is a list of what is about to happen
# rather than an archive -- a label being printed is not an event in the life of a
# machine, which is why it is not in the item's history either.
KEEP_DAYS = 7

QUEUED, CLAIMED, DONE, FAILED = "queued", "claimed", "done", "failed"

PDF, PNG = "pdf", "png"
FORMATS = (PDF, PNG)

# What a job can be for, and the table each kind is looked up in. The same three
# the labels module knows, which is not a coincidence: a label is a label.
KINDS: dict[str, type[Computer] | type[Part] | type[Project]] = {
    labels.COMPUTER: Computer,
    labels.PART: Part,
    labels.PROJECT: Project,
}


class Agent(NamedTuple):
    """One printer somewhere else, as the environment describes it.

    What stock is loaded and what the printer would rather be handed are facts
    about the printer, and they are answered here rather than configured again on
    the machine the printer is plugged into -- one place to change when the roll
    runs out and a different one goes in.
    """

    name: str
    key: str
    media: str
    fmt: str


def agents() -> dict[str, Agent]:
    """The agents named in the environment, by name.

    `RHDB_PRINT_AGENTS=name:key:stock:format,...`, with the stock and the format
    optional. Read on every call rather than cached at import: it is a handful of
    short strings, and a value read once at start-up is one that lies for as long
    as the process lives after somebody changes it.

    An entry that is malformed, or names a stock this register does not know, is
    dropped rather than guessed at. A printer configured wrongly printing the
    wrong thing is worse than one that does not appear.
    """
    out: dict[str, Agent] = {}
    for entry in os.getenv("RHDB_PRINT_AGENTS", "").split(","):
        bits = [b.strip() for b in entry.split(":")]
        if len(bits) < 2 or not bits[0] or not bits[1]:
            continue
        name, key = bits[0], bits[1]
        media = bits[2] if len(bits) > 2 and bits[2] else labels.SMALL
        fmt = bits[3].lower() if len(bits) > 3 and bits[3] else PDF
        if media not in labels.MEDIA or fmt not in FORMATS:
            continue
        out[name] = Agent(name=name, key=key, media=media, fmt=fmt)
    return out


def agent_for(key: str) -> Agent | None:
    """The agent a key belongs to, compared in constant time.

    Every agent is compared against even once one has matched, so the time this
    takes says nothing about which agent a key was closest to.
    """
    found = None
    for agent in agents().values():
        if secrets.compare_digest(agent.key, key):
            found = agent
    return found


def _now() -> datetime:
    """The clock, as the columns store it: UTC, without the offset. MariaDB's
    DATETIME has nowhere to put a timezone, and a naive local time in one is a
    value that jumps by an hour twice a year."""
    return datetime.now(UTC).replace(tzinfo=None)


def sweep(db: Session) -> int:
    """Forget what finished more than a week ago. Called when a job is added, so
    the table is tidied by the thing that grows it and there is nothing to
    schedule. Only finished jobs: an agent switched off for a fortnight is an
    ordinary state, not a reason to throw its work away."""
    old = _now() - timedelta(days=KEEP_DAYS)
    rows = (
        db.query(PrintJob)
        .filter(PrintJob.state.in_((DONE, FAILED)), PrintJob.finished_at < old)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(rows)


def add(
    db: Session,
    agent: Agent,
    kind: str,
    asset_id: str,
    media: str = "",
    fmt: str = "",
    dpi: int = 0,
    copies: int = 1,
) -> PrintJob:
    """Put a label on an agent's queue. The caller has already established that
    the item exists -- a job for something that is not there belongs to be refused
    at the door rather than discovered by a Pi in another room."""
    sweep(db)
    job = PrintJob(
        agent=agent.name,
        kind=kind,
        asset_id=asset_id,
        media=media or agent.media,
        fmt=fmt or agent.fmt,
        dpi=max(0, dpi),
        copies=max(1, min(copies, 20)),
        state=QUEUED,
        created_at=_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim(db: Session, agent: Agent) -> PrintJob | None:
    """The oldest job waiting for this agent, marked as claimed, or None.

    Claimed by an update that names the state it expects to find, and repeated if
    somebody else got there first. Two agents under one name, or one agent asking
    again before it has finished, must not both print the same label -- and the
    check has to be the write itself: reading a row and then writing it is two
    steps with room between them for the other claimant.
    """
    stale = _now() - timedelta(seconds=LEASE_SECONDS)
    for _ in range(5):
        row = db.execute(
            select(PrintJob)
            .where(
                PrintJob.agent == agent.name,
                (PrintJob.state == QUEUED)
                | ((PrintJob.state == CLAIMED) & (PrintJob.claimed_at < stale)),
            )
            .order_by(PrintJob.created_at, PrintJob.id)
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        was = row.state
        taken = (
            db.query(PrintJob)
            .filter(PrintJob.id == row.id, PrintJob.state == was)
            .update({"state": CLAIMED, "claimed_at": _now()}, synchronize_session=False)
        )
        db.commit()
        if taken:
            db.refresh(row)
            return row
    return None


def held_by(db: Session, agent: Agent, job_id: int) -> PrintJob | None:
    """A job this agent is holding. Another agent's job is not found rather than
    forbidden: there is nothing to be gained by confirming it exists."""
    job = db.get(PrintJob, job_id)
    if job is None or job.agent != agent.name or job.state != CLAIMED:
        return None
    return job


def finish(db: Session, job: PrintJob, ok: bool, error: str = "") -> PrintJob:
    job.state = DONE if ok else FAILED
    job.error = "" if ok else (error or "the agent did not say")[:255]
    job.finished_at = _now()
    db.commit()
    db.refresh(job)
    return job


def label_bytes(
    db: Session, kind: str, asset_id: str, media_name: str, fmt: str, dpi: int = 0
) -> bytes | None:
    """One item's label, rendered now. None if the item has since gone.

    Rendered at this moment and not when the job was made, so a correction in the
    minutes before an agent picks the job up is on the label that comes out.
    """
    model = KINDS.get(kind)
    if model is None:
        return None
    item = db.get(model, asset_id)
    if item is None:
        return None
    media = labels.MEDIA.get(media_name)
    if media is None:
        return None
    row = to_dict(item)
    parts: list[dict[str, object]] = []
    pairs = None
    form_factor = ""
    if isinstance(item, Part):
        pairs = specdb.pairs(db, item, display=True)
    elif isinstance(item, Computer):
        installed = db.query(Part).filter(Part.computer_id == asset_id).all()
        board = next((p for p in installed if p.type == "motherboard"), None)
        for p in installed:
            d = to_dict(p)
            d["spec_pairs"] = specdb.pairs(db, p, display=True)
            parts.append(d)
        raw = specdb.scalars(db, board).get("form_factor", "") if board else ""
        form_factor = raw if isinstance(raw, str) else ""
    # A machine's full label is the one that is read across a room; everything else
    # is a sticker on the thing itself. The same defaults the buttons take.
    small = kind != labels.COMPUTER or media_name != labels.FULL
    if fmt == PNG:
        return labels.render_png(
            row,
            parts,
            kind,
            media,
            dpi,
            small=small,
            form_factor=form_factor,
            spec_pairs=pairs,
        )
    return labels.render_pdf(
        row, parts, kind, small=small, media=media, form_factor=form_factor, spec_pairs=pairs
    )


def as_dict(job: PrintJob) -> dict[str, object]:
    """A job as the API answers with it. `fmt` is `format` on the wire: the column
    is not called that because `format` is a builtin, and the wire is not called
    `fmt` because nobody reading the manual should have to know that."""
    return {
        "id": job.id,
        "agent": job.agent,
        "kind": job.kind,
        "asset_id": job.asset_id,
        "media": job.media,
        "format": job.fmt,
        "dpi": job.dpi,
        "copies": job.copies,
        "state": job.state,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "claimed_at": job.claimed_at.isoformat() if job.claimed_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
