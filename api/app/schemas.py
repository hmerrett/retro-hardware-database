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
    installed_ram_kb: int | None = None
    installed_ram_note: str = ""
    drives_note: str = ""
    machine: MachineOut | None = None
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
    def _blank_link_is_none(cls, v):
        """A blank link means standalone, which the column stores as NULL."""
        return v or None


class PartOut(PartIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
    machine: BoardOut | None = None
    variant: str = ""
