"""The catalogue of known home machines, and the variations each was built in.

A PC is described by what is fitted in it -- a board, a card, a drive -- and the
register asks for those one at a time, each with its own asset tag. A home
computer or a console is not that sort of object. A ZX Spectrum is a sealed
machine that was built in a handful of documented forms, and what a collector
records about one is which of those forms it is: which board issue, which ULA,
16K or 48K, rubber keys or moulded ones. None of that is a part to tag, and none
of it means much except against a list of what was made.

So this module is the list. Families, the models in each, and for every model the
standard memory sizes, the board issues, the case and keyboard styles, the regions
it was sold in, and the chip sockets with the variants that turn up in them. It is
pure data and the lookups over it -- no database, no HTTP -- the way entry.py
holds the guided-entry vocabularies; machinedb owns the storage, as ramdb does for
a machine's memory.

Two things to hold on to when adding to it:

  * Every list names what is commonly seen, not everything that exists. The form
    offers them as suggestions beside a box that still takes whatever is typed --
    the rule the drive pickers already follow -- because a catalogue that refused
    the odd machine would be wrong more often than the machine was. A late board
    nobody has written up, a chip replaced in a repair, a Spectrum+ converted from
    a rubber-key machine: all of those are recorded by typing them.
  * `key` is the stable slug and is the only thing stored. A label, a note, a
    chip's part number and even a model's name can be corrected without orphaning
    a record; a key cannot be changed without a migration. This is the lesson
    migration 0011 wrote down about memory modules, applied before it can be
    learned twice.

What a machine's own record holds is in machinedb: the model key, the board
issue, the style, the region, and one chip variant per socket. The rest of what is
here -- names, years, CPU, notes -- is the catalogue's, read fresh every time, so
correcting an entry corrects every machine filed under it.
"""
from __future__ import annotations

from . import entry


def _chip(role, label, variants, note=""):
    """One socket a model's record can name a chip for. `role` is the stable slug
    that gets stored, `label` is what the form and the page call it."""
    return {"role": role, "label": label, "variants": list(variants), "note": note}


# --- chips and vocabularies shared inside a family --------------------------

# The Z80 was second-sourced by four foundries and Sinclair, Amstrad and Acorn all
# bought from whoever was cheapest that month. Nothing about the machine changes
# with the marking, which is exactly why it is worth writing down: it is one of the
# few things about a sealed machine you can only know by opening it.
_Z80 = ["Zilog Z80A", "NEC D780C-1", "SGS Z8400AB1", "Sharp LH0080A",
        "Mostek MK3880N-4", "Toshiba TMPZ84C00AP"]
_AY = ["General Instrument AY-3-8912", "Yamaha YM2149F"]

_SPECTRUM_ULA = ["Ferranti 5C102E", "Ferranti 5C112E", "Ferranti 6C001E-6",
                 "Ferranti 6C001E-7", "Ferranti 7K010E-5"]
_SPECTRUM_ISSUES = ["Issue 1", "Issue 2", "Issue 3", "Issue 3B", "Issue 4A",
                    "Issue 4B", "Issue 5", "Issue 6A"]

_C64_CHIPS = [
    _chip("cpu", "CPU", ["MOS 6510", "MOS 6510R4", "MOS 8500"],
          "the 6510 in a breadbin, the 8500 in the C64C and late boards"),
    _chip("vic", "VIC-II", ["MOS 6567R56A", "MOS 6567R8", "MOS 6569R1",
                            "MOS 6569R3", "MOS 6569R4", "MOS 6569R5",
                            "MOS 8562", "MOS 8565"],
          "6569 is the PAL part and 6567 the NTSC one; 8565/8562 are the HMOS-II "
          "chips of the later boards"),
    _chip("sid", "SID", ["MOS 6581", "MOS 6581R2", "MOS 6581R3", "MOS 6581R4",
                         "MOS 6581R4AR", "MOS 8580R5"],
          "the one chip people choose a machine by: 6581 in a breadbin, 8580 in "
          "the C64C"),
    _chip("cia", "CIA", ["MOS 6526", "MOS 6526A", "MOS 8521"],
          "two of them, and both are usually the same part"),
    _chip("pla", "PLA", ["MOS 906114-01", "MOS 252535-01", "MOS 251715-01"],
          "the chip that runs hot and takes the machine with it when it goes; "
          "251715-01 is the 250469 board's combined part"),
    _chip("kernal", "Kernal ROM", ["901227-01", "901227-02", "901227-03",
                                   "251913-01"],
          "-01 is the first Kernal, -03 the one nearly every machine has, and "
          "251913-01 the C64C's combined ROM"),
]
_C64_BREADBIN_BOARDS = ["ASSY 326298", "ASSY 250407", "ASSY 250425",
                        "ASSY 250466"]
_C64C_BOARDS = ["ASSY 250466", "ASSY 250469", "KU-14194HB"]

_TED_CHIPS = [
    _chip("cpu", "CPU", ["MOS 7501", "MOS 8501"]),
    _chip("ted", "TED", ["MOS 7360", "MOS 8360"],
          "video, sound and the timers in one chip -- the machine is named for "
          "what it has instead of a VIC-II and a SID"),
    _chip("pla", "PLA", ["MOS 251641-02"]),
]

_ATARI8_CHIPS = [
    _chip("cpu", "CPU", ["MOS 6502B", "Synertek 6502B", "MOS 6502C (Sally)"],
          "Sally is the 6502C with the halt line the later machines need"),
    _chip("antic", "ANTIC", ["C012296", "C021697"],
          "the display list processor; the second number is the later mask"),
    _chip("gtia", "GTIA", ["C010444 (CTIA)", "C014805", "C014889"],
          "an early 400/800 has the CTIA, which has no GTIA graphics modes"),
    _chip("pokey", "POKEY", ["C012294", "C012294B"],
          "sound, the keyboard scan and the serial port"),
    _chip("pia", "PIA", ["C014795 (6520)", "MOS 6520"],
          "the joystick ports"),
]

_ST_CHIPS = [
    _chip("cpu", "CPU", ["Motorola MC68000-8", "Signetics SCC68000"]),
    _chip("shifter", "Shifter", ["C025912", "C300589 (STE)"],
          "the video shifter; the STE part is the one with the palette the ST "
          "has not got"),
    _chip("glue", "GLUE", ["C025913", "combined in the STE's GST MCU"]),
    _chip("mmu", "MMU", ["C025912-002", "combined in the STE's GST MCU"]),
    _chip("psg", "Sound", ["Yamaha YM2149F"]),
    _chip("tos", "TOS ROM", ["TOS 1.00", "TOS 1.02", "TOS 1.04", "TOS 1.62",
                             "TOS 2.06"],
          "on socketed ROMs in most machines, so this is the one thing on the "
          "list that may not be what it left the factory with"),
]

