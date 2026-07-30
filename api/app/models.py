"""ORM tables. One shared asset register across computers + parts. A part's
computer_id links it to a computer's asset_id, and parent_id to the part it is
mounted on; both are real foreign keys, NULL when the part stands alone. Deleting
a computer or a host part unlinks what pointed at it rather than orphaning it.

The column set began as a mirror of the flat-file system's CSV schema, where
everything was a string; quantities and dates are being given real types as the
data proves clean enough to convert."""
from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Integer,
                        SmallInteger, String, Text)

from .db import Base


def _part_fk():
    """part_id column referencing a part, cascading on delete."""
    return Column(String(16), ForeignKey("parts.asset_id", ondelete="CASCADE"),
                  primary_key=True)


def _part_fk_indexed():
    return Column(String(16), ForeignKey("parts.asset_id", ondelete="CASCADE"),
                  index=True, nullable=False)


class Computer(Base):
    __tablename__ = "computers"
    asset_id = Column(String(16), primary_key=True)
    name = Column(String(255), default="")
    manufacturer = Column(String(255), default="")
    model = Column(String(255), default="")
    year = Column(SmallInteger)
    chassis = Column(String(64), default="")
    os = Column(String(255), default="")
    cpu = Column(String(255), default="")
    installed_ram = Column(String(255), default="")
    installed_ram_kb = Column(Integer)
    installed_ram_note = Column(String(255), nullable=False, default="",
                                server_default="")
    drives = Column(Text, default="")
    drives_note = Column(String(255), nullable=False, default="",
                         server_default="")
    condition = Column(String(64), default="")
    source = Column(String(255), default="")
    acquired_date = Column(Date)
    image = Column(String(255), default="")
    url = Column(Text, default="")
    summary = Column(Text, default="")
    notes = Column(Text, default="")
    disposed = Column(Boolean, nullable=False, default=False,
                      server_default="0")
    disposed_at = Column(Date)
    disposed_note = Column(Text, nullable=False, default="", server_default="")


class Part(Base):
    __tablename__ = "parts"
    asset_id = Column(String(16), primary_key=True)
    computer_id = Column(String(16),
                         ForeignKey("computers.asset_id", ondelete="SET NULL"),
                         index=True)
    parent_id = Column(String(16),
                       ForeignKey("parts.asset_id", ondelete="SET NULL"),
                       index=True)
    type = Column(String(32), default="")
    manufacturer = Column(String(255), default="")
    model = Column(String(255), default="")
    name = Column(String(255), default="")
    year = Column(SmallInteger)
    specs = Column(Text, default="")
    condition = Column(String(64), default="")
    source = Column(String(255), default="")
    acquired_date = Column(Date)
    image = Column(String(255), default="")
    url = Column(Text, default="")
    summary = Column(Text, default="")
    notes = Column(Text, default="")
    disposed = Column(Boolean, nullable=False, default=False,
                      server_default="0")
    disposed_at = Column(Date)
    disposed_note = Column(Text, nullable=False, default="", server_default="")
    disk_image = Column(String(255), default="")


# --- normalised spec tables ------------------------------------------------
# One typed row per part for each type that has a fixed set of attributes, plus
# child tables for the genuinely list-shaped motherboard/io fields. These are the
# read path for structured spec data (filtering, faceting, form repopulation);
# parts.specs holds the rendered string for display and for the REST/MCP wire
# format, refreshed from these on every write (see specdb.write).
#
# Quantities are stored as numbers in a fixed small unit named by the column
# suffix (_kb, _khz, _ns, _rpm) so they sort and compare properly; specstruct
# renders them back to friendly units for display. A value that will not parse
# as a number is preserved verbatim as a PartAttribute rather than being lost.


class MotherboardSpec(Base):
    __tablename__ = "motherboard_spec"
    part_id = _part_fk()
    chipset = Column(String(255))
    cpu_family = Column(String(255))
    form_factor = Column(String(64))
    onboard_ram = Column(String(64))
    cache_kb = Column(Integer)
    bios = Column(String(255))
    onboard_video = Column(String(255))


