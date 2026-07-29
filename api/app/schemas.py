"""Request/response shapes. Fields default to "" (or None for the typed ones) so
a POST can omit them; PATCH handlers use model_dump(exclude_unset=True) so only
supplied fields change. year is a plain integer, acquired_date and disposed_at
are ISO dates (all three take null for "not recorded"), and disposed is a
boolean flag whose optional detail lives in disposed_note."""
from datetime import date

from pydantic import BaseModel, ConfigDict


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
    computer_id: str = ""
    parent_id: str = ""
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


class PartOut(PartIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