_AMIGA_OCS_CHIPS = [
    _chip("cpu", "CPU", ["Motorola MC68000-7", "Motorola MC68000-14 (upgrade)"]),
    _chip("agnus", "Agnus", ["8370 (NTSC OCS)", "8371 (PAL OCS)",
                             "8372A (ECS, 1MB)", "8375 (ECS, 2MB)"],
          "which Agnus decides how much chip RAM the machine can see at all"),
    _chip("denise", "Denise", ["8362", "8373 (Super Denise)"]),
    _chip("paula", "Paula", ["8364"]),
    _chip("gary", "Gary", ["5719", "Gayle (A600/A1200)"]),
    _chip("kickstart", "Kickstart ROM", ["1.2", "1.3", "2.04", "2.05", "3.0",
                                         "3.1"],
          "socketed, and swapped often enough that it is worth recording what "
          "is in there now"),
]

_CPC_CHIPS = [
    _chip("cpu", "CPU", _Z80),
    _chip("gate-array", "Gate Array", ["Amstrad 40007", "Amstrad 40008",
                                       "Amstrad 40010", "Amstrad 40489 (ASIC)"],
          "video and memory banking; the ASIC of a Plus machine does this and "
          "the CRTC's job together"),
    _chip("crtc", "CRTC", ["Hitachi HD6845S (type 0)", "UMC UM6845R (type 1)",
                           "Motorola MC6845 (type 2)",
                           "Amstrad pre-ASIC (type 3)",
                           "Amstrad 40489 ASIC (type 4)"],
          "the type number is what software cares about -- the border and split "
          "tricks behave differently on each"),
    _chip("psg", "Sound", _AY),
    _chip("ppi", "PPI", ["NEC D8255AC-5", "Intel 8255A-5"]),
]

_BBC_CHIPS = [
    _chip("cpu", "CPU", ["Rockwell R6502A", "Synertek SY6502A", "MOS 6502A"]),
    _chip("video-ula", "Video ULA", ["Ferranti 5C022E", "VideoProc (VIDPROC)"],
          "the ULA that fails and takes the display with it; VIDPROC is the "
          "modern stand-in"),
    _chip("serial-ula", "Serial ULA", ["Ferranti 2C199E"],
          "the cassette and RS423 side, and the other ULA that fails"),
    _chip("crtc", "CRTC", ["Hitachi HD6845", "Motorola MC6845",
                           "Synertek SY6845"]),
    _chip("fdc", "Floppy controller", ["Intel 8271", "WD1770", "WD1772",
                                       "none fitted"],
          "the 8271 of an early board, the 1770 of a later one, or an empty "
          "socket on a machine sold without discs"),
    _chip("os-rom", "OS ROM", ["OS 0.10", "OS 1.00", "OS 1.20", "OS 2.00 (B+)",
                               "MOS 3.20", "MOS 3.50"]),
    _chip("basic-rom", "BASIC ROM", ["BASIC I", "BASIC II", "BASIC IV"]),
]

_MEGADRIVE_BOARDS = ["VA0", "VA1", "VA2", "VA3", "VA4", "VA5", "VA6", "VA6.8",
                     "VA7"]
_MEGADRIVE_CHIPS = [
    _chip("cpu", "CPU", ["Motorola MC68000", "Signetics SCC68000",
                         "Hitachi HD68HC000"]),
    _chip("z80", "Sound CPU", ["Zilog Z80A", "Sharp LH5080A",
                               "integrated in the ASIC"]),
    _chip("vdp", "VDP", ["Sega 315-5313", "Sega 315-5313A",
                         "Sega 315-5660 (Model 2 ASIC)"]),
    _chip("fm", "FM sound", ["Yamaha YM2612", "Yamaha YM3438",
                             "integrated in the ASIC"],
          "the discrete YM2612 is the one people buy a Model 1 for; the YM3438 "
          "and the ASIC's version are cleaner and thinner"),
    _chip("amp", "Amplifier", ["Sanyo LA6510", "Sony CXA1034", "Rohm BA10324"],
          "part of why two Model 1s of different revisions do not sound alike"),
]


