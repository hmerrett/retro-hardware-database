"""Code 128: the barcode a label carries beside its QR code, or instead of it
(MANUAL §13, "QR code, barcode or both"; ADR-0034).

It holds the tag and nothing else -- `RH-K7Q2`, seven characters -- because the tag
is the only thing on a label that never changes, and what a handheld scanner types
is then exactly what the register looks things up by. Code 128 because every
scanner reads it, the cheapest included, and because it checks itself: a misread
bar fails the checksum rather than coming out as somebody else's tag.

Only code set B, which is printable ASCII: an asset tag is letters, digits and a
hyphen, and the cleverness that switches to set C for runs of digits buys two bars'
width on a historic RH-0001 and costs a second path through the decoder. The table
below is the standard one, and the browser's reader in static/code128.js carries a
copy of it -- which the suite holds to this one, and this one to ReportLab's.
"""

# Each symbol's bar and space widths in modules, bar first: symbol n is PATTERNS[n].
# Six elements and eleven modules each, but for the stop, which is seven and thirteen.
PATTERNS: tuple[str, ...] = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312",
    "132212", "221213", "221312", "231212", "112232", "122132", "122231", "113222",
    "123122", "123221", "223211", "221132", "221231", "213212", "223112", "312131",
    "311222", "321122", "321221", "312212", "322112", "322211", "212123", "212321",
    "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121",
    "313121", "211331", "231131", "213113", "213311", "213131", "311123", "311321",
    "331121", "312113", "312311", "332111", "314111", "221411", "431111", "111224",
    "111422", "121124", "121421", "141122", "141221", "112214", "112412", "122114",
    "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112",
    "421211", "212141", "214121", "412121", "111143", "111341", "131141", "114113",
    "114311", "411113", "411311", "113141", "114131", "311141", "411131", "211412",
    "211214", "211232", "2331112",
)  # fmt: skip

START_B, STOP = 104, 106

# The white either side of the bars a scanner needs to know where they start: ten
# modules is the standard's, and a margin eaten into is a label that has to be
# scanned twice.
QUIET = 10


def symbols(text: str) -> list[int]:
    """`text` as code set B symbols, start and checksum and stop included. Raises
    ValueError for a character set B cannot carry, which nothing a label prints is."""
    if any(not 32 <= ord(ch) <= 126 for ch in text):
        raise ValueError(f"Code 128 set B cannot carry {text!r}")
    data = [ord(ch) - 32 for ch in text]
    check = (START_B + sum(n * v for n, v in enumerate(data, start=1))) % 103
    return [START_B, *data, check, STOP]


def modules(text: str) -> list[int]:
    """The bar and space widths, in modules, from the first bar to the last --
    alternating bar, space, bar, starting and ending with a bar. The quiet zones
    either side are the caller's to leave."""
    return [int(w) for s in symbols(text) for w in PATTERNS[s]]


def width(text: str) -> int:
    """How many modules the bars take, quiet zones included."""
    return sum(modules(text)) + 2 * QUIET
