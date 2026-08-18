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
    # What this machine scores in TopBench, the DOS benchmark that puts a PC in
    # order against a table of known ones. It sits beside the CPU because that is
    # mostly what decides it, and it is the one measured number in a record that
    # otherwise says only what a machine was built as -- two 486DX2-66s with the
    # same score are the same machine, and the one that scores half is telling you
    # something (a cache disabled, a turbo button, a chipset set up wrong).
    #
    # Only an x86 machine has one: TopBench is a DOS program and there is no score
    # to be had for a Spectrum. NULL is a machine it has not been run on, which is
    # most of them, and no number is inferred from the CPU -- running it is the
    # whole point.
    topbench = Column(Integer)
    installed_ram = Column(String(255), default="")
    installed_ram_kb = Column(Integer)
    installed_ram_note = Column(String(255), nullable=False, default="",
                                server_default="")
    # The rendered cache of the catalogue rows, in the same relation to
    # asset_variant / asset_chip as installed_ram is to the memory tables:
    # written from them on every change, read by the page, the label, the search
    # index and the wire format, and never parsed back (see machinedb).
    variant = Column(Text, nullable=False, default="", server_default="")
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
    # The rendered cache of the catalogue rows, in exactly the relation to
    # asset_variant / asset_chip that computers.variant is: written from them on
    # every change and never parsed back. Only a board ever has one -- a catalogue
    # identity is something a machine or the board out of one can answer to, and a
    # SIMM cannot -- so on every other part this stays the empty string it starts as.
    variant = Column(Text, nullable=False, default="", server_default="")
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
    # The other sort of drive speed: the × rating of an optical drive, where 1× is
    # the 150 KB/s a CD player runs at. Its own column because 48× and 5400 rpm are
    # different quantities and one column could not sort or compare both; they
    # share the Speed spec key, and the unit written in the value says which is
    # meant (see specstruct.ALT_COLS).
    speed_x = Column(Integer)
    role = Column(String(255))
    # The same two things a machine's drive rows record about the same plastic (see
    # ComputerDrive), so a drive on the shelf and one fitted are described alike.
    colour = Column(String(32))
    yellowing = Column(String(32))


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
    quantities, and 1.44MB is 1475 KB only by convention. media and speed are the
    same sort of label for the drive that has no capacity to state -- an optical
    drive is known by the discs it takes ('CD-RW') and the rating on its front
    ('48×'), from entry.OPTICAL_MEDIA and entry.OPTICAL_SPEEDS.

    colour is the shade the bezel was made in and yellowing is how far it has gone
    since, from entry.BEZEL_COLOURS and entry.YELLOWING -- two fields because they
    answer different questions, and either can be known without the other. Both
    hold a label rather than a hex value: what is recorded is which shade and which
    stage, so the swatch that stands for one is free to be adjusted without
    rewriting anyone's data."""
    __tablename__ = "computer_drive"
    id = Column(Integer, primary_key=True, autoincrement=True)
    computer_id = _computer_fk()
    count = Column(Integer, default=1)
    kind = Column(String(32), nullable=False, default="")
    form_factor = Column(String(16), nullable=False, default="")
    size = Column(String(32), nullable=False, default="")
    media = Column(String(32), nullable=False, default="", server_default="")
    speed = Column(String(16), nullable=False, default="", server_default="")
    model = Column(String(255), nullable=False, default="")
    colour = Column(String(32), nullable=False, default="")
    yellowing = Column(String(32), nullable=False, default="")


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