# --- the catalogue ----------------------------------------------------------
# One entry per family, each holding what its models share (the maker, the regions
# it sold in, the chip sockets) and then the models themselves. A model's own
# fields win over its family's, and a chip it names replaces the family's chip for
# that socket rather than adding a second one.
#
# Per model:
#   key       the stable slug; stored, never rendered
#   model     the name it is known by, which fills the machine's model field
#   year      the year that model appeared
#   cpu       what goes in the CPU field, in the register's maker model-MHz form
#   chassis   the shape of the thing, in the words the chassis field uses
#   os        the ROM or system it boots into
#   ram       [(label, KB)] of the sizes it was sold with, offered on the memory
#             box; each label has to be one entry.to_kb can read back
#   issues    the board issues or revisions, as they are marked or written up
#   styles    the case and keyboard variations, which is what tells two otherwise
#             identical machines apart at a glance
#   chips     sockets beyond the family's, or replacements for them
FAMILIES = [
    {
        "key": "sinclair",
        "name": "Sinclair ZX",
        "manufacturer": "Sinclair",
        "regions": ["PAL (UK/Europe)", "NTSC (Timex/US)"],
        "chips": [
            _chip("cpu", "CPU", _Z80,
                  "four foundries made it and Sinclair bought from whoever was "
                  "cheapest; nothing but the marking changes"),
            _chip("ula", "ULA", _SPECTRUM_ULA,
                  "the heart of the machine and the part that kills it: the "
                  "number under the heatsink is worth writing down before it is "
                  "needed"),
        ],
        "models": [
            {"key": "zx80", "model": "ZX80", "year": 1980,
             "cpu": "NEC D780C-3.25", "chassis": "white wedge, membrane keyboard",
             "os": "4K ZX80 BASIC ROM", "ram": [("1K", 1), ("16K", 16)],
             "issues": [], "styles": ["membrane keyboard"],
             "chips": [_chip("ula", "ULA", [],
                             "there isn't one -- the ZX80 does it in TTL, which "
                             "is why the board is so busy")]},
            {"key": "zx81", "model": "ZX81", "year": 1981,
             "cpu": "NEC D780C-3.25", "chassis": "black wedge, membrane keyboard",
             "os": "8K ZX81 BASIC ROM", "ram": [("1K", 1), ("16K", 16)],
             "issues": ["Issue 1", "Issue 3"],
             "styles": ["membrane keyboard", "Timex Sinclair 1000"],
             "chips": [_chip("ula", "ULA", ["Ferranti 2C158E", "Ferranti 2C184E"],
                             "the one chip that made a ZX81 out of a ZX80's "
                             "worth of TTL")]},
            {"key": "zx-spectrum-16k", "model": "ZX Spectrum 16K", "year": 1982,
             "cpu": "Zilog Z80A-3.5", "chassis": "wedge, rubber keys",
             "os": "Sinclair BASIC (48K ROM)", "ram": [("16K", 16)],
             "issues": _SPECTRUM_ISSUES[:4], "styles": ["rubber keys"]},
            {"key": "zx-spectrum-48k", "model": "ZX Spectrum 48K", "year": 1982,
             "cpu": "Zilog Z80A-3.5", "chassis": "wedge, rubber keys",
             "os": "Sinclair BASIC (48K ROM)",
             "ram": [("48K", 48), ("16K", 16)],
             "issues": _SPECTRUM_ISSUES,
             "styles": ["rubber keys", "16K board upgraded to 48K"]},
            {"key": "zx-spectrum-plus", "model": "ZX Spectrum+", "year": 1984,
             "cpu": "Zilog Z80A-3.5", "chassis": "wedge, moulded keys",
             "os": "Sinclair BASIC (48K ROM)", "ram": [("48K", 48)],
             "issues": ["Issue 4A", "Issue 4B", "Issue 6A"],
             "styles": ["moulded keys", "rubber-key machine in a + case"]},
            {"key": "zx-spectrum-128", "model": "ZX Spectrum 128", "year": 1986,
             "cpu": "Zilog Z80A-3.5", "chassis": "wedge with heatsink (toastrack)",
             "os": "128 BASIC / 48 BASIC", "ram": [("128K", 128)],
             "issues": [], "styles": ["toastrack", "Spanish 128 (Investronica)"],
             "chips": [_chip("psg", "Sound", _AY,
                             "the three-channel chip that is the whole reason a "
                             "128 sounds like a 128")]},
            {"key": "zx-spectrum-plus2", "model": "ZX Spectrum +2", "year": 1986,
             "manufacturer": "Amstrad", "cpu": "Zilog Z80A-3.5",
             "chassis": "grey case, built-in tape", "os": "128 BASIC / 48 BASIC",
             "ram": [("128K", 128)], "issues": [], "styles": ["grey case"],
             "chips": [_chip("psg", "Sound", _AY)]},
            {"key": "zx-spectrum-plus2a", "model": "ZX Spectrum +2A", "year": 1987,
             "manufacturer": "Amstrad", "cpu": "Zilog Z80A-3.5",
             "chassis": "black case, built-in tape", "os": "128 BASIC / +3 BASIC",
             "ram": [("128K", 128)], "issues": [],
             "styles": ["black case", "+2B (later production)"],
             "chips": [
                 _chip("ula", "ASIC", ["Amstrad 40056"],
                       "Amstrad's gate array, which does the ULA's job and the "
                       "memory decoding with it"),
                 _chip("psg", "Sound", _AY)]},
            {"key": "zx-spectrum-plus3", "model": "ZX Spectrum +3", "year": 1987,
             "manufacturer": "Amstrad", "cpu": "Zilog Z80A-3.5",
             "chassis": 'black case, built-in 3" floppy',
             "os": "+3 BASIC / +3DOS / CP/M", "ram": [("128K", 128)],
             "issues": [], "styles": ["black case", "+3B (later production)"],
             "chips": [
                 _chip("ula", "ASIC", ["Amstrad 40056"]),
                 _chip("psg", "Sound", _AY),
                 _chip("fdc", "Floppy controller", ["NEC D765AC", "UMC UM8272A"]),
                 _chip("rom", "ROM", ["v4.0", "v4.1"],
                       "v4.1 fixed the bugs v4.0 shipped with; a machine can "
                       "have either")]},
        ],
    },
    {
        "key": "commodore-8bit",
        "name": "Commodore 8-bit",
        "manufacturer": "Commodore",
        "regions": ["PAL", "NTSC"],
        "chips": _C64_CHIPS,
        "models": [
            {"key": "vic-20", "model": "VIC-20", "year": 1980,
             "cpu": "MOS 6502A-1.02", "chassis": "breadbin",
             "os": "Commodore BASIC 2.0", "ram": [("5K", 5)],
             "issues": ["ASSY 324003", "ASSY 250403 (VIC-20CR)"],
             "styles": ["VIC-20 (1980 case)", "VIC-20CR"],
             "chips": [
                 _chip("cpu", "CPU", ["MOS 6502", "MOS 6502A"]),
                 _chip("vic", "VIC", ["MOS 6560 (NTSC)", "MOS 6561 (PAL)"]),
                 _chip("via", "VIA", ["MOS 6522"], "two of them"),
                 _chip("sid", "SID", [], "there is no SID -- the VIC makes the "
                                        "sound"),
                 _chip("cia", "CIA", []),
                 _chip("pla", "PLA", []),
                 _chip("kernal", "Kernal ROM", ["901486-01", "901486-06",
                                                "901486-07"])]},
            {"key": "c64", "model": "Commodore 64", "year": 1982,
             "cpu": "MOS 6510-1.02", "chassis": "breadbin",
             "os": "Commodore BASIC 2.0", "ram": [("64K", 64)],
             "issues": _C64_BREADBIN_BOARDS,
             "styles": ["silver label", "rainbow label", "Aldi C64 (short board)"]},
            {"key": "c64c", "model": "Commodore 64C", "year": 1986,
             "cpu": "MOS 8500-1.02", "chassis": "wedge (C64C)",
             "os": "Commodore BASIC 2.0", "ram": [("64K", 64)],
             "issues": _C64C_BOARDS, "styles": ["C64C", "C64G"]},
            {"key": "sx-64", "model": "Commodore SX-64", "year": 1984,
             "cpu": "MOS 6510-1.02", "chassis": "luggable, built-in 1541",
             "os": "Commodore BASIC 2.0", "ram": [("64K", 64)],
             "issues": ["ASSY 250425"], "styles": ["SX-64 (single drive)"]},
            {"key": "c16", "model": "Commodore 16", "year": 1984,
             "cpu": "MOS 7501", "chassis": "dark breadbin",
             "os": "Commodore BASIC 3.5", "ram": [("16K", 16)],
             "issues": [], "styles": ["C16 (dark case)", "C116 (rubber keys)"],
             "chips": [*_TED_CHIPS,
                        _chip("vic", "VIC-II", []), _chip("sid", "SID", []),
                        _chip("cia", "CIA", []),
                        _chip("kernal", "Kernal ROM",
                              ["318004-05", "318005-05"])]},
            {"key": "plus4", "model": "Commodore Plus/4", "year": 1984,
             "cpu": "MOS 7501", "chassis": "wedge, dark case",
             "os": "Commodore BASIC 3.5 with 3-plus-1", "ram": [("64K", 64)],
             "issues": [], "styles": ["Plus/4"],
             "chips": [*_TED_CHIPS,
                        _chip("vic", "VIC-II", []), _chip("sid", "SID", []),
                        _chip("cia", "CIA", []),
                        _chip("acia", "ACIA", ["MOS 6551"]),
                        _chip("kernal", "Kernal ROM",
                              ["318005-05", "318006-01"])]},
            {"key": "c128", "model": "Commodore 128", "year": 1985,
             "cpu": "MOS 8502-2.04", "chassis": "wedge with numeric keypad",
             "os": "Commodore BASIC 7.0 / CP/M 3.0", "ram": [("128K", 128)],
             "issues": [], "styles": ["C128 (flat case)"],
             "chips": [
                 _chip("cpu", "CPU", ["MOS 8502"]),
                 _chip("cpu2", "Z80", ["Zilog Z80A", "MOS 8502-paired Z80B"],
                       "the second processor, for the CP/M side"),
                 _chip("vic", "VIC-IIe", ["MOS 8564 (NTSC)", "MOS 8566 (PAL)"]),
                 _chip("vdc", "VDC", ["MOS 8563", "MOS 8568"],
                       "the 80-column chip, and the one that runs hottest"),
                 _chip("sid", "SID", ["MOS 6581", "MOS 8580R5"]),
                 _chip("cia", "CIA", ["MOS 6526", "MOS 8521"]),
                 _chip("pla", "PLA", ["MOS 8721"]),
                 _chip("kernal", "Kernal ROM", ["318020-03", "318020-05"])]},
            {"key": "c128d", "model": "Commodore 128D", "year": 1986,
             "cpu": "MOS 8502-2.04", "chassis": "desktop with built-in 1571",
             "os": "Commodore BASIC 7.0 / CP/M 3.0", "ram": [("128K", 128)],
             "issues": [], "styles": ["plastic 128D", "metal 128DCR"],
             "chips": [
                 _chip("cpu", "CPU", ["MOS 8502"]),
                 _chip("vic", "VIC-IIe", ["MOS 8564 (NTSC)", "MOS 8566 (PAL)"]),
                 _chip("vdc", "VDC", ["MOS 8563", "MOS 8568"]),
                 _chip("sid", "SID", ["MOS 6581", "MOS 8580R5"]),
                 _chip("cia", "CIA", ["MOS 6526", "MOS 8521"]),
                 _chip("pla", "PLA", ["MOS 8721"]),
                 _chip("kernal", "Kernal ROM", ["318020-03", "318020-05"])]},
        ],
    },
    {
        "key": "amiga",
        "name": "Commodore Amiga",
        "manufacturer": "Commodore",
        "regions": ["PAL", "NTSC"],
        "chips": _AMIGA_OCS_CHIPS,
        "models": [
            {"key": "amiga-500", "model": "Amiga 500", "year": 1987,
             "cpu": "Motorola 68000-7.09", "chassis": "wedge, built-in floppy",
             "os": "Kickstart / Workbench",
             "ram": [("512K", 512), ("1MB", 1024)],
             "issues": ["Rev 3", "Rev 5", "Rev 6A", "Rev 8A"],
             "styles": ["A500"]},
            {"key": "amiga-500-plus", "model": "Amiga 500+", "year": 1991,
             "cpu": "Motorola 68000-7.09", "chassis": "wedge, built-in floppy",
             "os": "Kickstart 2.04 / Workbench 2.0",
             "ram": [("1MB", 1024), ("2MB", 2048)],
             "issues": ["Rev 8A.1"], "styles": ["A500+"],
             "chips": [_chip("agnus", "Agnus", ["8375 (ECS, 2MB)"]),
                       _chip("denise", "Denise", ["8373 (Super Denise)"]),
                       _chip("kickstart", "Kickstart ROM", ["2.04"])]},
            {"key": "amiga-600", "model": "Amiga 600", "year": 1992,
             "cpu": "Motorola 68000-7.09", "chassis": "compact, built-in floppy",
             "os": "Kickstart 2.05 / Workbench 2.1",
             "ram": [("1MB", 1024), ("2MB", 2048)],
             "issues": ["Rev 1.5"], "styles": ["A600", "A600HD"],
             "chips": [_chip("agnus", "Agnus", ["8375 (ECS, 2MB)"]),
                       _chip("denise", "Denise", ["8373 (Super Denise)"]),
                       _chip("gary", "Gayle", ["Gayle"]),
                       _chip("kickstart", "Kickstart ROM", ["2.05"])]},
            {"key": "amiga-1200", "model": "Amiga 1200", "year": 1992,
             "cpu": "Motorola 68EC020-14.19",
             "chassis": "wedge, built-in floppy",
             "os": "Kickstart 3.0 / Workbench 3.0",
             "ram": [("2MB", 2048)],
             "issues": ["Rev 1A", "Rev 1D1", "Rev 1D4", "Rev 2B"],
             "styles": ["A1200"],
             "chips": [
                 _chip("cpu", "CPU", ["Motorola MC68EC020-14"]),
                 _chip("agnus", "Alice", ["AGA Alice"]),
                 _chip("denise", "Lisa", ["AGA Lisa"]),
                 _chip("paula", "Paula", ["8364"]),
                 _chip("gary", "Gayle", ["Gayle"]),
                 _chip("kickstart", "Kickstart ROM", ["3.0", "3.1"])]},
        ],
    },
    {
        "key": "atari-8bit",
        "name": "Atari 8-bit",
        "manufacturer": "Atari",
        "regions": ["PAL", "NTSC"],
        "chips": _ATARI8_CHIPS,
        "models": [
            {"key": "atari-400", "model": "Atari 400", "year": 1979,
             "cpu": "MOS 6502B-1.79", "chassis": "wedge, membrane keyboard",
             "os": "Atari OS ROM", "ram": [("8K", 8), ("16K", 16)],
             "issues": [], "styles": ["membrane keyboard"],
             "chips": [
                 _chip("os-rom", "OS ROM", ["Rev A", "Rev B"])]},
            {"key": "atari-800", "model": "Atari 800", "year": 1979,
             "cpu": "MOS 6502B-1.79", "chassis": "desktop, two cartridge slots",
             "os": "Atari OS ROM",
             "ram": [("8K", 8), ("16K", 16), ("48K", 48)],
             "issues": [], "styles": ["Atari 800"],
             "chips": [
                 _chip("os-rom", "OS ROM", ["Rev A", "Rev B"])]},
            {"key": "atari-600xl", "model": "Atari 600XL", "year": 1983,
             "cpu": "MOS 6502C-1.79", "chassis": "XL wedge",
             "os": "Atari OS Rev 2", "ram": [("16K", 16), ("64K", 64)],
             "issues": [], "styles": ["600XL"],
             "chips": [
                 _chip("freddie", "FREDDIE", ["C061618", "not fitted"],
                       "the XL/XE memory controller; the earliest 600XL boards "
                       "do without it"),
                 _chip("os-rom", "OS ROM", ["Rev 2 (XL)", "Rev 3 (XE)"])]},
            {"key": "atari-800xl", "model": "Atari 800XL", "year": 1983,
             "cpu": "MOS 6502C-1.79", "chassis": "XL wedge",
             "os": "Atari OS Rev 2", "ram": [("64K", 64)],
             "issues": [], "styles": ["800XL", "800XLF (later board)"],
             "chips": [
                 _chip("freddie", "FREDDIE", ["C061618"]),
                 _chip("os-rom", "OS ROM", ["Rev 2 (XL)", "Rev 3 (XE)"])]},
            {"key": "atari-65xe", "model": "Atari 65XE", "year": 1985,
             "cpu": "MOS 6502C-1.79", "chassis": "XE wedge",
             "os": "Atari OS Rev 3", "ram": [("64K", 64)],
             "issues": [], "styles": ["65XE", "800XE (Eastern Europe)"],
             "chips": [
                 _chip("freddie", "FREDDIE", ["C061618"]),
                 _chip("os-rom", "OS ROM", ["Rev 3 (XE)"])]},
            {"key": "atari-130xe", "model": "Atari 130XE", "year": 1985,
             "cpu": "MOS 6502C-1.79", "chassis": "XE wedge",
             "os": "Atari OS Rev 3", "ram": [("128K", 128)],
             "issues": [], "styles": ["130XE"],
             "chips": [
                 _chip("freddie", "FREDDIE", ["C061618"]),
                 _chip("os-rom", "OS ROM", ["Rev 3 (XE)"])]},
            {"key": "atari-xegs", "model": "Atari XE Game System", "year": 1987,
             "cpu": "MOS 6502C-1.79", "chassis": "console with detachable keyboard",
             "os": "Atari OS Rev 4 with Missile Command", "ram": [("64K", 64)],
             "issues": [], "styles": ["XEGS"],
             "chips": [
                 _chip("freddie", "FREDDIE", ["C061618"]),
                 _chip("os-rom", "OS ROM", ["Rev 4 (XEGS)"])]},
        ],
    },
    {
        "key": "atari-consoles",
        "name": "Atari consoles",
        "manufacturer": "Atari",
        "regions": ["PAL", "NTSC", "SECAM"],
        "chips": [],
        "models": [
            {"key": "atari-2600", "model": "Atari 2600", "year": 1977,
             "cpu": "MOS 6507-1.19", "chassis": "console",
             "os": "cartridge only", "ram": [],
             "issues": [],
             "styles": ["heavy sixer", "light sixer", "4-switch woodgrain",
                        "4-switch (Vader)", "2600 Jr short rainbow",
                        "2600 Jr long rainbow"],
             "chips": [
                 _chip("cpu", "CPU", ["MOS 6507", "Synertek 6507"]),
                 _chip("tia", "TIA", ["C010444", "C011903"],
                       "graphics and sound in one chip, and no frame buffer "
                       "behind it"),
                 _chip("riot", "RIOT", ["MOS 6532", "Synertek 6532"],
                       "the RAM, the timers and the switch inputs -- all 128 "
                       "bytes of the machine's memory are in here")]},
            {"key": "atari-7800", "model": "Atari 7800", "year": 1986,
             "cpu": "MOS 6502C-1.79", "chassis": "console",
             "os": "cartridge only, with a BIOS", "ram": [("4K", 4)],
             "issues": [], "styles": ["7800 (1986 production)", "7800 with expansion port"],
             "chips": [
                 _chip("cpu", "CPU", ["MOS 6502C (Sally)"]),
                 _chip("maria", "MARIA", ["C300599"],
                       "the display chip that made the 7800 a 7800 rather than "
                       "a faster 2600"),
                 _chip("tia", "TIA", ["C011903"],
                       "kept for sound, and for playing 2600 cartridges"),
                 _chip("pokey", "POKEY", ["C012294", "not fitted"],
                       "on the cartridge rather than the board, in the handful "
                       "of games that wanted better sound")]},
        ],
    },
    {
        "key": "atari-st",
        "name": "Atari ST",
        "manufacturer": "Atari",
        "regions": ["PAL", "NTSC"],
        "chips": _ST_CHIPS,
        "models": [
            {"key": "atari-520stfm", "model": "Atari 520STFM", "year": 1986,
             "cpu": "Motorola 68000-8", "chassis": "wedge, built-in floppy",
             "os": "TOS 1.02 / GEM", "ram": [("512K", 512), ("1MB", 1024)],
             "issues": [], "styles": ["520STFM", "520STM (no drive)"]},
            {"key": "atari-1040stf", "model": "Atari 1040STF", "year": 1986,
             "cpu": "Motorola 68000-8", "chassis": "wedge, built-in floppy",
             "os": "TOS 1.02 / GEM", "ram": [("1MB", 1024)],
             "issues": [], "styles": ["1040STF", "1040STFM"]},
            {"key": "atari-1040ste", "model": "Atari 1040STE", "year": 1989,
             "cpu": "Motorola 68000-8", "chassis": "wedge, built-in floppy",
             "os": "TOS 1.62 / GEM", "ram": [("1MB", 1024), ("4MB", 4096)],
             "issues": [], "styles": ["1040STE"],
             "chips": [
                 _chip("blitter", "Blitter", ["C025972"],
                       "standard on the STE, an option on an ST"),
                 _chip("psg", "Sound", ["Yamaha YM2149F"]),
                 _chip("tos", "TOS ROM", ["TOS 1.62", "TOS 2.06"])]},
        ],
    },
    {
        "key": "acorn",
        "name": "Acorn",
        "manufacturer": "Acorn",
        "regions": ["PAL (UK)"],
        "chips": _BBC_CHIPS,
        "models": [
            {"key": "bbc-model-a", "model": "BBC Micro Model A", "year": 1981,
             "cpu": "Rockwell 6502A-2", "chassis": "beige case, cream keys",
             "os": "Acorn MOS 1.20", "ram": [("16K", 16)],
             "issues": ["Issue 1", "Issue 2", "Issue 3", "Issue 4", "Issue 7"],
             "styles": ["Model A"]},
            {"key": "bbc-model-b", "model": "BBC Micro Model B", "year": 1981,
             "cpu": "Rockwell 6502A-2", "chassis": "beige case, cream keys",
             "os": "Acorn MOS 1.20", "ram": [("32K", 32)],
             "issues": ["Issue 1", "Issue 2", "Issue 3", "Issue 4", "Issue 7"],
             "styles": ["Model B", "Model A upgraded to B"]},
            {"key": "bbc-b-plus", "model": "BBC Micro Model B+", "year": 1985,
             "cpu": "Rockwell 6512A-2", "chassis": "beige case, cream keys",
             "os": "Acorn MOS 2.00", "ram": [("64K", 64), ("128K", 128)],
             "issues": [], "styles": ["B+ 64K", "B+ 128K"]},
            {"key": "bbc-master-128", "model": "BBC Master 128", "year": 1986,
             "cpu": "Rockwell 65SC12-2", "chassis": "beige case with keypad",
             "os": "Acorn MOS 3.20", "ram": [("128K", 128)],
             "issues": [], "styles": ["Master 128", "Master Compact"],
             "chips": [
                 _chip("cpu", "CPU", ["Rockwell R65SC12", "GTE G65SC12"]),
                 _chip("fdc", "Floppy controller", ["WD1770", "WD1772"]),
                 _chip("os-rom", "OS ROM", ["MOS 3.20", "MOS 3.50"]),
                 _chip("basic-rom", "BASIC ROM", ["BASIC IV"])]},
            {"key": "acorn-electron", "model": "Acorn Electron", "year": 1983,
             "cpu": "Rockwell 6502A-2", "chassis": "compact beige wedge",
             "os": "Acorn OS 1.00", "ram": [("32K", 32)],
             "issues": ["Issue 4", "Issue 6"], "styles": ["Electron"],
             "chips": [
                 _chip("cpu", "CPU", ["Rockwell R6502A", "Synertek SY6502A"]),
                 _chip("ula", "ULA", ["Ferranti 12C021", "Ferranti 12C021A"],
                       "video, memory and cassette in one chip that runs hot "
                       "and is the usual reason a dead Electron is dead"),
                 _chip("os-rom", "OS ROM", ["OS 1.00"]),
                 _chip("basic-rom", "BASIC ROM", ["BASIC II"])]},
            {"key": "acorn-a3000", "model": "Acorn Archimedes A3000", "year": 1989,
             "cpu": "Acorn ARM2-8", "chassis": "wedge, one-piece",
             "os": "RISC OS 2.00", "ram": [("1MB", 1024), ("2MB", 2048),
                                           ("4MB", 4096)],
             "issues": [], "styles": ["A3000"],
             "chips": [
                 _chip("cpu", "CPU", ["Acorn ARM2", "Acorn ARM3 (upgrade)"]),
                 _chip("memc", "MEMC", ["MEMC1a"]),
                 _chip("vidc", "VIDC", ["VIDC1a"]),
                 _chip("ioc", "IOC", ["IOC"]),
                 _chip("os-rom", "OS ROM", ["RISC OS 2.00", "RISC OS 3.00",
                                            "RISC OS 3.10", "RISC OS 3.11"])]},
            {"key": "acorn-a3010", "model": "Acorn A3010", "year": 1992,
             "cpu": "Acorn ARM250-12", "chassis": "wedge, one-piece",
             "os": "RISC OS 3.10", "ram": [("1MB", 1024), ("2MB", 2048),
                                           ("4MB", 4096)],
             "issues": [], "styles": ["A3010", "A3020"],
             "chips": [
                 _chip("cpu", "CPU", ["Acorn ARM250"],
                       "the ARM250 has the MEMC, VIDC and IOC inside it, so "
                       "there are no separate chips to record"),
                 _chip("os-rom", "OS ROM", ["RISC OS 3.10", "RISC OS 3.11"])]},
        ],
    },
    {
        "key": "amstrad",
        "name": "Amstrad",
        "manufacturer": "Amstrad",
        "regions": ["PAL (UK/Europe)"],
        "chips": _CPC_CHIPS,
        "models": [
            {"key": "cpc-464", "model": "Amstrad CPC 464", "year": 1984,
             "cpu": "Zilog Z80A-4", "chassis": "wedge, built-in tape",
             "os": "Locomotive BASIC 1.0", "ram": [("64K", 64)],
             "issues": ["Z70200", "Z70290"],
             "styles": ["grey keys", "colour keys (later production)"]},
            {"key": "cpc-664", "model": "Amstrad CPC 664", "year": 1985,
             "cpu": "Zilog Z80A-4", "chassis": 'wedge, built-in 3" floppy',
             "os": "Locomotive BASIC 1.1 / AMSDOS", "ram": [("64K", 64)],
             "issues": [], "styles": ["CPC 664"],
             "chips": [
                 _chip("fdc", "Floppy controller", ["NEC D765AC"])]},
            {"key": "cpc-6128", "model": "Amstrad CPC 6128", "year": 1985,
             "cpu": "Zilog Z80A-4", "chassis": 'wedge, built-in 3" floppy',
             "os": "Locomotive BASIC 1.1 / AMSDOS / CP/M Plus",
             "ram": [("128K", 128)],
             "issues": [], "styles": ["grey case (UK)", "white case (Europe)"],
             "chips": [
                 _chip("fdc", "Floppy controller", ["NEC D765AC"])]},
            {"key": "cpc-464-plus", "model": "Amstrad 464 Plus", "year": 1990,
             "cpu": "Zilog Z80A-4", "chassis": "wedge, built-in tape",
             "os": "Locomotive BASIC 1.1", "ram": [("64K", 64)],
             "issues": [], "styles": ["464 Plus"],
             "chips": [
                 _chip("cpu", "CPU", _Z80),
                 _chip("gate-array", "ASIC", ["Amstrad 40489"],
                       "the Plus ASIC does the Gate Array's and the CRTC's work "
                       "together, and adds the sprites"),
                 _chip("psg", "Sound", _AY)]},
            {"key": "cpc-6128-plus", "model": "Amstrad 6128 Plus", "year": 1990,
             "cpu": "Zilog Z80A-4", "chassis": 'wedge, built-in 3" floppy',
             "os": "Locomotive BASIC 1.1 / AMSDOS / CP/M Plus",
             "ram": [("128K", 128)], "issues": [], "styles": ["6128 Plus"],
             "chips": [
                 _chip("cpu", "CPU", _Z80),
                 _chip("gate-array", "ASIC", ["Amstrad 40489"]),
                 _chip("psg", "Sound", _AY),
                 _chip("fdc", "Floppy controller", ["NEC D765AC"])]},
            {"key": "gx4000", "model": "Amstrad GX4000", "year": 1990,
             "cpu": "Zilog Z80A-4", "chassis": "console",
             "os": "cartridge only", "ram": [("64K", 64)],
             "issues": [], "styles": ["GX4000"],
             "chips": [
                 _chip("cpu", "CPU", _Z80),
                 _chip("gate-array", "ASIC", ["Amstrad 40489"]),
                 _chip("psg", "Sound", _AY)]},
            {"key": "pcw-8256", "model": "Amstrad PCW 8256", "year": 1985,
             "cpu": "Zilog Z80A-4", "chassis": 'monitor unit with 3" floppy',
             "os": "CP/M Plus / LocoScript", "ram": [("256K", 256)],
             "issues": [], "styles": ["PCW 8256", "PCW 8512 (two drives, 512K)"],
             "chips": [
                 _chip("cpu", "CPU", _Z80),
                 _chip("gate-array", "Gate Array", ["Amstrad 40026",
                                                    "Amstrad 40028"],
                       "the PCW's own gate array, not a CPC part"),
                 _chip("fdc", "Floppy controller", ["NEC D765AC"])]},
        ],
    },
    {
        "key": "sega",
        "name": "Sega",
        "manufacturer": "Sega",
        "regions": ["PAL", "NTSC-U", "NTSC-J"],
        "chips": _MEGADRIVE_CHIPS,
        "models": [
            {"key": "master-system", "model": "Sega Master System", "year": 1986,
             "cpu": "Zilog Z80A-3.58", "chassis": "console",
             "os": "cartridge, with a boot ROM", "ram": [("8K", 8)],
             "issues": [], "styles": ["Master System", "Master System (built-in "
                                      "Hang-On)", "Master System (Alex Kidd)"],
             "chips": [
                 _chip("cpu", "CPU", ["Zilog Z80A", "Sharp LH5080A"]),
                 _chip("vdp", "VDP", ["Sega 315-5124", "Sega 315-5246"],
                       "the -5246 of a later machine and a Game Gear fixes some "
                       "of the -5124's quirks"),
                 _chip("psg", "Sound", ["SN76489 (in the VDP)",
                                        "Yamaha YM2413 (FM, Japan)"],
                       "the FM chip is a Japanese Mark III / Master System "
                       "fitting, and worth recording where it is there")]},
            {"key": "master-system-ii", "model": "Sega Master System II",
             "year": 1990, "cpu": "Zilog Z80A-3.58", "chassis": "console",
             "os": "cartridge, with a built-in game",
             "ram": [("8K", 8)], "issues": [],
             "styles": ["Master System II (Alex Kidd)",
                        "Master System II (Sonic)"],
             "chips": [
                 _chip("cpu", "CPU", ["Zilog Z80A", "Sharp LH5080A"]),
                 _chip("vdp", "VDP", ["Sega 315-5246"]),
                 _chip("psg", "Sound", ["SN76489 (in the VDP)"])]},
            {"key": "megadrive", "model": "Sega Mega Drive", "year": 1988,
             "cpu": "Motorola 68000-7.6", "chassis": "console",
             "os": "cartridge, with TMSS on later boards", "ram": [("64K", 64)],
             "issues": _MEGADRIVE_BOARDS,
             "styles": ["High Definition Graphics badge",
                        "later Model 1 (no badge)", "Genesis Model 1 (US)",
                        "Mega Drive (Japan)"]},
            {"key": "megadrive-2", "model": "Sega Mega Drive 2", "year": 1993,
             "cpu": "Motorola 68000-7.6", "chassis": "console (smaller case)",
             "os": "cartridge, with TMSS", "ram": [("64K", 64)],
             "issues": ["VA0", "VA1", "VA1.8", "VA2", "VA2.3"],
             "styles": ["Mega Drive 2", "Genesis Model 2 (US)"],
             "chips": [
                 _chip("cpu", "CPU", ["Motorola MC68000",
                                      "Hitachi HD68HC000"]),
                 _chip("z80", "Sound CPU", ["integrated in the ASIC"]),
                 _chip("vdp", "VDP", ["Sega 315-5660", "Sega 315-5700"]),
                 _chip("fm", "FM sound", ["Yamaha YM3438",
                                          "integrated in the ASIC"]),
                 _chip("amp", "Amplifier", ["Rohm BA10324", "JRC 2100"])]},
            {"key": "game-gear", "model": "Sega Game Gear", "year": 1990,
             "cpu": "Zilog Z80A-3.58", "chassis": "handheld",
             "os": "cartridge", "ram": [("8K", 8)],
             "issues": ["VA0", "VA1", "VA4", "VA5"],
             "styles": ["Game Gear", "Game Gear (Majesco)"],
             "chips": [
                 _chip("cpu", "CPU", ["Zilog Z80A", "Sharp LH5080A"]),
                 _chip("vdp", "VDP", ["Sega 315-5378", "Sega 315-5535"]),
                 _chip("psg", "Sound", ["SN76489 (in the VDP)"])]},
        ],
    },
]


