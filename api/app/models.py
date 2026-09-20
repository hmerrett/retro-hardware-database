"""ORM tables. One shared asset register across computers + parts. A part's
computer_id links it to a computer's asset_id, and parent_id to the part it is
mounted on; both are real foreign keys, NULL when the part stands alone. Deleting
a computer or a host part unlinks what pointed at it rather than orphaning it.

The column set began as a mirror of the flat-file system's CSV schema, where
everything was a string; quantities and dates are being given real types as the
data proves clean enough to convert."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column

from .db import Base


def _part_fk() -> MappedColumn[str]:
    """part_id column referencing a part, cascading on delete."""
    return mapped_column(
        String(16), ForeignKey("parts.asset_id", ondelete="CASCADE"), primary_key=True
    )


def _part_fk_indexed() -> MappedColumn[str]:
    return mapped_column(
        String(16), ForeignKey("parts.asset_id", ondelete="CASCADE"), index=True, nullable=False
    )


class Computer(Base):
    __tablename__ = "computers"
    asset_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), default="")
    manufacturer: Mapped[str | None] = mapped_column(String(255), default="")
    model: Mapped[str | None] = mapped_column(String(255), default="")
    year: Mapped[int | None] = mapped_column(SmallInteger)
    # What the maker stamped on this particular one, as against the model, which is
    # what it is one of. The only identity field that is never true of a second
    # object -- which is why a duplicate does not carry it across, and why it is
    # worth having: a machine can be looked up by the number on its own back, and a
    # warranty date, a factory or a production run can be read off it later by
    # somebody who knows how.
    # Not nullable: "" is the one spelling of a number nobody has written down, so
    # the column cannot hold the second one the API used to choke on (0034).
    serial: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    chassis: Mapped[str | None] = mapped_column(String(64), default="")
    os: Mapped[str | None] = mapped_column(String(255), default="")
    cpu: Mapped[str | None] = mapped_column(String(255), default="")
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
    topbench: Mapped[int | None] = mapped_column(Integer)
    installed_ram: Mapped[str | None] = mapped_column(String(255), default="")
    installed_ram_kb: Mapped[int | None] = mapped_column(Integer)
    installed_ram_note: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    # The rendered cache of the catalogue rows, in the same relation to
    # asset_variant / asset_chip as installed_ram is to the memory tables:
    # written from them on every change, read by the page, the label, the search
    # index and the wire format, and never parsed back (see machinedb).
    variant: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    drives: Mapped[str | None] = mapped_column(Text, default="")
    drives_note: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    condition: Mapped[str | None] = mapped_column(String(64), default="")
    source: Mapped[str | None] = mapped_column(String(255), default="")
    acquired_date: Mapped[date | None] = mapped_column(Date)
    # Where the object is kept, in the owner's own words -- a loft, a crate, a shelf.
    # Free text and not a link to anywhere: a collection's geography is its own, and
    # the one thing that is certainly not a place is `computer_id`, which says what a
    # part is fitted in rather than where that machine has been put (ADR-0027).
    #
    # Shown to a visitor only while `public_locations` says so, which is why this is
    # the one column search asks a setting about rather than reading off a fixed set.
    location: Mapped[str | None] = mapped_column(String(255), default="")
    image: Mapped[str | None] = mapped_column(String(255), default="")
    url: Mapped[str | None] = mapped_column(Text, default="")
    summary: Mapped[str | None] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text, default="")
    disposed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    disposed_at: Mapped[date | None] = mapped_column(Date)
    disposed_note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # Might go: the step before disposal, and the owner's alone (ADR-0018). Kept off
    # a visitor's page, out of their search (common.OWNER_ONLY) and out of the API.
    for_sale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


class Part(Base):
    __tablename__ = "parts"
    asset_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    computer_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("computers.asset_id", ondelete="SET NULL"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("parts.asset_id", ondelete="SET NULL"), index=True
    )
    type: Mapped[str | None] = mapped_column(String(32), default="")
    manufacturer: Mapped[str | None] = mapped_column(String(255), default="")
    model: Mapped[str | None] = mapped_column(String(255), default="")
    name: Mapped[str | None] = mapped_column(String(255), default="")
    year: Mapped[int | None] = mapped_column(SmallInteger)
    # The number on this one, for the reason a machine has one (see Computer.serial).
    # A part is where it matters most often: two identical SIMMs are told apart by
    # nothing else, and a drive's own label is the only place its date code lives.
    serial: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    specs: Mapped[str | None] = mapped_column(Text, default="")
    # The rendered cache of the catalogue rows, in exactly the relation to
    # asset_variant / asset_chip that computers.variant is: written from them on
    # every change and never parsed back. Only a board ever has one -- a catalogue
    # identity is something a machine or the board out of one can answer to, and a
    # SIMM cannot -- so on every other part this stays the empty string it starts as.
    variant: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    condition: Mapped[str | None] = mapped_column(String(64), default="")
    source: Mapped[str | None] = mapped_column(String(255), default="")
    acquired_date: Mapped[date | None] = mapped_column(Date)
    # See Computer.location. A part keeps its own, and it is not `computer_id` read
    # another way: a card in a machine is wherever that machine is, and a card in a
    # drawer is in the drawer, so neither answer can be worked out from the other.
    location: Mapped[str | None] = mapped_column(String(255), default="")
    image: Mapped[str | None] = mapped_column(String(255), default="")
    url: Mapped[str | None] = mapped_column(Text, default="")
    summary: Mapped[str | None] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text, default="")
    disposed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    disposed_at: Mapped[date | None] = mapped_column(Date)
    disposed_note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # See Computer.for_sale. The same flag on the other half of the register,
    # because a spare card is as likely to be the thing going as a whole machine.
    for_sale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    disk_image: Mapped[str | None] = mapped_column(String(255), default="")


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
    part_id: Mapped[str] = _part_fk()
    chipset: Mapped[str | None] = mapped_column(String(255))
    cpu_family: Mapped[str | None] = mapped_column(String(255))
    form_factor: Mapped[str | None] = mapped_column(String(64))
    onboard_ram: Mapped[str | None] = mapped_column(String(64))
    cache_kb: Mapped[int | None] = mapped_column(Integer)
    bios: Mapped[str | None] = mapped_column(String(255))
    onboard_video: Mapped[str | None] = mapped_column(String(255))


class CpuSpec(Base):
    __tablename__ = "cpu_spec"
    part_id: Mapped[str] = _part_fk()
    socket: Mapped[str | None] = mapped_column(String(64))
    # kHz, not MHz: the 8088's 4.77 MHz would not survive an integer MHz column.
    speed_khz: Mapped[int | None] = mapped_column(Integer)
    fsb_khz: Mapped[int | None] = mapped_column(Integer)
    cores: Mapped[int | None] = mapped_column(Integer)
    cache_kb: Mapped[int | None] = mapped_column(Integer)


class RamSpec(Base):
    __tablename__ = "ram_spec"
    part_id: Mapped[str] = _part_fk()
    ram_type: Mapped[str | None] = mapped_column(String(64))
    size_kb: Mapped[int | None] = mapped_column(Integer)
    # Module access time (70, 60, ...). SDRAM clock speeds belong in ram_type.
    speed_ns: Mapped[int | None] = mapped_column(Integer)


class VideoSpec(Base):
    __tablename__ = "video_spec"
    part_id: Mapped[str] = _part_fk()
    chip: Mapped[str | None] = mapped_column(String(255))
    interface: Mapped[str | None] = mapped_column(String(64))
    connector: Mapped[str | None] = mapped_column(String(255))
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    video_type: Mapped[str | None] = mapped_column(String(64))


class SoundSpec(Base):
    __tablename__ = "sound_spec"
    part_id: Mapped[str] = _part_fk()
    chip: Mapped[str | None] = mapped_column(String(255))
    interface: Mapped[str | None] = mapped_column(String(64))
    fm: Mapped[str | None] = mapped_column(String(255))
    ports: Mapped[str | None] = mapped_column(String(255))


class NetworkSpec(Base):
    __tablename__ = "network_spec"
    part_id: Mapped[str] = _part_fk()
    chip: Mapped[str | None] = mapped_column(String(255))
    interface: Mapped[str | None] = mapped_column(String(64))
    connector: Mapped[str | None] = mapped_column(String(255))


class IoSpec(Base):
    __tablename__ = "io_spec"
    part_id: Mapped[str] = _part_fk()
    chip: Mapped[str | None] = mapped_column(String(255))
    interface: Mapped[str | None] = mapped_column(String(64))


class StorageSpec(Base):
    __tablename__ = "storage_spec"
    part_id: Mapped[str] = _part_fk()
    kind: Mapped[str | None] = mapped_column(String(64))
    interface: Mapped[str | None] = mapped_column(String(64))
    protocol: Mapped[str | None] = mapped_column(String(64))
    capacity_kb: Mapped[int | None] = mapped_column(Integer)
    chs_c: Mapped[int | None] = mapped_column(Integer)
    chs_h: Mapped[int | None] = mapped_column(Integer)
    chs_s: Mapped[int | None] = mapped_column(Integer)
    media: Mapped[str | None] = mapped_column(String(255))
    speed_rpm: Mapped[int | None] = mapped_column(Integer)
    # The other sort of drive speed: the × rating of an optical drive, where 1× is
    # the 150 KB/s a CD player runs at. Its own column because 48× and 5400 rpm are
    # different quantities and one column could not sort or compare both; they
    # share the Speed spec key, and the unit written in the value says which is
    # meant (see specstruct.ALT_COLS).
    speed_x: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str | None] = mapped_column(String(255))
    # The same two things a machine's drive rows record about the same plastic (see
    # ComputerDrive), so a drive on the shelf and one fitted are described alike.
    colour: Mapped[str | None] = mapped_column(String(32))
    yellowing: Mapped[str | None] = mapped_column(String(32))


class DisplaySpec(Base):
    """A screen: a monitor, a fitted panel, the tube out of an all-in-one.

    Two fields describe the picture-making rather than one. `tech` is CRT or LCD or
    OLED, and `panel` is how that technology is arranged -- a shadow mask, an
    aperture grille, TN or IPS. A Trinitron is a CRT with a grille in it, and filing
    one under a single field would mean it stopped counting as a CRT; kept apart,
    "every CRT" and "every aperture grille" are both answerable.

    `picture` is what colour comes out. A green screen and an amber one are
    different things to own, so the phosphor is named rather than the absence of
    colour being noted.

    The two numbers are stored the way every other quantity here is -- as plain
    integers in a small unit, so they sort and compare in SQL, with specstruct
    rendering them back to the units a person writes. A screen size is in tenths of
    an inch because a 13.3" panel exists and a whole-inch column could not hold it;
    a dot pitch is in micrometres because 0.28 mm is not an integer and the pitch is
    what separates a good tube from a tired one.

    `resolution` is text, deliberately. A fixed panel has one native resolution and
    could be two numbers, but a multisync CRT does 640x480 through 1280x1024 and
    picking one of those to store would be inventing a fact: what goes here is what
    the monitor claims, in its own words.

    `refresh` and `sync` are text for the reason `interface` is: a screen answers
    them more than once. A refresh rate was a whole-Hz integer while it was the one
    highest figure, and stopped being able to be when a screen was allowed to say it
    does 50 Hz and 85 Hz both -- which is the answer that matters on hardware driven
    at television rates, and the answer an integer holding the highest would drop.

    The same goes for the line rate. A tube that locks to 15 kHz and to 31 kHz has two rates and nothing
    between them, while a multiscan quotes a range instead -- an Acorn AKF18 is
    15-38 kHz -- and a single kHz integer could hold neither. So the rates are
    stored as they are given, comma-separated or as the range the monitor claims,
    and "every 15 kHz monitor" is asked of the string.

    `colour` and `yellowing` are the same two the drive rows and storage parts hold,
    from entry.BEZEL_COLOURS and entry.YELLOWING. A monitor's front is the largest
    piece of beige plastic in most collections and it yellows like everything else,
    so it is described in the words the register already uses for plastic."""

    __tablename__ = "display_spec"
    part_id: Mapped[str] = _part_fk()
    tech: Mapped[str | None] = mapped_column(String(64))
    panel: Mapped[str | None] = mapped_column(String(64))
    screen_in_tenths: Mapped[int | None] = mapped_column(Integer)
    aspect: Mapped[str | None] = mapped_column(String(16))
    resolution: Mapped[str | None] = mapped_column(String(64))
    refresh: Mapped[str | None] = mapped_column(String(255))
    sync: Mapped[str | None] = mapped_column(String(255))
    dot_pitch_um: Mapped[int | None] = mapped_column(Integer)
    interface: Mapped[str | None] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(String(32))
    colour: Mapped[str | None] = mapped_column(String(32))
    yellowing: Mapped[str | None] = mapped_column(String(32))


class PartSlot(Base):
    __tablename__ = "part_slot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[str] = _part_fk_indexed()
    bus: Mapped[str | None] = mapped_column(String(64))
    count: Mapped[int | None] = mapped_column(Integer, default=1)


class PartRamSlot(Base):
    __tablename__ = "part_ram_slot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[str] = _part_fk_indexed()
    slot_type: Mapped[str | None] = mapped_column(String(64))
    count: Mapped[int | None] = mapped_column(Integer, default=1)


class PartPort(Base):
    __tablename__ = "part_port"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[str] = _part_fk_indexed()
    port: Mapped[str | None] = mapped_column(String(64))
    count: Mapped[int | None] = mapped_column(Integer, default=1)


class PartAttribute(Base):
    __tablename__ = "part_attribute"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[str] = _part_fk_indexed()
    akey: Mapped[str | None] = mapped_column(String(128), default="")
    avalue: Mapped[str | None] = mapped_column(Text, default="")


def _computer_fk() -> MappedColumn[str]:
    return mapped_column(
        String(16), ForeignKey("computers.asset_id", ondelete="CASCADE"), index=True, nullable=False
    )


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
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    computer_id: Mapped[str] = _computer_fk()
    count: Mapped[int | None] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    form_factor: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    size: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    media: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    speed: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")
    model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    colour: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    yellowing: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class ComputerRamModule(Base):
    """How many of each SIMM/SIPP module type are fitted in a machine. `module` is
    the stable slug from entry.RAM_MODULES, never the display label -- the label
    is free to change without orphaning anyone's data."""

    __tablename__ = "computer_ram_module"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    computer_id: Mapped[str] = _computer_fk()
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int | None] = mapped_column(Integer, default=1)