class AssetVariant(Base):
    """Which catalogue machine an asset is, and which of that model's documented
    variations. One row per asset, and only for one the catalogue names -- a PC or
    a custom build has none, which is why this is a table of its own rather than
    four more columns on `computers`.

    Keyed by a plain asset_id from the shared register, the way log_entry is, and
    for the same reason: what answers a catalogue question is a machine or the
    board out of one, and both give the same sort of answer. A sealed Spectrum is
    a Spectrum; a bare Amiga 500 board on a shelf is an Amiga 500 board, and can
    say so with the same words rather than in free text. Which of the two is
    holding the identity is already known from which table the asset_id is in.

    model_key is the stable slug from machines.FAMILIES and is the only part of the
    catalogue stored here; the model's name, year, CPU and chip lists are read from
    the catalogue every time, so correcting an entry there corrects everything
    filed under it. The other three hold what was picked or typed, verbatim: the
    lists in the catalogue name what was commonly made, not everything that
    exists, so a value from outside one is kept as it was given.

    issue is the board as its make marked it -- Sinclair's Issue 6A, Commodore's
    ASSY 250425, an Amiga's Rev 6A, a Mega Drive's VA6 -- and is asked of a board
    as readily as of a machine, since it is the board it was always about.

    style and region are asked only of a machine. A case or keyboard style and the
    market a machine was built for are facts about an assembled computer in a box:
    a board out of a rubber-key Spectrum is the same board as one out of a moulded
    one, and a PAL machine's board is not a PAL board. So a part leaves both blank
    rather than the two moving to a table of their own."""
    __tablename__ = "asset_variant"
    asset_id = Column(String(16), primary_key=True)
    model_key = Column(String(64), nullable=False, default="", server_default="")
    issue = Column(String(64), nullable=False, default="", server_default="")
    style = Column(String(64), nullable=False, default="", server_default="")
    region = Column(String(32), nullable=False, default="", server_default="")


class AssetChip(Base):
    """Which variant of a chip is in one of an asset's sockets: the ULA under the
    heatsink, the SID, the CRTC type, the Kickstart in the ROM socket.

    One row per socket, keyed by the catalogue's stable role slug ('ula', 'sid',
    'crtc') with the part number or version as it is marked on the chip. A socket
    the catalogue no longer lists still reads back, under the role's own name --
    what was seen on the board is not wrong for having gone out of the catalogue.

    These are not parts: a chip soldered to a board is not tagged, photographed or
    shelved separately, and giving each one an asset id would say the collection
    holds forty more objects than it does. The memory chips are the exception that
    proves the rule -- they are counted, not identified, and so have their own
    table (see ComputerRamChip).

    Where the chips are read off is where they are recorded: a sealed machine
    answers for its own sockets, and a board lifted out of one answers for them
    afterwards, which is the whole of what detaching a board moves."""
    __tablename__ = "asset_chip"
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String(16), index=True, nullable=False)
    role = Column(String(32), nullable=False)
    variant = Column(String(64), nullable=False, default="", server_default="")
    # Whether it sits in a socket or is soldered to the board -- the difference
    # between a chip that can be swapped to test a fault and one that means
    # desoldering forty pins. NULL is a chip recorded before the question was asked;
    # nothing claims a chip is soldered because nobody has said otherwise.
    socketed = Column(Boolean, nullable=True)


class StoredFile(Base):
    """A file kept beside the register: a driver disk, a manual, a ROM dump, the
    utility that came with a card.

    It belongs to no one asset. A driver is a fact about a model, not about the
    particular card on the shelf, and a collection with three of the same card
    would otherwise hold the same download three times. So a file is tagged with
    the names it is for, and every item answering to one of those names shows it
    -- see filesdb, which owns both the matching and the bytes on disk.

    `stored` is the name on disk, which is generated: what was uploaded is kept in
    `filename` for the download to be called by, and never used as a path."""
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    stored = Column(String(72), nullable=False, unique=True)
    filename = Column(String(255), nullable=False)
    size = Column(Integer, nullable=False, default=0)
    note = Column(String(255), nullable=False, default="", server_default="")
    created_at = Column(DateTime, index=True)


class FileTag(Base):
    """One name a file is for. `fold` is that name normalised for matching (case
    and spacing are how one name gets typed two ways); `tag` is it as written, for
    showing back. A file has as many as it needs -- a driver that covers a card and
    the machine it shipped in is tagged with both."""
    __tablename__ = "file_tag"
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    tag = Column(String(120), nullable=False)
    fold = Column(String(120), nullable=False, index=True)


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