# --- lookups ----------------------------------------------------------------

def _merge(family, mod):
    """One model as everything known about it: the family's fields where the model
    is silent, and the family's chip sockets where it names none of its own.

    A chip the model names replaces the family's for that socket rather than
    joining it, keeping the family's place in the order -- which is the order a
    person reads a board in -- and anything it adds follows. A replacement with no
    variants removes the socket, which is how a VIC-20 says it has no SID and a
    ZX80 that it has no ULA, without either repeating the rest of its family.
    """
    out = {"family": family["name"], "family_key": family["key"],
           "manufacturer": family.get("manufacturer", ""),
           "regions": list(family.get("regions", [])),
           "ram": [], "issues": [], "styles": [], "cpu": "", "chassis": "",
           "os": "", "year": None}
    out.update({k: v for k, v in mod.items() if k != "chips"})
    own = {c["role"]: c for c in mod.get("chips", [])}
    chips = [own.pop(c["role"], c) for c in family.get("chips", [])]
    chips += [c for c in mod.get("chips", []) if c["role"] in own]
    out["chips"] = [c for c in chips if c["variants"]]
    return out


_MODELS = {}
_ORDER = []
for _family in FAMILIES:
    for _model in _family["models"]:
        _MODELS[_model["key"]] = _merge(_family, _model)
        _ORDER.append(_model["key"])


