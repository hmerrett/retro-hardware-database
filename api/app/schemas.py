"""Request/response shapes. Fields default to "" (or None for the typed ones) so
a POST can omit them; PATCH handlers use model_dump(exclude_unset=True) so only
supplied fields change. year is a plain integer, acquired_date and disposed_at
are ISO dates (all three take null for "not recorded"), and disposed is a
boolean flag whose optional detail lives in disposed_note. A part's
computer_id / parent_id accept "" or null for "standalone"; both store NULL."""
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator


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


class ComputerOut(ComputerIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str


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
