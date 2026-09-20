"""The print queue, in two halves that do not trust each other equally.

`/api/print/jobs` is the owner's: put a label on a printer's queue, see what is
waiting, take one back off. It is behind the login like the rest of the API.

`/api/print/agent/…` is the agent's, and an agent holds a key rather than the
owner's password. Everything that key reaches is under that one prefix and there
is nothing else there: claim a job for *this* agent, fetch the label for a job
*this* agent holds, say how it went (ADR-0025).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import auth, labels, printing
from ..db import get_db
from ..models import PrintJob
from ..printing import Agent
from ..register import get_or_404
from ..schemas import PrintJobIn, PrintResultIn

router = APIRouter()

MEDIA_TYPE = {printing.PDF: "application/pdf", printing.PNG: "image/png"}


def agent_from_key(request: Request) -> Agent:
    """Which agent is asking, from its bearer key.

    A wrong key is counted against the address that sent it, exactly as a wrong
    password at the API's door is: this is the one route in the app that a machine
    with no password may knock on, so it is also the one that could be knocked on
    all night.
    """
    header = request.headers.get("authorization", "")
    key = header[7:].strip() if header[:7].lower() == "bearer " else ""
    found = printing.agent_for(key) if key else None
    if found is not None:
        return found
    if not auth.note_wrong_secret(request):
        raise HTTPException(status_code=429, detail="Too many failed attempts, try again later")
    raise HTTPException(status_code=401, detail="Unknown print agent")


def _named(name: str) -> Agent:
    """The agent a job is addressed to.

    404 and not 422 for a name that is not configured, and the same 404 when no
    agents are configured at all: until somebody has written a key down there is
    no queue, and an installation that has not asked for one should not be able to
    tell a name it typed wrongly from a feature it never turned on.
    """
    found = printing.agents().get(name)
    if found is None:
        raise HTTPException(status_code=404, detail="No such print agent")
    return found


@router.post("/api/print/jobs")
def queue_label(body: PrintJobIn, db: Session = Depends(get_db)) -> dict[str, object]:
    """Put a label on an agent's queue.

    The item is looked up here rather than when the agent asks, so a mistyped tag
    is refused while the person who typed it is still looking at the screen."""
    agent = _named(body.agent)
    model = printing.KINDS.get(body.kind)
    if model is None:
        raise HTTPException(status_code=422, detail="A label is for a computer, part or project")
    if body.media and body.media not in labels.MEDIA:
        raise HTTPException(status_code=422, detail="No such label stock")
    if body.format and body.format not in printing.FORMATS:
        raise HTTPException(status_code=422, detail="A label is a pdf or a png")
    item = get_or_404(db, model, body.asset_id)
    job = printing.add(
        db,
        agent,
        body.kind,
        str(item.asset_id),
        media=body.media,
        fmt=body.format,
        dpi=body.dpi,
        copies=body.copies,
    )
    return printing.as_dict(job)


@router.get("/api/print/jobs")
def list_jobs(
    agent: str = "", state: str = "", db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """What is waiting, what has printed and what went wrong -- so the answer to
    "why has nothing come out" is on the screen in the room the label was sent
    from, rather than in a log on the Pi."""
    q = db.query(PrintJob)
    if agent:
        q = q.filter(PrintJob.agent == agent)
    if state:
        q = q.filter(PrintJob.state == state)
    return [printing.as_dict(j) for j in q.order_by(PrintJob.created_at, PrintJob.id).all()]


@router.delete("/api/print/jobs/{job_id}")
def cancel_job(job_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Take a job off the queue. Only one that has not been claimed: a job an agent
    is holding may already be half way through a printer, and the register is not
    in a position to know."""
    job = db.get(PrintJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such print job")
    if job.state != printing.QUEUED:
        raise HTTPException(status_code=409, detail="That job is no longer waiting")
    db.delete(job)
    db.commit()
    return {"ok": True, "id": job_id}


# response_model=None: the answer is a job or a bare 204, and FastAPI cannot make a
# response model out of a union with a Response in it.
@router.post("/api/print/agent/claim", response_model=None)
def claim_job(
    agent: Agent = Depends(agent_from_key), db: Session = Depends(get_db)
) -> dict[str, object] | Response:
    """The next label for this agent, or nothing.

    Nothing is a 204 and not an error: an agent asks every few seconds forever, and
    an empty queue is its ordinary answer rather than a fault to fill a log with.
    """
    job = printing.claim(db, agent)
    if job is None:
        return Response(status_code=204)
    return printing.as_dict(job)


@router.get("/api/print/agent/jobs/{job_id}/label.{fmt}")
def agent_label(
    job_id: int,
    fmt: str,
    agent: Agent = Depends(agent_from_key),
    db: Session = Depends(get_db),
) -> Response:
    """The label for a job this agent is holding, rendered now.

    410 where the item has gone since the job was made: the agent has to be told
    that this one is never going to work, which a 404 -- the answer for a job that
    was never its -- does not say.
    """
    if fmt not in printing.FORMATS:
        raise HTTPException(status_code=404, detail="A label is a pdf or a png")
    job = printing.held_by(db, agent, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such print job")
    body = printing.label_bytes(db, job.kind, job.asset_id, job.media, fmt, job.dpi)
    if body is None:
        printing.finish(db, job, ok=False, error="the item is no longer in the register")
        raise HTTPException(status_code=410, detail="The item is no longer in the register")
    return Response(
        body,
        media_type=MEDIA_TYPE[fmt],
        headers={"Content-Disposition": f'inline; filename="{job.asset_id}.{fmt}"'},
    )


@router.post("/api/print/agent/jobs/{job_id}/done")
def report_job(
    job_id: int,
    body: PrintResultIn,
    agent: Agent = Depends(agent_from_key),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    job = printing.held_by(db, agent, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such print job")
    return printing.as_dict(printing.finish(db, job, ok=body.ok, error=body.error))