def model(key):
    """One catalogue model by key, with its family's fields filled in, or None for
    a key the catalogue does not know -- which is what a machine filed under a key
    since removed comes back as."""
    return _MODELS.get((key or "").strip()) or None


def models():
    """Every model, in catalogue order."""
    return [_MODELS[k] for k in _ORDER]


def keys():
    return list(_ORDER)


def grouped():
    """[(family name, [model])] in catalogue order, for the picker's optgroups."""
    out = []
    for family in FAMILIES:
        out.append((family["name"],
                    [_MODELS[m["key"]] for m in family["models"]]))
    return out


def roles(key):
    """The chip sockets a model is asked about, in board-reading order."""
    m = model(key)
    return [c["role"] for c in m["chips"]] if m else []


def chip(key, role):
    """One socket of one model, or None if that model has no such socket."""
    m = model(key)
    if not m:
        return None
    return next((c for c in m["chips"] if c["role"] == role), None)


def chip_label(key, role):
    """What to call a socket on a page or a label. Falls back to the role slug
    tidied up, so a chip recorded against a model or a socket the catalogue no
    longer lists still says what it is rather than disappearing."""
    c = chip(key, role)
    if c:
        return c["label"]
    return (role or "").replace("-", " ").upper() if len(role or "") <= 4 \
        else (role or "").replace("-", " ").capitalize()


