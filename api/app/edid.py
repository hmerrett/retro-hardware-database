"""What a monitor says it is, from the EDID it gave the video card (ADR-0051).

DDC hands over 128 bytes (VESA EDID 1.x): a fixed header, the maker's
three-letter code and a product number, a 32-bit serial number, the week and
year it was made, and four descriptors, which on most monitors include its name
and its serial number written out. The survey program sends the block as it came,
in hex, and this reads it; a block whose header or checksum is wrong was misread
on the way and says nothing.
"""

from typing import NamedTuple

_HEADER = bytes.fromhex("00FFFFFFFFFFFF00")

# A serial number many monitors give when they have none.
_NO_NUMBER = (0, 0x01010101, 0xFFFFFFFF)


class Monitor(NamedTuple):
    code: str  # the maker's three letters, DEL
    product: str  # its product number in hex, A0A3
    serial: str  # written out where it gives one, else its number; "" for neither
    name: str  # its own name, DELL P1110, or ""


def read(text: str) -> Monitor | None:
    """The monitor an EDID block in hex describes, or None for one that is not a
    whole, well-formed block."""
    try:
        block = bytes.fromhex("".join((text or "").split()))
    except ValueError:
        return None
    if len(block) < 128 or block[:8] != _HEADER or sum(block[:128]) % 256:
        return None
    packed = int.from_bytes(block[8:10], "big")
    letters = [(packed >> shift) & 0x1F for shift in (10, 5, 0)]
    if not all(1 <= n <= 26 for n in letters):
        return None
    code = "".join(chr(64 + n) for n in letters)
    product = f"{int.from_bytes(block[10:12], 'little'):04X}"
    number = int.from_bytes(block[12:16], "little")
    texts = {}
    for at in (54, 72, 90, 108):
        d = block[at : at + 18]
        if d[0:3] == b"\0\0\0" and d[3] in (0xFC, 0xFF) and d[3] not in texts:
            words = d[5:18].split(b"\n")[0].decode("ascii", "replace")
            texts[d[3]] = " ".join(words.split())
    serial = texts.get(0xFF, "") or ("" if number in _NO_NUMBER else str(number))
    return Monitor(code, product, serial, texts.get(0xFC, ""))
