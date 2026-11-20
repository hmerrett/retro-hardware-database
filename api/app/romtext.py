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


# The computer makers who had a BIOS written for them and put their own name in it,
# as it is printed there. Looked for whoever wrote the BIOS, because the writer's
# name (Phoenix's) is in it too (ADR-0047).
_OEMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("HP", re.compile(r"Hewlett[- ]?Packard", re.I)),
    ("Dell", re.compile(r"\bDell (?:Computer|Inc\b)", re.I)),
)


def oem(texts: list[str]) -> str:
    """The computer maker whose name is in a BIOS somebody else wrote for it, or ""."""
    for maker, pattern in _OEMS:
        if any(pattern.search(text) for text in texts):
            return maker
    return ""


# Who made the cards that carry a ROM of their own, as their ROMs name them and as the
# register writes them: the chip makers whose own BIOS most cards carry, then the
# makers of cards, of disk and SCSI controllers and of network cards, and the
# computer makers whose own cards carry their name. A program names a ROM and not who
# built the card it is on, so its maker is "" (ADR-0047). Each pattern takes the
# maker's words as a banner writes them, company suffix and all, so that what is left
# is the card's model.
_INC = r"(?:,? (?:Inc|Corp|Corporation|Ltd)\b\.?)?"
_MAKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bTseng(?: Lab(?:s|oratories))?\b" + _INC, re.I), "Tseng Labs"),
    (re.compile(r"\bTrident(?: Microsystems)?\b" + _INC, re.I), "Trident Microsystems"),
    (re.compile(r"\bS3\b" + _INC), "S3"),
    (re.compile(r"\bCirrus(?: Logic)?\b" + _INC, re.I), "Cirrus Logic"),
    (re.compile(r"\bATI(?: Technologies)?\b" + _INC), "ATI"),
    (re.compile(r"\bParadise(?: Systems)?\b" + _INC, re.I), "Paradise"),
    (re.compile(r"\bWestern Digital\b" + _INC, re.I), "Western Digital"),
    (re.compile(r"\bOak Technology\b" + _INC, re.I), "Oak Technology"),
    (re.compile(r"\bRealtek(?: Semiconductor)?\b" + _INC, re.I), "Realtek"),
    (re.compile(r"\bChips (?:and|&) Tech(?:nologies)?\b" + _INC, re.I), "Chips and Technologies"),
    (re.compile(r"\bVideo Seven\b" + _INC, re.I), "Video Seven"),
    (re.compile(r"\bHeadland(?: Technology)?\b" + _INC, re.I), "Headland Technology"),
    (re.compile(r"\bAvance(?: Logic)?\b" + _INC, re.I), "Avance Logic"),
    (re.compile(r"\bMatrox\b" + _INC, re.I), "Matrox"),
    (re.compile(r"\bNumber Nine(?: Computer)?\b" + _INC, re.I), "Number Nine"),
    (re.compile(r"\bGenoa(?: Systems)?\b" + _INC, re.I), "Genoa Systems"),
    (re.compile(r"\bOrchid(?: Technology)?\b" + _INC, re.I), "Orchid Technology"),
    (re.compile(r"\bDiamond(?: Multimedia| Computer Systems)?\b" + _INC, re.I), "Diamond"),
    (re.compile(r"\bHercules(?: Computer Technology)?\b" + _INC, re.I), "Hercules"),
    (re.compile(r"\bEverex(?: Systems)?\b" + _INC, re.I), "Everex"),
    (re.compile(r"\bAhead(?: Systems)?\b" + _INC, re.I), "Ahead Systems"),
    (re.compile(r"\bSigma(?: Designs)?\b" + _INC, re.I), "Sigma Designs"),
    (re.compile(r"\bAdaptec\b" + _INC, re.I), "Adaptec"),
    (re.compile(r"\bFuture Domain\b" + _INC, re.I), "Future Domain"),
    (re.compile(r"\bSeagate(?: Technology)?\b" + _INC, re.I), "Seagate"),
    (re.compile(r"\bPromise(?: Technology)?\b" + _INC, re.I), "Promise Technology"),
    (re.compile(r"\b3Com\b" + _INC, re.I), "3Com"),
    (re.compile(r"\bCOMPAQ(?: Computer)?\b" + _INC, re.I), "Compaq"),
    # IBM's own, by its copyright mark rather than the "IBM compatible" a clone says.
    (re.compile(r"COPR\. IBM\b|\bIBM Corp(?:oration)?\b\.?"), "IBM"),
    (re.compile(r"\bXT-?IDE\b", re.I), ""),
    (re.compile(r"\bnetboot\b", re.I), ""),
)

# What comes after a card's name on its banner line: the words about which BIOS and
# which version this is, which are not the card's name. Whole words only, or the
# "ver" in Everex or Universal would end the name there.
_AFTER_NAME = re.compile(
    r"\s*(?:(?:VGA|SVGA|EGA|Video|Graphics|Display)\s+)?\b(?:BIOS|ROM)\b.*$"
    r"|\s*\b(?:Version\b|Ver\b\.?|Rev\b\.?|Copyright\b).*$|\s*\(C\).*$",
    re.I,
)


# The words of a ROM's banner: the line that says what the card is, as against the
# messages the ROM prints while it works. QEMU's VGA BIOS carries "cirrus mode switch
# regular", which names a maker and is not a name.
_BANNER = re.compile(r"\b(?:BIOS|ROM|Version|Copyright)\b|\b(?:Ver|Rev)\.|\(C\)", re.I)

# What may come before a banner's first word and is no part of the name.
_LEADING = re.compile(r"^[^A-Za-z0-9]+")


def _named(text: str) -> str:
    """A banner line with the words about which BIOS and which version it is taken
    off, and anything before its first word: what it calls the card. A ROM's header
    can run straight into its banner (the size byte of a 32 KiB ROM is "@")."""
    return _LEADING.sub("", _AFTER_NAME.sub("", text)).strip(" ,.-")


def card_made(texts: list[str]) -> tuple[str, str]:
    """(maker, model) of a card as its ROM names them: the maker its first banner line
    naming one gives, as the register writes it, and the rest of that line's name for
    the card as the model. Where that line names only the maker (a copyright line), the
    model is the first banner line naming a chip: the words on it with a number in them
    (`CL-GD5428`). ("", "") for a ROM whose banners name nobody, so that a card whose
    ROM says nothing of itself is one nobody can name (ADR-0044)."""
    banners = [text for text in texts if _BANNER.search(text)]
    for text in banners:
        for pattern, maker in _MAKERS:
            if pattern.search(text) is None:
                continue
            model = _named(pattern.sub(" ", text) if maker else text)
            if not model:
                model = next((n for n in map(_named, banners) if _chip(n)), "")
            if maker or len(model) >= 3:
                return maker, model[:120]
            break
    return "", ""


def _chip(name: str) -> bool:
    """Whether a banner's name is a chip's: a number in it, and no maker's name."""
    return any(c.isdigit() for c in name) and not any(p.search(name) for p, _ in _MAKERS)


def card(texts: list[str]) -> str:
    """What a card's ROM calls the card: its maker and its model (ADR-0044, ADR-0047),
    or "" for a ROM that names nobody."""
    name = " ".join(filter(None, card_made(texts)))
    return name if len(name) >= 3 else ""


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