def prefill(key):
    """What picking a model can fill in on a machine's record: the fields that are
    true of every one of that model. The form only ever puts these into a box that
    is empty, because the machine in front of you is the authority and the
    catalogue is a starting point."""
    m = model(key)
    if not m:
        return {}
    return {"manufacturer": m.get("manufacturer", ""), "model": m.get("model", ""),
            "year": m.get("year"), "cpu": m.get("cpu", ""),
            "chassis": m.get("chassis", ""), "os": m.get("os", "")}


def ram_labels(key):
    """The standard memory sizes a model was sold with, as the labels the memory
    box takes ('16K', '48K')."""
    m = model(key)
    return [label for label, _kb in m["ram"]] if m else []


# --- rendering --------------------------------------------------------------

# The keys the rendered line uses for the three answers that are not a chip. The
# chips use their own labels, so a line reads as the machine reads: the model, then
# what distinguishes this one, then the sockets in board order.
#
# "Board" rather than "Issue" because the value already says which word its make
# used for the same thing -- Sinclair and Acorn number an issue, Commodore an ASSY,
# Amiga a Rev and Sega a VA -- and one field holds all four rather than pretending
# they are different questions.
ISSUE_KEY = "Board"
STYLE_KEY = "Style"
REGION_KEY = "Region"