class ComputerRamChip(Base):
    """How many of each DRAM chip are fitted directly on the board, keyed by part
    number (4164, 41256, ...)."""

    __tablename__ = "computer_ram_chip"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    computer_id: Mapped[str] = _computer_fk()
    chip: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int | None] = mapped_column(Integer, default=1)


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
    asset_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    model_key: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    issue: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    style: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    region: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")


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
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    variant: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    # Whether it sits in a socket or is soldered to the board -- the difference
    # between a chip that can be swapped to test a fault and one that means
    # desoldering forty pins. NULL is a chip recorded before the question was asked;
    # nothing claims a chip is soldered because nobody has said otherwise.
    socketed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class StoredFile(Base):
    """A file kept beside the register: a driver disk, a manual, a ROM dump, the
    utility that came with a card.

    It belongs to no one asset, and is not a column on one. What it is for is
    stated in `file_asset` and `file_model` -- this one unit, or every item of a
    model -- and stated by hand (ADR-0006, ADR-0020). Until 0039 it was inferred
    from the file's tags, by containment on the item's name, which is why the
    argument for that lived in this docstring; it is in ADR-0006 now, kept rather
    than lost. filesdb still owns the bytes on disk.

    `stored` is the name on disk, which is generated: what was uploaded is kept in
    `filename` for the download to be called by, and never used as a path."""

    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stored: Mapped[str] = mapped_column(String(72), nullable=False, unique=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    # Whether a visitor may see this one at all.
    #
    # The other way up from projects.private, and on purpose. A project is a piece
    # of writing about the collection and is worth reading by default; an upload is
    # whatever came out of a drawer, and the drawer holds receipts with an address
    # on them as readily as it holds a driver disk. So nothing is published until
    # somebody says it is, and the tick that says so is the only thing standing
    # between a scanned invoice and the open web (ADR-0009).
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    # Not columns. filesdb.with_links and with_tags hang these on the rows of a page
    # so that a list of files costs three queries and not three per file, and the
    # templates read them back. Declared for the type checker alone: SQLAlchemy
    # never sees this block, so nothing here is mapped, stored or migrated, and a
    # row that has not been through those two functions does not have them.
    if TYPE_CHECKING:
        assets: list[str]
        models: list[tuple[str, str, str]]
        model_pairs: set[tuple[str, str]]
        unfiled: bool
        tags: list[str]


class FileTag(Base):
    """One label on a file: `manual`, `driver`, `ROM dump`. `fold` is it normalised
    (case and spacing are how one word gets typed two ways); `tag` is it as
    written, for showing back.

    A label since 0039, and not an association: what a file is for is in
    `file_asset` and `file_model`. A tag that reads like the name of a machine is
    still only a tag."""

    __tablename__ = "file_tag"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(120), nullable=False)
    fold: Mapped[str] = mapped_column(String(120), nullable=False, index=True)


