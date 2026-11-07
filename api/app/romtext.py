"""What a ROM says about itself (MANUAL §23, "ROMs"; ADR-0043): the readable text in
it, and the little the register makes of that text -- which BIOS it is, and what a
card's ROM calls the card.

A ROM is code and data with words in it: a copyright line, a version, the name a video
BIOS gives its chip, the identification string an AMI or Award BIOS carries. Those
words are what somebody looking a BIOS up would search for, so a survey's page shows
them all, and the few the register recognises are read for the record.
"""

import re

# Runs of printable ASCII at least this long. Shorter ones are mostly the bytes of an
# instruction that happen to land on letters.
SHORTEST = 6

# Enough for any BIOS's own words, and a ceiling on what one survey keeps.
MOST = 300

_RUN = re.compile(rb"[\x20-\x7e]{%d,}" % SHORTEST)


def strings(data: bytes) -> list[str]:
    """The readable text in a ROM, in the order it appears, each line once."""
    seen: set[str] = set()
    out: list[str] = []
    for found in _RUN.finditer(data):
        text = " ".join(found.group().decode("ascii").split())
        # Code that lands on printable bytes reads as capitals and punctuation with
        # hardly a letter between them; words have letters in them.
        if len(text) < SHORTEST or sum(c.isalpha() for c in text) < 4 or text in seen:
            continue
        seen.add(text)
        out.append(text[:160])
        if len(out) >= MOST:
            break
    return out


# A BIOS's maker and version as its own banner and copyright lines give them. Tried in
# this order, so a line that names a version wins over one that only names a maker,
# and the makers of clone BIOSes are looked for before a word they all share.
_BIOSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Award",
        re.compile(
            r"Award (?:Modular |Software |Plug and Play |Medallion )?BIOS v?(\d+\.\d+[A-Za-z0-9]*)",
            re.I,
        ),
    ),
    ("AMI", re.compile(r"AMIBIOS(?: Version)? ?v?(\d+\.\d+[\d.]*)", re.I)),
    (
        "Phoenix",
        re.compile(r"Phoenix\w*(?: ROM)? BIOS(?: PLUS)?(?: Version)? ?(\d+\.\d+[\w.]*)", re.I),
    ),
    ("MR BIOS", re.compile(r"MR BIOS.*?\bV?(\d+\.\d+)", re.I)),
    ("Award", re.compile(r"Award Software", re.I)),
    ("AMI", re.compile(r"American Megatrends|AMIBIOS", re.I)),
    ("Phoenix", re.compile(r"Phoenix Technologies", re.I)),
    ("Quadtel", re.compile(r"Quadtel", re.I)),
    ("Chips and Technologies", re.compile(r"Chips (?:and|&) Tech", re.I)),
    ("Compaq", re.compile(r"\bCOMPAQ\b", re.I)),
    # IBM's own, by its copyright mark rather than the "IBM compatible" every clone says.
    ("IBM", re.compile(r"COPR\. IBM|IBM Corp", re.I)),
)


def bios(texts: list[str]) -> tuple[str, str]:
    """(maker, version) as far as a BIOS's own text says them, and ("", "") for a ROM
    that names neither."""
    for maker, pattern in _BIOSES:
        for text in texts:
            found = pattern.search(text)
            if found is not None:
                return maker, (found.group(1) if found.lastindex else "") or ""
    return "", ""


# Who made the cards that carry a ROM of their own, as their ROMs name themselves:
# video chips first, then disk controllers and boot ROMs.
_MAKERS = (
    "Tseng",
    "Trident",
    "S3 ",
    "Cirrus",
    "ATI ",
    "Paradise",
    "Western Digital",
    "Oak Technology",
    "Realtek",
    "Chips and Tech",
    "Chips & Tech",
    "Video Seven",
    "Headland",
    "Avance",
    "Matrox",
    "Number Nine",
    "Genoa",
    "Orchid",
    "Diamond",
    "Hercules",
    "Everex",
    "Ahead",
    "Sigma",
    "Adaptec",
    "XTIDE",
    "XT-IDE",
    "Future Domain",
    "Seagate",
    "Promise",
    "netboot",
    "3Com",
)

# What comes after a card's name on its banner line: the words about which BIOS and
# which version this is, which are not the card's name.
_AFTER_NAME = re.compile(
    r"\s*(?:(?:VGA|SVGA|EGA|Video|Graphics|Display)\s+)?(?:BIOS|ROM)\b.*$"
    r"|\s*(?:Version|Ver\.?|Rev\.?|Copyright|\(C\)).*$",
    re.I,
)


# The words of a ROM's banner: the line that says what the card is, as against the
# messages the ROM prints while it works. QEMU's VGA BIOS carries "cirrus mode switch
# regular", which names a maker and is not a name.
_BANNER = re.compile(r"\b(?:BIOS|ROM|Version|Copyright)\b|\b(?:Ver|Rev)\.|\(C\)", re.I)

# What may come before a banner's first word and is no part of the name.
_LEADING = re.compile(r"^[^A-Za-z0-9]+")


def card(texts: list[str]) -> str:
    """What a card's ROM calls the card: its first banner line naming a maker, with the
    words about versions and copyright taken off. "" when no banner names one, so that
    a card whose ROM says nothing of itself is one nobody can name (ADR-0044)."""
    for text in texts:
        if not _BANNER.search(text):
            continue
        if any(maker.lower() in text.lower() for maker in _MAKERS):
            # A ROM's header can run straight into its banner: the size byte of a 32 KiB
            # ROM is "@", and is not part of the card's name.
            name = _LEADING.sub("", _AFTER_NAME.sub("", text)).strip(" ,.-")
            if len(name) >= 3:
                return name[:120]
    return ""


# What a network card's boot ROM says of itself: the boot code's own name, or its
# author's. netboot 0.8.1, which the boot network's machines start from, compresses
# everything but its copyright line, and says neither that it is a network card's nor
# whose, so its author's name is the one word it has.
_BOOT_ROM = re.compile(
    r"\b(?:i?PXE|gPXE|PXENV|Etherboot|netboot|Boot ?ROM|Boot Agent|BootWare|"
    r"Remote Program Load|Lanworks)\b|G\. Kuhlmann",
    re.I,
)


def boot_rom(texts: list[str]) -> bool:
    """Whether a ROM's text says it starts a machine from the network."""
    return any(_BOOT_ROM.search(text) for text in texts)