def render(model_key="", issue="", style="", region="", chips=()):
    """A machine's catalogue identity as one line, in the register's own
    'Key: value | Key: value' notation -- the model first, without a key, because
    it is the subject rather than an attribute of one.

        ZX Spectrum+ | Board: Issue 6A | Style: moulded keys | ULA: Ferranti 6C001E-7

    This is a rendering and never a store: it is what the machine page, the label,
    the search index and the wire format read, and it is written fresh from the
    rows every time they change (machinedb.write). Nothing parses it back -- the
    mistake migration 0011 was written to undo -- so the words here are free to be
    improved.
    """
    m = model(model_key)
    pairs = []
    if model_key:
        pairs.append(("", m["model"] if m else model_key))
    pairs += [(ISSUE_KEY, issue), (STYLE_KEY, style), (REGION_KEY, region)]
    for role, variant in in_role_order(model_key, chips):
        pairs.append((chip_label(model_key, role), variant))
    return entry.build_specs(pairs)


def in_role_order(model_key, chips):
    """(role, variant) pairs in the order the catalogue lists the sockets, with
    anything it does not list last -- a chip kept from a model this machine is no
    longer filed as, or a socket since removed from the catalogue."""
    pairs = list(chips.items()) if isinstance(chips, dict) else list(chips)
    order = roles(model_key)
    return sorted(pairs, key=lambda kv: (order.index(kv[0]) if kv[0] in order
                                         else len(order), kv[0]))


def form_catalogue():
    """The whole catalogue as plain data for the edit form's pickers: what each
    model offers, and what picking it fills in.

    One structure, shipped to the browser as JSON, because the form's variation
    fields are built from whichever model is chosen and a page cannot hold a set of
    menus for all sixty of them. The same lists the server reads a save back
    against, so the two cannot come to disagree about what a model was built in.
    """
    out = {}
    for key in _ORDER:
        m = _MODELS[key]
        out[key] = {
            "model": m["model"], "issues": m["issues"], "styles": m["styles"],
            "regions": m["regions"], "ram": ram_labels(key),
            "prefill": {k: v for k, v in prefill(key).items() if v not in (None, "")},
            "chips": [{"role": c["role"], "label": c["label"],
                       "variants": c["variants"], "note": c.get("note", "")}
                      for c in m["chips"]],
        }
    return out
