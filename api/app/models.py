"""ORM tables. One shared asset register across computers + parts. A part's
computer_id links it to a computer's asset_id, and parent_id to the part it is
mounted on; both are real foreign keys, NULL when the part stands alone. Deleting
a computer or a host part unlinks what pointed at it rather than orphaning it.

The column set began as a mirror of the flat-file system's CSV schema, where
everything was a string; quantities and dates are being given real types as the
data proves clean enough to convert."""
from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Integer,
                        SmallInteger, String, Text, UniqueConstraint)

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
    # What the maker stamped on this particular one, as against the model, which is
    # what it is one of. The only identity field that is never true of a second
    # object -- which is why a duplicate does not carry it across, and why it is
    # worth having: a machine can be looked up by the number on its own back, and a
    # warranty date, a factory or a production run can be read off it later by
    # somebody who knows how.
    serial = Column(String(64), default="")
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
    # Whether this is one of the things waiting to be worked on, and what the plan
    # is. The pair sits in the same relation to each other as disposed and
    # disposed_note: a flag the whole register can be asked at once, and the free
    # text that is the actual content of the intention -- "recap, one leg already
    # green", "needs a PSU before it can even be tried".
    #
    # A plan is worth a column of its own rather than a line in `notes` because it
    # is the one thing written here that is about the future. Everything else the
    # record holds is a description of what is, and a description can be read in
    # any order; a list of intentions is only useful gathered up, and a sentence
    # buried in the middle of a paragraph about a machine's condition cannot be
    # gathered.
    #
    # Both are private, in a way nothing else on this table is: an item page is
    # public and these two are left out of it, out of the search index and out of
    # the history unless somebody is logged in (see main._haystack and the panel
    # in _photocol.html). What is here is a description of the collection and can
    # be read by anybody; what is planned for it is not finished being decided.
    project = Column(Boolean, nullable=False, default=False, server_default="0")
    project_note = Column(Text, nullable=False, default="", server_default="")


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
    # The number on this one, for the reason a machine has one (see Computer.serial).
    # A part is where it matters most often: two identical SIMMs are told apart by
    # nothing else, and a drive's own label is the only place its date code lives.
    serial = Column(String(64), default="")
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
    # The same pair the machines have, and for the same reason (see
    # Computer.project). A part is if anything where it comes up more often: a
    # recap is a thing done to a board, a belt is a thing done to a drive, and a
    # capacitor kit ordered for one card is a plan about that card rather than
    # about whatever it is currently plugged into.
    project = Column(Boolean, nullable=False, default=False, server_default="0")
    project_note = Column(Text, nullable=False, default="", server_default="")


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
    part_id = _part_fk()
    tech = Column(String(64))
    panel = Column(String(64))
    screen_in_tenths = Column(Integer)
    aspect = Column(String(16))
    resolution = Column(String(64))
    refresh = Column(String(255))
    sync = Column(String(255))
    dot_pitch_um = Column(Integer)
    interface = Column(String(255))
    picture = Column(String(32))
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
    id = Column(Integer, primary_key=True, autoincrement=True)
    log_id = Column(Integer, ForeignKey("log_entry.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    rel = Column(String(255), nullable=False)


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
    asset_id = Column(String(16), primary_key=True)
    name = Column(String(255), nullable=False, default="", server_default="")
    status = Column(String(16), nullable=False, default="planned",
                    server_default="planned")
    summary = Column(Text, default="")
    notes = Column(Text, default="")
    started_at = Column(Date)
    target_date = Column(Date)
    finished_at = Column(Date)


class ProjectAsset(Base):
    """One computer or part that a project is about.

    `asset_id` is a plain column and not a foreign key, for the reason log_entry's
    is: it names something in the shared register, and the register is two tables.
    Which of them holds it is looked up, exactly as /items/<id> looks it up.

    `project_id` is a real foreign key, because a project is a row in one table and
    a membership means nothing without it -- the same split AssetVariant and
    LogPhoto make for the same reason.

    Many-to-many on purpose: the same PSU can be wanted by two projects, and a
    machine being restored is also the machine the spare board is destined for.
    The unique constraint is on the pair, so a thing is in a project once however
    many times it is added.

    `note` is why this one is in this project -- 'donor for the keyboard', 'needs
    the recap' -- which is a fact about the pairing rather than about either end of
    it, and so has nowhere else to live."""
    __tablename__ = "project_asset"
    __table_args__ = (UniqueConstraint("project_id", "asset_id",
                                       name="uq_project_asset"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(16),
                        ForeignKey("projects.asset_id", ondelete="CASCADE"),
                        nullable=False, index=True)
    asset_id = Column(String(16), nullable=False, index=True)
    note = Column(String(255), nullable=False, default="", server_default="")


class ProjectTask(Base):
    """One job, and whether it is done.

    Deliberately only a sentence and a tick. A task list that asks for a priority,
    an estimate and an owner is a task list nobody writes anything in, and there is
    one person here. What a job needs is to be written down in the words it will be
    recognised by and ticked when it is over.

    `done_at` is a date rather than a timestamp: the history already holds the
    minute anything happened, and what a finished job is worth remembering by is
    the day."""
    __tablename__ = "project_task"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(16),
                        ForeignKey("projects.asset_id", ondelete="CASCADE"),
                        nullable=False, index=True)
    text = Column(Text, nullable=False, default="")
    done = Column(Boolean, nullable=False, default=False, server_default="0")
    done_at = Column(Date)


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
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(16),
                        ForeignKey("projects.asset_id", ondelete="CASCADE"),
                        nullable=False, index=True)
    description = Column(String(255), nullable=False, default="")
    supplier = Column(String(255), nullable=False, default="", server_default="")
    url = Column(Text, default="")
    qty = Column(Integer, nullable=False, default=1, server_default="1")
    cost_p = Column(Integer)
    ordered_at = Column(Date)
    expected_at = Column(Date)
    delivered = Column(Boolean, nullable=False, default=False, server_default="0")
    delivered_at = Column(Date)
    note = Column(String(255), nullable=False, default="", server_default="")
