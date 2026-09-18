"""Request/response shapes. Fields default to "" (or None for the typed ones) so
a POST can omit them; PATCH handlers use model_dump(exclude_unset=True) so only
supplied fields change. year is a plain integer, acquired_date and disposed_at
are ISO dates (all three take null for "not recorded"), and disposed is a
boolean flag whose optional detail lives in disposed_note. A part's
computer_id / parent_id accept "" or null for "standalone"; both store NULL.

A computer's installed_ram is rendered from its fitted modules and chips, so it
is read-only in that sense: sending one sets the total (or a note when it is not
an amount) and leaves any breakdown alone. installed_ram_kb is the usable total.

`machine` is the one nested shape, because a catalogue identity is not a string:
it is a model key from app/machines.py plus the variations that model was built
in. Omitting it leaves the catalogue rows alone, sending null forgets them
altogether, and sending an object replaces the fields it names. `variant` beside
it is the rendered line those rows come out as, and is read-only: it is written
from the rows and never parsed back into them.

A part takes one too, and only a motherboard may: a board is the object the board
issue and the chip sockets were always about, so a bare one on a shelf files as
what it is instead of as free text. It answers a little less than a machine does
(see BoardIn), and asking it of any other kind of part is refused.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator


def _null_is_blank(v: object) -> object:
    """A serial that reads as null is one nobody wrote down, which is "".

    Belt to 0034's braces. That migration makes the column NOT NULL so the app's
    own database cannot produce a null here again, but a database restored from a
    backup taken before it can -- and this shape is read from ORM rows, so a single
    null used to fail response validation for the entire list rather than for the
    one row holding it. Coercing costs nothing and keeps the blast radius at the
    row. On the way in it means a caller may send null for "not recorded", the
    leniency PartIn's links already extend.
    """
    return "" if v is None else v


class MachineIn(BaseModel):
    """A machine's catalogue identity as it arrives. Every field is optional so a
    caller can name a board issue without restating the model, and the fields it
    does not name are left as they are -- except model_key, which being blanked
    forgets the catalogue for that machine, board issue and chips and all.

    chips is {role: variant}, keyed by the catalogue's role slugs for the model
    ('ula', 'sid', 'crtc'). A role the model has no socket for is refused rather
    than stored, because a C64 with a ULA is a mistake worth hearing about; the
    variant itself is free text, since the catalogue's lists name what was
    commonly made rather than everything that exists.

    sockets is {role: bool} beside it: true for a chip in a socket, false for one
    soldered to the board. A role left out keeps whatever it already said, and null
    puts it back to nobody having looked -- which is why this is a field of its own
    rather than a third state stuffed into the variant string.
    """

    model_key: str | None = None
    issue: str | None = None
    style: str | None = None
    region: str | None = None
    chips: dict[str, str] | None = None
    sockets: dict[str, bool | None] | None = None


class BoardIn(BaseModel):
    """The same identity as it arrives for a motherboard, which is asked less of it.

    A board is the one part the catalogue can name: it is the thing a board issue
    and a chip socket were always about, and a bare Amiga 500 board is an Amiga 500
    board rather than an unidentified green rectangle. What it is not asked is the
    case style and the region, which are facts about a whole machine in a box -- a
    board out of a rubber-key Spectrum is the same board as one out of a moulded
    one.

    This is the one shape here that refuses a field it does not have. Everywhere
    else an unknown key is a caller's own typo and dropping it costs nothing; here
    the two most likely ones are `style` and `region`, which are real questions
    asked of the machine next door -- so ignoring them would take an answer somebody
    meant and quietly put it nowhere. The same reasoning the catalogue file follows
    for a misspelled field (see machines._fields).
    """

    model_config = ConfigDict(extra="forbid")

    model_key: str | None = None
    issue: str | None = None
    chips: dict[str, str] | None = None
    sockets: dict[str, bool | None] | None = None


class ComputerIn(BaseModel):
    name: str = ""
    manufacturer: str = ""
    model: str = ""
    year: int | None = None
    # The number on this particular machine, not a fact about the model.
    serial: str = ""
    chassis: str = ""
    os: str = ""
    cpu: str = ""
    # The DOS benchmark's number for this machine, on the machines that have one:
    # null is "not run", and nothing infers a score from the CPU.
    topbench: int | None = None
    installed_ram: str = ""
    drives: str = ""
    condition: str = ""
    source: str = ""
    acquired_date: date | None = None
    image: str = ""
    url: str = ""
    summary: str = ""
    notes: str = ""
    disposed: bool = False
    disposed_at: date | None = None
    disposed_note: str = ""
    machine: MachineIn | None = None

    _serial_null_is_blank = field_validator("serial", mode="before")(_null_is_blank)


class WorkIn(BaseModel):
    """What a thing needs doing, asked at the moment it is entered.

    A create carries this and an update does not, which is why it is a shape of its
    own rather than two more fields on ComputerIn: the note belongs to checking
    something in -- it is thought while the machine is being unpacked -- and a field
    that a PATCH accepted and ignored would be a worse answer than one it refuses.
    An item that already exists has its own page, with the same box on it.

    work_needed is one job to a line. work_project names a project already going for
    the item to join instead of raising one of its own; a tag that names no project
    is refused rather than filed elsewhere."""

    work_needed: str = ""
    work_project: str = ""


class ComputerCreate(ComputerIn, WorkIn):
    pass


class MachineOut(BaseModel):
    """What a machine's catalogue identity reads back as: what is stored, plus the
    catalogue's own words for it. model and family come from app/machines.py rather
    than the database, so a caller does not have to hold the catalogue itself to
    know that `zx-spectrum-plus` is a Sinclair ZX Spectrum+."""

    model_key: str = ""
    model: str = ""
    family: str = ""
    issue: str = ""
    style: str = ""
    region: str = ""
    chips: dict[str, str] = {}
    # Only the sockets somebody has actually looked at: absent is "not recorded",
    # which is a different thing from soldered.
    sockets: dict[str, bool] = {}


class ComputerOut(ComputerIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
    # The project this one is on, by tag, or null. One of them (ADR-0016); this was
    # a list while a thing could be on several. A tag rather than a name because a
    # name is edited and a tag is not, and because the project itself is one GET
    # away -- so a caller that has just noted work down can reach what it made
    # without going looking for it by name.
    project: str | None = None
    installed_ram_kb: int | None = None
    installed_ram_note: str = ""
    drives_note: str = ""
    # What is read back is more than what may be written -- the catalogue's own
    # facts about the model come with it -- so the response narrows the field the
    # request declared. Pydantic means this to be done; mypy reads it as an
    # attribute changing type under a subclass, which for a mutable one it is. The
    # alternative is a shared base without the field, and that reorders the
    # published schema (ADR-0010) to satisfy a checker.
    machine: MachineOut | None = None  # type: ignore[assignment]
    variant: str = ""


class BoardOut(BaseModel):
    """What a board's catalogue identity reads back as. MachineOut without the two
    rows a case answers, for the reason BoardIn leaves them out."""

    model_key: str = ""
    model: str = ""
    family: str = ""
    issue: str = ""
    chips: dict[str, str] = {}
    sockets: dict[str, bool] = {}


class PartIn(BaseModel):
    computer_id: str | None = None
    parent_id: str | None = None
    type: str = ""
    manufacturer: str = ""
    model: str = ""
    name: str = ""
    year: int | None = None
    serial: str = ""
    specs: str = ""
    condition: str = ""
    source: str = ""
    acquired_date: date | None = None
    image: str = ""
    url: str = ""
    summary: str = ""
    notes: str = ""
    disposed: bool = False
    disposed_at: date | None = None
    disposed_note: str = ""
    disk_image: str = ""
    machine: BoardIn | None = None

    @field_validator("computer_id", "parent_id", mode="before")
    @classmethod
    def _blank_link_is_none(cls, v: object) -> object:
        """A blank link means standalone, which the column stores as NULL."""
        return v or None

    _serial_null_is_blank = field_validator("serial", mode="before")(_null_is_blank)


class PartCreate(PartIn, WorkIn):
    pass


class PartOut(PartIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
    # Narrowed on the way out, as ComputerOut's is and for the reason given there.
    machine: BoardOut | None = None  # type: ignore[assignment]
    variant: str = ""
    # By tag, for the reason a computer's is (see ComputerOut).
    project: str | None = None


# --- projects ----------------------------------------------------------------
# A project is not an asset and its shape says so: no manufacturer, no model, no
# condition, no disposal. What it has instead is a state, three dates, and three
# lists -- what it is about, what is to be done, and what has been bought.
#
# The three lists are read-only in ProjectOut and written through endpoints of
# their own, which is the one place these shapes depart from ComputerIn's habit of
# taking everything at once. A task is a row a person ticks, not a field of the
# project: sending the whole list back to change one of them would mean a caller
# that read the list, edited it and posted it could silently drop a job somebody
# else added in between.


class ProjectIn(BaseModel):
    """A project as it arrives. Every field is optional so a PATCH can name one.

    `status` is a slug from app/projects.py -- planned, active, stalled, done,
    abandoned -- and anything else is stored as `planned` rather than refused, the
    same forgiveness the GUI's menu gives. The three dates are independent: a
    project can be finished without ever having been started."""

    name: str = ""
    status: str = ""
    summary: str = ""
    notes: str = ""
    started_at: date | None = None
    target_date: date | None = None
    finished_at: date | None = None
    # Whether it is kept off the public site. The API is behind the login entire,
    # so this reads and writes here like any other column; what it governs is the
    # five places a page could otherwise show it (see main._visible).
    private: bool = False


class ProjectItemOut(BaseModel):
    """One computer or part a project is about. `kind` is the URL segment its page
    lives under, so a caller can build a link without knowing which of the two
    tables holds it."""

    asset_id: str
    kind: str
    name: str
    note: str = ""


class ProjectItemIn(BaseModel):
    asset_id: str
    note: str = ""


class ProjectTaskIn(BaseModel):
    """A job. `asset_id` is the thing it is about, where it is about one -- it must
    be something the project already holds, and is left out for the jobs that are
    about the project rather than any single thing on it."""

    text: str = ""
    done: bool | None = None
    asset_id: str | None = None


class ProjectTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    done: bool
    done_at: date | None = None
    asset_id: str | None = None


class ProjectOrderIn(BaseModel):
    """Something bought for a project.

    `cost_p` is pence, as an integer, because that is what the column holds and
    what it holds is exact -- see the migration on why every quantity in this
    schema is an integer in a small unit. Null is a cost not recorded, which is not
    the same as zero, and a total is entitled to say how many of its lines are
    null rather than counting them as free.

    `qty` multiplies nothing: the cost is the cost of the line as paid. Four SIMMs
    for twelve pounds is qty 4 and cost_p 1200."""

    description: str = ""
    supplier: str = ""
    url: str = ""
    qty: int = 1
    cost_p: int | None = None
    ordered_at: date | None = None
    expected_at: date | None = None
    delivered: bool | None = None
    note: str = ""


class ProjectOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    description: str
    supplier: str = ""
    url: str = ""
    qty: int = 1
    cost_p: int | None = None
    ordered_at: date | None = None
    expected_at: date | None = None
    delivered: bool = False
    delivered_at: date | None = None
    note: str = ""


class ProjectOut(ProjectIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
    # The status as it is written on screen beside the slug it is stored as, for
    # the reason MachineOut carries the catalogue's own words: a caller should not
    # have to hold this module's vocabulary to know that `active` reads
    # "in progress".
    status_label: str = ""
    items: list[ProjectItemOut] = []
    tasks: list[ProjectTaskOut] = []
    orders: list[ProjectOrderOut] = []