class CpuSpec(Base):
    __tablename__ = "cpu_spec"
    part_id = _part_fk()
    socket = Column(String(64))
    # kHz, not MHz: the 8088's 4.77 MHz would not survive an integer MHz column.
    speed_khz = Column(Integer)
    fsb_khz = Column(Integer)
    cores = Column(Integer)
    cache_kb = Column(Integer)


class RamSpec(Base):
    __tablename__ = "ram_spec"
    part_id = _part_fk()
    ram_type = Column(String(64))
    size_kb = Column(Integer)
    # Module access time (70, 60, ...). SDRAM clock speeds belong in ram_type.
    speed_ns = Column(Integer)


class VideoSpec(Base):
    __tablename__ = "video_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))
    connector = Column(String(255))
    memory_kb = Column(Integer)
    video_type = Column(String(64))


class SoundSpec(Base):
    __tablename__ = "sound_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))
    fm = Column(String(255))
    ports = Column(String(255))


class NetworkSpec(Base):
    __tablename__ = "network_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))
    connector = Column(String(255))


class IoSpec(Base):
    __tablename__ = "io_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))


class StorageSpec(Base):
    __tablename__ = "storage_spec"
    part_id = _part_fk()
    kind = Column(String(64))
    interface = Column(String(64))
    protocol = Column(String(64))
    capacity_kb = Column(Integer)
    chs_c = Column(Integer)
    chs_h = Column(Integer)
    chs_s = Column(Integer)
    media = Column(String(255))
    speed_rpm = Column(Integer)
    role = Column(String(255))


class PartSlot(Base):
    __tablename__ = "part_slot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    bus = Column(String(64))
    count = Column(Integer, default=1)


class PartRamSlot(Base):
    __tablename__ = "part_ram_slot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    slot_type = Column(String(64))
    count = Column(Integer, default=1)


class PartPort(Base):
    __tablename__ = "part_port"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    port = Column(String(64))
    count = Column(Integer, default=1)


class PartAttribute(Base):
    __tablename__ = "part_attribute"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    akey = Column(String(128), default="")
    avalue = Column(Text, default="")


def _computer_fk():
    return Column(String(16), ForeignKey("computers.asset_id", ondelete="CASCADE"),
                  index=True, nullable=False)


class ComputerDrive(Base):
    """A removable-media drive fitted in a machine: floppy, Gotek, optical, or a
    card standing in for one. Mechanical hard disks and tape are parts with their
    own asset tag, not rows here.

    size and form_factor hold the standard labels a person writes ('1.44MB',
    '5.25"') rather than a byte count: these are media designations, not measured
    quantities, and 1.44MB is 1475 KB only by convention."""
    __tablename__ = "computer_drive"
    id = Column(Integer, primary_key=True, autoincrement=True)
    computer_id = _computer_fk()
    count = Column(Integer, default=1)
    kind = Column(String(32), nullable=False, default="")
    form_factor = Column(String(16), nullable=False, default="")
    size = Column(String(32), nullable=False, default="")
    model = Column(String(255), nullable=False, default="")


class ComputerRamModule(Base):
    """How many of each SIMM/SIPP module type are fitted in a machine. `module` is
    the stable slug from entry.RAM_MODULES, never the display label -- the label
    is free to change without orphaning anyone's data."""
    __tablename__ = "computer_ram_module"
    id = Column(Integer, primary_key=True, autoincrement=True)
    computer_id = _computer_fk()
    module = Column(String(32), nullable=False)
    count = Column(Integer, default=1)


class ComputerRamChip(Base):
    """How many of each DRAM chip are fitted directly on the board, keyed by part
    number (4164, 41256, ...)."""
    __tablename__ = "computer_ram_chip"
    id = Column(Integer, primary_key=True, autoincrement=True)
    computer_id = _computer_fk()
    chip = Column(String(32), nullable=False)
    count = Column(Integer, default=1)


class LogEntry(Base):
    """A dated history entry for any asset (computer or part): automatic
    change records and free-text notes. asset_id is from the shared register, so
    it is a plain column rather than a foreign key to one table."""
    __tablename__ = "log_entry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String(16), index=True)
    created_at = Column(DateTime, index=True)
    kind = Column(String(16), default="change")
    message = Column(Text, default="")
