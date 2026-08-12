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
in. Omitting it leaves a machine's catalogue rows alone, sending null forgets them
altogether, and sending an object replaces the fields it names. `variant` beside
it is the rendered line those rows come out as, and is read-only: it is written
from the rows and never parsed back into them.
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
    """
    model_key: str | None = None
    issue: str | None = None
    style: str | None = None
    region: str | None = None
    chips: dict[str, str] | None = None


class ComputerIn(BaseModel):
    name: str = ""
    manufacturer: str = ""
    model: str = ""
    year: int | None = None
    chassis: str = ""
    os: str = ""
    cpu: str = ""
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


class ComputerOut(ComputerIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
    installed_ram_kb: int | None = None
    installed_ram_note: str = ""
    drives_note: str = ""
    machine: MachineOut | None = None
    variant: str = ""


class PartIn(BaseModel):
    computer_id: str | None = None
    parent_id: str | None = None
    type: str = ""
    manufacturer: str = ""
    model: str = ""
    name: str = ""
    year: int | None = None
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

    @field_validator("computer_id", "parent_id", mode="before")
    @classmethod
    def _blank_link_is_none(cls, v):
        """A blank link means standalone, which the column stores as NULL."""
        return v or None


class PartOut(PartIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