class FileAsset(Base):
    """A file about one particular unit: a receipt, a photograph of a repair, a
    ROM read off one board.

    `asset_id` is a plain column and not a foreign key, following ProjectAsset and
    for its reason: the register is two tables and what this names may be in
    either. Deleting the item takes the link with it and never the bytes -- a file
    left with no links is unfiled, which is a state the files page shows rather
    than a reason to delete anything (ADR-0006)."""

    __tablename__ = "file_asset"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("file_id", "asset_id", name="uq_file_asset_pair"),)


class FileModel(Base):
    """A file about every item of a model: a driver, a manual, a utility disk.

    `kind` says which sort of handle `model_key` is, because the register holds two
    sorts of thing (ADR-0020). `catalogue` is machines.yaml's stable key, held by a
    machine the catalogue names or the board out of one; `named` is the maker and
    the model as somebody wrote them, folded and joined -- `trident|tvga8900` --
    which is the only handle a part or a PC clone has. An item answers to both
    where it has both.

    `label` is that model as typed, since a folded key is not something to show
    anybody: a cache of what to print, never what to match on.

    Matching is equality on `model_key`. Containment is what let a tag of "16"
    reach half the register, and the key stored is the one made at the time: a
    change to how `filesdb.fold` folds must not quietly move a file."""

    __tablename__ = "file_model"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    model_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    __table_args__ = (
        UniqueConstraint("file_id", "kind", "model_key", name="uq_file_model_triple"),
    )


