"""The survey agent's door, and surveys as JSON (MANUAL §23; ADR-0043).

`/api/survey/agent/…` is the agent's, and an agent holds a key rather than the owner's
password -- ADR-0025's shape. Two things are under it: a machine's question before its
tests, and its reports. The key cannot list or read anything else.

`/api/surveys` is the owner's read of them, behind the login like the rest of the API.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import auth, surveyreport, surveys
from ..db import get_db
from ..forms import posted
from ..models import Survey

router = APIRouter()

# A report is text, and a ROM is at most the 128 KiB of a BIOS. Generous ceilings, so
# a door that a machine with no password may knock on cannot be used to fill a disk.
MOST_REPORT = 4 * 1024 * 1024
MOST_ROM = 1024 * 1024
MOST_QUESTION = 64 * 1024
# A PC's first megabyte holds at most a few dozen option ROMs on 2 KiB boundaries.
MOST_ROMS = 32


def agent_from_key(request: Request) -> surveys.Agent:
    """Which agent is asking, from its bearer key. A wrong key is counted against the
    address that sent it, as a wrong password at the API's door is."""
    header = request.headers.get("authorization", "")
    key = header[7:].strip() if header[:7].lower() == "bearer " else ""
    found = surveys.agent_for(key) if key else None
    if found is not None:
        return found
    if not auth.note_wrong_secret(request):
        raise HTTPException(status_code=429, detail="Too many failed attempts, try again later")
    raise HTTPException(status_code=401, detail="Unknown survey agent")


def _taken(value: str) -> datetime | None:
    """When the agent first saw the report, by its own clock, as UTC without the offset
    the columns have nowhere to keep. None for a value that is not a time."""
    try:
        when = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if when.tzinfo is not None:
        when = when.astimezone(UTC).replace(tzinfo=None)
    return when


@router.post("/api/survey/agent/ask", response_class=PlainTextResponse, tags=["surveys"])
async def ask(
    request: Request,
    agent: surveys.Agent = Depends(agent_from_key),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """A machine's question before its tests: the lines it has found so far, and the
    tag once it has been typed, with the copies of its ROMs that it names. The answer
    is the lines the agent leaves beside it. Asking writes nothing."""
    question, roms = await _question(request)
    return PlainTextResponse(
        surveys.answer_question(db, surveyreport.decode(question), roms, agent)
    )


async def _question(request: Request) -> tuple[bytes, dict[str, bytes]]:
    """The question and the ROMs that came with it: a multipart body (`question`, then
    `roms`) from an agent that sends them, plain text from one from before it did
    (ADR-0044)."""
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        return (await request.body())[:MOST_QUESTION], {}
    form = await posted(request)
    asked = form.uploads("question")
    question = await asked[0].read(MOST_QUESTION) if asked else b""
    roms: dict[str, bytes] = {}
    for rom in form.uploads("roms")[:MOST_ROMS]:
        data = await rom.read(MOST_ROM + 1)
        if 0 < len(data) <= MOST_ROM:
            roms[Path(rom.filename or "").name] = data
    return question, roms


@router.post("/api/survey/agent/surveys", tags=["surveys"])
async def send(
    report: UploadFile = File(...),
    roms: list[UploadFile] = File(default=[]),
    taken: str = Form(""),
    agent: surveys.Agent = Depends(agent_from_key),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """A file of reports, with the ROMs named in them, as the agent found them. Each
    report is a survey, filed as far as it can be. 422 for a file that is not a report,
    with the reason for the agent to leave beside it."""
    raw = await report.read(MOST_REPORT + 1)
    if len(raw) > MOST_REPORT:
        raise HTTPException(status_code=422, detail="The report is too big to be one.")
    copied: dict[str, bytes] = {}
    for rom in roms:
        data = await rom.read(MOST_ROM + 1)
        if 0 < len(data) <= MOST_ROM:
            copied[Path(rom.filename or "").name] = data
    try:
        made = surveys.take(db, agent, raw, copied, _taken(taken))
    except surveyreport.Unreadable as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    answer = surveys.receipt(db, [s for s, _ in made])
    db.commit()
    surveys.labels_for(db, agent, [tag for _, filing in made for tag in filing.made])
    if said := surveys.labels_asked(db, agent, made):
        answer += said + "\r\n"
    return {
        "receipt": answer,
        "surveys": [{"id": s.id, "machine": s.machine, "waiting": s.waiting} for s, _ in made],
    }


@router.get("/api/surveys", tags=["surveys"])
def list_surveys(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Every survey: waiting first, then newest first."""
    return [
        {
            "id": s.id,
            "machine": s.machine,
            "taken": s.taken.isoformat() if s.taken else None,
            "result": s.result,
            "waiting": s.waiting,
        }
        for s in surveys.listing(db)
    ]


@router.get("/api/surveys/{sid}", tags=["surveys"])
def get_survey(sid: int, db: Session = Depends(get_db)) -> dict[str, object]:
    s = db.get(Survey, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="No such survey")
    return surveys.as_dict(s)
