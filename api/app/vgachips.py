"""Which VGA chip a card's own registers say it is (ADR-0051).

The survey program tries each family's test in the order SuperProbe, XFree86 and
whatvga settled on, and reports the family whose test answered and the ID it read,
in hex: `TSENG 40`, `CIRRUS A0`, `S3 E1 11`. Its tables live here rather than in the
program, which has 48K to fit in. An ID this does not know names the family's maker
and the ID as it came, which is still more than "VGA".
"""

from collections.abc import Callable

Decode = Callable[[list[int]], tuple[str, str]]

_TSENG_W32 = {
    0x0: "ET4000/W32",
    0x1: "ET4000/W32i",
    0x2: "ET4000/W32p",
    0x3: "ET4000/W32i",
    0x5: "ET4000/W32p",
    0x6: "ET4000/W32p",
    0x7: "ET4000/W32p",
    0xB: "ET4000/W32i",
}

# CR27's top six bits; a 5402 and a 5420 are told apart by its bottom two.
_CIRRUS = {
    0x23: "CL-GD5422",
    0x24: "CL-GD5426",
    0x25: "CL-GD5424",
    0x26: "CL-GD5428",
    0x27: "CL-GD5429",
    0x28: "CL-GD5430",
    0x29: "CL-GD5434",
    0x2A: "CL-GD5434",
    0x2B: "CL-GD5436",
    0x2E: "CL-GD5446",
    0x2F: "CL-GD5480",
}

_S3 = {
    0x81: "86C911",
    0x82: "86C924",
    0x90: "86C928",
    0x91: "86C928",
    0x94: "86C928",
    0x95: "86C928",
    0xB0: "86C928",
    0xC0: "Vision864",
    0xC1: "Vision864",
    0xD0: "Vision964",
    0xD1: "Vision964",
}
# A later S3 says which it is in CR2E.
_S3_LATER = {
    0x10: "Trio32",
    0x11: "Trio64",
    0x80: "Vision866",
    0x90: "Vision868",
    0xF0: "Vision968",
}

_TRIDENT = {
    0x01: "TVGA8800BR",
    0x02: "TVGA8800CS",
    0x03: "TVGA8900B",
    0x04: "TVGA8900C",
    0x13: "TVGA8900C",
    0x23: "TVGA9000",
    0x33: "TVGA8900CL",
    0x43: "TVGA9000i",
    0x53: "TVGA9200CXr",
    0x73: "TGUI9420",
    0x93: "TVGA9400CXi",
    0xA3: "TVGA9320",
    0xD3: "TGUI96xx",
    0xE3: "TGUI9440AGi",
    0xF3: "TGUI9430",
}

_OAK = {
    0x00: "OTI-037C",
    0x02: "OTI-067",
    0x05: "OTI-077",
    0x07: "OTI-057",
    0x83: "OTI-083",
    0x87: "OTI-087",
}

_CHIPS = {
    0x0: "82C451",
    0x1: "82C452",
    0x2: "82C455",
    0x3: "82C453",
    0x4: "82C450",
    0x5: "82C456",
    0x6: "82C457",
    0x7: "F65520",
    0x8: "F65530",
    0x9: "F65510",
    0xC: "F65535",
    0xD: "F65540",
}

# The ID in ATI's BIOS (C000:0043), as a character.
_ATI = {
    "1": "18800",
    "2": "18800-1",
    "3": "28800-2",
    "4": "28800-4",
    "5": "28800-5",
    "6": "28800-6",
    "a": "mach32",
    "b": "mach32",
    "c": "mach32",
    " ": "mach64",
}

_COMPAQ = {0x03: "IVGS", 0x05: "AVGA", 0x06: "QVision", 0x0E: "QVision 1024", 0x10: "AVGA"}

_GENOA = {0x00: "GVGA 6200", 0x11: "GVGA 6400", 0x22: "GVGA 6100", 0x33: "ET3000", 0x55: "ET3000"}

_HEADLAND = {
    0x7151: "HT208B",
    0x7152: "HT208C",
    0x7760: "HT216B",
    0x7763: "HT216D",
    0x7764: "HT216E",
    0x7765: "HT216F",
}


def _tseng(ident: list[int]) -> tuple[str, str]:
    code = ident[0]
    if code == 0x30:
        return "Tseng Labs", "ET3000"
    if code >> 4 == 0x5:
        return "Tseng Labs", _TSENG_W32.get(code & 0xF, "ET4000/W32")
    return "Tseng Labs", "ET4000"


def _cirrus(ident: list[int]) -> tuple[str, str]:
    code = ident[0] >> 2
    if code == 0x22:
        return "Cirrus Logic", "CL-GD5420" if ident[0] & 2 else "CL-GD5402"
    return "Cirrus Logic", _CIRRUS.get(code, "CL-GD54xx")


def _s3(ident: list[int]) -> tuple[str, str]:
    code = ident[0]
    if code in (0xE0, 0xE1) and len(ident) > 1:
        return "S3", _S3_LATER.get(ident[1], "Trio")
    if 0xA0 <= code <= 0xAF:
        return "S3", "86C801/805"
    return "S3", _S3.get(code, f"86C {code:02X}")


def _wd(ident: list[int]) -> tuple[str, str]:
    if ident == [0x1A]:
        return "Paradise", "PVGA1A"
    if len(ident) == 2 and all(0x30 <= c <= 0x39 for c in ident):
        return "Western Digital", "WD90C" + bytes(ident).decode("ascii")
    return "Western Digital", "WD90C00"


def _video7(ident: list[int]) -> tuple[str, str]:
    code = ident[0] << 8 | ident[1] if len(ident) > 1 else 0
    if code >= 0x8000:
        return "Video Seven", "V7VGA"
    if 0x7000 <= code <= 0x70FF:
        return "Headland", "HT208"
    if 0x7140 <= code <= 0x714F:
        return "Headland", "HT208A"
    if code in _HEADLAND:
        return "Headland", _HEADLAND[code]
    return "Video Seven", "VGA"


def _ati(ident: list[int]) -> tuple[str, str]:
    return "ATI", _ATI.get(chr(ident[0]), "VGA Wonder")


def _table(maker: str, names: dict[int, str]) -> Decode:
    def name(ident: list[int]) -> tuple[str, str]:
        return maker, names.get(ident[0], f"{ident[0]:02X}")

    return name


_FAMILIES: dict[str, Decode] = {
    "TSENG": _tseng,
    "CIRRUS": _cirrus,
    "S3": _s3,
    "TRIDENT": _table("Trident", _TRIDENT),
    "WD": _wd,
    "OAK": _table("Oak Technology", _OAK),
    "VIDEO7": _video7,
    "CHIPS": _table("Chips and Technologies", _CHIPS),
    "ATI": _ati,
    "COMPAQ": _table("Compaq", _COMPAQ),
    "GENOA": _table("Genoa Systems", _GENOA),
}


def name(reported: str) -> tuple[str, str]:
    """(maker, chip) for what the survey program reported (`TSENG 40`); ("", "") for
    nothing it could have said."""
    family, _, rest = " ".join((reported or "").split()).upper().partition(" ")
    try:
        ident = [int(word, 16) for word in rest.split()]
    except ValueError:
        return "", ""
    if family not in _FAMILIES or not ident or not all(0 <= c <= 0xFF for c in ident):
        return "", ""
    return _FAMILIES[family](ident)