class LogEntry(Base):
    """A dated history entry for any asset (computer or part): automatic
    change records and free-text notes. asset_id is from the shared register, so
    it is a plain column rather than a foreign key to one table."""

    __tablename__ = "log_entry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str | None] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    kind: Mapped[str | None] = mapped_column(String(16), default="change")
    message: Mapped[str | None] = mapped_column(Text, default="")


class LogPhoto(Base):
    """A photograph hung on one history entry.

    The portrait on `computers.image` answers "which one is this?"; these answer
    "what happened to it?" -- the board before the recap, the crack in the case as
    it was found, the label under the lid that settled which revision it is. So
    they are not gallery photographs of the object and are never counted among
    them, and the entry's own message is their caption: a photograph of a repair
    with the repair written beside it needs nothing further said about it.

    Unlike log_entry's asset_id this is a real foreign key, because a log entry is
    a row in one table rather than an identity in the shared register, and the id
    here means nothing without it. The delete path still clears these by hand --
    it has to read `rel` before the rows go, since the files behind them cannot be
    rolled back.

    `rel` is the path under the images directory, and it lives in `log/` rather
    than in `computers/` or `parts/`. That is the whole of why this table can
    exist safely: those two folders are read by stem, so a photograph of a recap
    filed beside a part would be claimed as one of that part's gallery pictures
    and counted as its portrait.
    """

    __tablename__ = "log_photo"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("log_entry.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rel: Mapped[str] = mapped_column(String(255), nullable=False)


# --- projects: the work, as against the things it is done to -----------------
# A machine is something owned and a project is something intended, and the two
# are described by different facts: a Spectrum has a board issue and a ULA, and
# "recap the +2A" has a state, a list of jobs and a pile of things on order. So
# these are tables of their own rather than more columns on `computers`.
#
# What they share is the register. A project takes an asset id from the same
# allocator the two asset tables draw from, which is what lets it keep a history
# without a line of new code: log_entry is keyed by a plain asset id precisely
# because no one table owns the register, and a project is now a third thing that
# id can mean.


class Project(Base):
    """A piece of work: a repair, a build, a machine wanted and not yet found.

    It need own nothing. A project with no computers and no parts attached is the
    ordinary case at the start -- the idea comes before the hardware, and a plan to
    build a 486 exists for months before there is a 486 to point at. Which is why
    the assets are a table beside this one rather than columns in it, and why
    nothing here is required except the name.

    `status` is a slug from projects.STATUSES, not a label, for the reason
    ComputerRamModule.module is: the words on screen are free to be reworded
    without orphaning anybody's rows.

    Three dates, because they answer three questions and any of them can be
    unknown while the others are not. `started_at` is when work began, which is not
    when the project was thought of; `target_date` is when it is wanted by, which
    is a hope rather than a record; `finished_at` is when it was done, and is the
    only one that can be read off the history afterwards. A project can be finished
    without ever having been started -- the part turned up and it took an evening --
    and none of the three is inferred from another."""

    __tablename__ = "projects"
    asset_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="planned", server_default="planned"
    )
    summary: Mapped[str | None] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text, default="")
    started_at: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)
    finished_at: Mapped[date | None] = mapped_column(Date)
    # Whether this one is kept back from the public site.
    #
    # The register is a public catalogue with a login over the editing rather than
    # over the data, and a project is the one record here that can be either. What
    # is being built is worth reading about; what is wrong with a machine, in the
    # owner's own words, is not finished being decided and may never be. So it is a
    # property of the project rather than of the whole section, and a project can be
    # published later by clearing it.
    #
    # False by default, everywhere. The quick box used to set it true on the
    # argument that a line typed at a bench in five seconds has not been considered
    # for publication -- but the register is a public catalogue, what is wrong with
    # a machine is a good part of what is interesting about it, and that default was
    # undone by hand on nearly every project. So keeping one back is a decision now
    # rather than a starting point (ADR-0004); everything below is unchanged, and
    # is what a project that is meant to be unreadable still gets.
    #
    # This replaces the `project` / `project_note` pair that computers and parts
    # carried, which said the same thing about an item rather than about the work
    # (see migration 0031).
    private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


class ProjectAsset(Base):
    """One computer or part that a project is about.

    `asset_id` is a plain column and not a foreign key, for the reason log_entry's
    is: it names something in the shared register, and the register is two tables.
    Which of them holds it is looked up, exactly as /items/<id> looks it up.

    `project_id` is a real foreign key, because a project is a row in one table and
    a membership means nothing without it -- the same split AssetVariant and
    LogPhoto make for the same reason.

    One project to a thing (ADR-0016), which is what the unique constraint on
    `asset_id` says. It was many-to-many, on the argument that the same PSU can be
    wanted by two projects -- but a thing being in two places at once is a question
    ("which of these is it actually on?") rather than an answer, and the work on a
    thing is the work on a thing whichever project it was raised from. A project
    still holds many things; it is only the other direction that is now one.

    Still a join table rather than a column on the item, because the register is
    two tables and this is the one place that is already handled: a column would
    have to be added to computers and to parts, and every query would then ask both.

    `note` is why this one is in this project -- 'donor for the keyboard', 'needs
    the recap' -- which is a fact about the pairing rather than about either end of
    it, and so has nowhere else to live."""

    __tablename__ = "project_asset"
    __table_args__ = (UniqueConstraint("asset_id", name="uq_project_asset_item"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("projects.asset_id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    note: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")


class ProjectTask(Base):
    """One job, and whether it is done.

    Deliberately only a sentence and a tick. A task list that asks for a priority,
    an estimate and an owner is a task list nobody writes anything in, and there is
    one person here. What a job needs is to be written down in the words it will be
    recognised by and ticked when it is over.

    `done_at` is a date rather than a timestamp: the history already holds the
    minute anything happened, and what a finished job is worth remembering by is
    the day.

    `asset_id` is the thing the job is about, where it is about one. Optional
    because plenty of a project's jobs are not about any single item on it --
    'order the caps', 'find a service manual' -- and a column that insisted would
    turn those into a lie. Where it is set, the asset is one of the project's own
    members, which is what lets an item's page show its own jobs rather than the
    whole project's.

    A plain column with no foreign key, like project_asset.asset_id and for the
    same reason: the register is two tables, so there is no one table to point at.
    The delete paths clear these by hand."""

    __tablename__ = "project_task"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("projects.asset_id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str | None] = mapped_column(String(16), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    done_at: Mapped[date | None] = mapped_column(Date)


class ProjectOrder(Base):
    """Something bought for a project, and whether it has turned up.

    This is the one place in the register that records money. Everything else here
    describes what a thing is; an order describes a transaction, and what it cost
    is most of what there is to say about one. `cost_p` is an integer of pence for
    the reason every other quantity in this schema is an integer in a small unit
    named by the column suffix (_kb, _khz, _ns, _rpm): so it sorts and adds up
    exactly, which a float of pounds does not. NULL is a cost not recorded, which
    is not the same as free.

    `qty` multiplies it. The cost is the cost of the line as paid -- four SIMMs for
    twelve pounds is qty 4 and 1200, not 300 -- because that is the figure on the
    receipt, and dividing it to store a unit price would be inventing a number that
    was never quoted.

    Delivery is a flag and a date rather than a state machine. What is wanted from a
    pile of ordered things is which of them are still coming, and a tick answers it.

    Nothing here links to a part. When the Gotek arrives it is added to the register
    the ordinary way, and this row is ticked -- which keeps an order a note about
    a purchase rather than a half-made asset, and keeps the register a list of
    things that exist."""

    __tablename__ = "project_order"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("projects.asset_id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    supplier: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    url: Mapped[str | None] = mapped_column(Text, default="")
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    cost_p: Mapped[int | None] = mapped_column(Integer)
    ordered_at: Mapped[date | None] = mapped_column(Date)
    expected_at: Mapped[date | None] = mapped_column(Date)
    delivered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    delivered_at: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")


class PrintJob(Base):
    """One label waiting to be printed by an agent somewhere else (ADR-0025).

    The register is a server and the label printer is behind a broadband router,
    so there is no route from here to there: the agent asks for its jobs, and this
    row is what it is told.

    It holds a request to print an item, not a copy of one -- the label is rendered
    when it is fetched, so a correction made in the two minutes before the agent
    picks the job up is on the label that comes out, and the queue never becomes a
    second place the register's data lives.

    `asset_id` is a plain column and not a foreign key, as `log_entry`'s is: it is
    an identity in the shared register, which is three tables. An item deleted
    before its label prints leaves the job pointing at nothing, which is answered
    when the agent asks for the label rather than by a cascade -- the agent has to
    be told that this one will never work, and a row vanishing tells it nothing.

    `claimed_at` is a lease and not a receipt. An agent that takes a job and stops
    existing lets it fall back to the queue (printing.LEASE_SECONDS), because a
    label printed twice is a label and a job lost in silence is somebody standing
    at a printer wondering."""

    __tablename__ = "print_job"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    media: Mapped[str] = mapped_column(String(32), nullable=False)
    fmt: Mapped[str] = mapped_column(String(8), nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued", index=True
    )
    error: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Setting(Base):
    """One thing the owner prefers, as against one thing that is true of the
    collection (ADR-0023).

    A key and a value rather than a column apiece, because the page they are edited
    on is expected to grow and a migration per preference would be a tax on exactly
    the thing it is meant to make cheap. What each key means -- its label, its
    default, the kind of control it is asked with, the environment variable that
    pins it -- is in `settings.py`, which is also the only thing that writes here.

    An absent row is not a missing value: every setting has a default in that
    module, so an empty table is a working site and nothing has to be seeded
    (ADR-0002).

    `name` rather than `key`: KEY is reserved in MariaDB, and a column that has to
    be quoted everywhere it is named is a column that will one day be named
    somewhere that forgets."""

    __tablename__ = "setting"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class Location(Base):
    """A place something has been kept, remembered so it can be offered again
    (ADR-0027).

    The register's first stored vocabulary, and it exists because the derived pick
    lists cannot cover this one field. Every other list is the register asked a
    question -- `pages._answers_given` counts the spellings in a column and offers
    the commonest back -- and that works for a source, which is written once and
    stays true. A location stops being true the moment the thing is moved, so the
    last item out of a crate takes the crate's spelling with it, and the crate is
    typed again a month later as something not quite the same.

    So: a row per location ever saved, holding only what the derived list has lost.
    The suggestions are still the union of the two, in-use first, which is what
    keeps this table optional -- empty or deleted, the forms go on working.

    Written only while `remember_locations` is on, and deleted outright when it is
    turned off. Ignoring rows the owner has asked the register to forget would be
    answering a different question from the one the switch asks.

    `name` is the primary key, for the reason Setting.name is one: there is nothing
    else to identify a place by, and a surrogate id would only let the same place in
    twice. MariaDB's collation folds case here, which is wanted -- one crate, one
    row, whichever way it was capitalised on the day."""

    __tablename__ = "location"
    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    # When it was last saved against something, which is the order the remembered
    # half of the pick list is offered in: the crate filled last week is a likelier
    # answer than one nothing has gone into since 2019.
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
