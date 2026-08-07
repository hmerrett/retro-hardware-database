"""Convert between the free-text specs string ('Key: value | Key: value') and a
normalised structure, so the relational spec tables and the legacy specs string
stay in agreement.

- parse(ptype, specs) -> Struct: scalars (mapped to DB columns), the count-list
  fields (slots / RAM slots / ports), storage CHS split into ints, and a
  key/value fallback for free-form types. A drive with a geometry but no stated
  capacity has one worked out from it; a stated capacity is always kept.
- format(ptype, struct) -> specs string: the canonical rendering, used to keep
  parts.specs as a denormalised cache and to render spec tables.

Everything here is pure (no DB); models.py owns the tables and main.py maps a
Struct onto them.
"""
from __future__ import annotations

import re

from .entry import fmt_kb, parse_specs

# Spec-key -> column name, per typed table. Aliases (Chipset->chip) collapse on
# the way in; format() uses the display order below on the way out.
SCALARS = {
    "motherboard": {"Chipset": "chipset", "CPU family": "cpu_family",
                    "Form factor": "form_factor", "Onboard RAM": "onboard_ram",
                    "Cache": "cache_kb", "BIOS": "bios",
                    "Onboard video": "onboard_video"},
    "cpu": {"Socket": "socket", "Speed": "speed_khz", "FSB": "fsb_khz",
            "Cores": "cores", "Cache": "cache_kb", "L2 cache": "cache_kb",
            "L1/L2 cache": "cache_kb"},
    "ram": {"Type": "ram_type", "Size": "size_kb", "Speed": "speed_ns"},
    "video": {"Chip": "chip", "Chipset": "chip", "Interface": "interface",
              "Connector": "connector", "Memory": "memory_kb", "Type": "video_type"},
    "sound": {"Chip": "chip", "Chipset": "chip", "Interface": "interface",
              "FM": "fm", "Ports": "ports"},
    "network": {"Chip": "chip", "Chipset": "chip", "Interface": "interface",
                "Connector": "connector"},
    "io": {"Chip": "chip", "Chipset": "chip", "Interface": "interface"},
    "storage": {"Kind": "kind", "Interface": "interface", "Protocol": "protocol",
                "Capacity": "capacity_kb", "Media": "media", "Speed": "speed_rpm",
                "Role": "role", "Colour": "colour", "Yellowing": "yellowing"},
}

# --- numeric columns -------------------------------------------------------
# Quantities are stored as plain integers in the unit named by the column suffix,
# so they sort and compare in SQL; format() renders them back to friendly units.
# Anything that will not parse becomes a verbatim attribute instead (see parse).
KB_COLS = {"size_kb", "memory_kb", "capacity_kb", "cache_kb"}
KHZ_COLS = {"speed_khz", "fsb_khz"}
NS_COLS = {"speed_ns"}
RPM_COLS = {"speed_rpm"}
INT_COLS = {"cores"}

# A unitless number means MB for a drive capacity ('44'), but KB everywhere else
# ('256' cache). Real data relies on this: RH-0247's bare '44' is 44 MB, which
# its recorded CHS geometry confirms.
KB_BARE_MB_COLS = {"capacity_kb"}
# Every KB column is rendered in the unit a person would use, by entry.fmt_kb --
# a 20 GB drive is not '20971520 KB', and a 2 MB SIMM is not '2048 KB'. Which unit
# is a rendering question; the column stays a plain KB integer.

# Count-list spec keys, per type -> which Struct list they populate.
LIST_KEYS = {
    "motherboard": {"Slots": "slots", "RAM slots": "ram_slots", "Ports": "ports"},
    "io": {"Ports": "ports"},
}

# Display order per type for format() (includes list + CHS keys).
ORDER = {
    "motherboard": ["Chipset", "CPU family", "Form factor", "RAM slots",
                    "Onboard RAM", "Slots", "Cache", "BIOS", "Onboard video",
                    "Ports"],
    "cpu": ["Socket", "Speed", "FSB", "Cores", "Cache"],
    "ram": ["Type", "Size", "Speed"],
    "video": ["Chip", "Interface", "Connector", "Memory", "Type"],
    "sound": ["Chip", "Interface", "FM", "Ports"],
    "network": ["Chip", "Interface", "Connector"],
    "io": ["Chip", "Interface", "Ports"],
    "storage": ["Kind", "Interface", "Protocol", "Capacity", "CHS", "Media",
                "Speed", "Role", "Colour", "Yellowing"],
}
# Which column a display key reads from in format() (first alias wins).
DISPLAY_COL = {t: {} for t in SCALARS}
for _t, _m in SCALARS.items():
    for _key, _col in _m.items():
        DISPLAY_COL[_t].setdefault(_col, _key)

TYPED = set(SCALARS)

_COUNT_RE = re.compile(r"^\s*(\d+)\s*[×x]\s*(.+?)\s*$")
_KB_RE = re.compile(r"^\s*([\d.]+)\s*([kKmMgG]?)[bB]?\s*$")
_CHS_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*$")
_MHZ_RE = re.compile(r"^\s*([\d.]+)\s*(mhz|khz)?\s*$", re.I)
_NS_RE = re.compile(r"^\s*(\d+)\s*(?:ns)?\s*$", re.I)
_RPM_RE = re.compile(r"^\s*(\d+)\s*(?:rpm)?\s*$", re.I)


class Struct:
    __slots__ = ("attributes", "chs", "ports", "ram_slots", "scalars", "slots")

    def __init__(self):
        self.scalars = {}
        self.slots = []
        self.ram_slots = []
        self.ports = []
        self.chs = None
        self.attributes = []


def _to_kb(text, bare=1):
    """'2MB'->2048, '20GB'->20971520, '32.4MB'->33178. `bare` is the multiplier
    applied to a unitless number (see KB_BARE_MB_COLS)."""
    m = _KB_RE.match(text or "")
    if not m:
        return None
    unit = m.group(2).lower()
    mult = {"k": 1, "m": 1024, "g": 1024 * 1024}.get(unit, bare)
    try:
        return round(float(m.group(1)) * mult)
    except ValueError:
        return None


def _to_khz(text):
    """'25 MHz'->25000, '4.77MHz'->4770, '33'->33000, '1475 kHz'->1475. A unitless
    number is MHz, which is how clock speeds are actually written."""
    m = _MHZ_RE.match(text or "")
    if not m:
        return None
    mult = 1 if (m.group(2) or "").lower() == "khz" else 1000
    try:
        return round(float(m.group(1)) * mult)
    except ValueError:
        return None


def _simple_int(pattern):
    def parse(text):
        m = pattern.match(text or "")
        return int(m.group(1)) if m else None
    return parse


def _fmt_khz(khz):
    """Render as MHz when that is exactly reversible, else keep kHz -- so a stored
    speed never drifts by being rounded to the nearest MHz on display."""
    if khz % 1000 == 0:
        return f"{khz // 1000} MHz"
    text = f"{khz / 1000:g}"
    if round(float(text) * 1000) == khz:
        return f"{text} MHz"
    return f"{khz} kHz"


def numeric_handler(col, display=False):
    """(parse, format) for a numeric column, or None if the column is free text.

    `display` is passed through to the KB formatter: on for text that is only read,
    off for the edit form and the stored specs string, which are parsed back."""
    if col in KB_COLS:
        bare = 1024 if col in KB_BARE_MB_COLS else 1
        # A spec that says zero is saying something ('Cache: 0'), where a memory
        # total of zero is just a machine with none recorded -- so this does not
        # inherit fmt_kb's nothing-for-nothing.
        return ((lambda v: _to_kb(v, bare)),
                (lambda n: fmt_kb(n, display=display) if n else f"{n} KB"))
    if col in KHZ_COLS:
        return _to_khz, _fmt_khz
    if col in NS_COLS:
        return _simple_int(_NS_RE), (lambda n: f"{n} ns")
    if col in RPM_COLS:
        return _simple_int(_RPM_RE), (lambda n: f"{n} rpm")
    if col in INT_COLS:
        return _simple_int(re.compile(r"^\s*(\d+)")), str
    return None


def chs_capacity_kb(chs):
    """Capacity in KB from a drive's geometry: cylinders x heads x sectors, each
    sector 512 bytes, which is every drive this catalogue holds.

    A KB being 1024 bytes, two sectors make one, so the arithmetic is that simple.
    A geometry of 615/4/17 comes to 20,910 KB -- near enough the "20MB" written on
    the label to corroborate it, and far enough off to show why a figure a person
    typed is left alone rather than being corrected to this one.
    """
    c, h, sec = chs
    return (c * h * sec) // 2


def _parse_counts(value):
    """'2× 8-bit ISA, 6× 16-bit ISA, VLB' -> [('8-bit ISA', 2), ('16-bit ISA', 6),
    ('VLB', 1)]."""
    out = []
    for tok in (value or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = _COUNT_RE.match(tok)
        if m:
            out.append((m.group(2).strip(), int(m.group(1))))
        else:
            out.append((tok, 1))
    return out


def _fmt_counts(items):
    return ", ".join(f"{n}× {name}" if n and n > 1 else name for name, n in items)


def parse(ptype, specs) -> Struct:
    s = Struct()
    pairs = parse_specs(specs)
    if ptype not in TYPED:
        s.attributes = list(pairs)
        return s
    scalar_map = SCALARS[ptype]
    list_map = LIST_KEYS.get(ptype, {})
    for k, v in pairs:
        if not k:
            # A bare value with no key (messy legacy entry) -- keep it verbatim.
            s.attributes.append((k, v))
            continue
        if k in list_map:
            getattr(s, list_map[k]).extend(_parse_counts(v))
        elif ptype == "storage" and k == "CHS":
            m = _CHS_RE.match(v)
            s.chs = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
            if not m:
                s.attributes.append((k, v))
        elif k in scalar_map:
            col = scalar_map[k]
            handler = numeric_handler(col)
            if handler:
                n = handler[0](v)
                s.scalars[col] = n
                if n is None:
                    # Not a number ('Fake', '20MB (36MB?!)'): keep it verbatim
                    # rather than dropping it on the floor.
                    s.attributes.append((k, v))
            else:
                s.scalars[col] = v
        else:
            s.attributes.append((k, v))
    if ptype == "storage" and s.chs and "capacity_kb" not in s.scalars:
        s.scalars["capacity_kb"] = chs_capacity_kb(s.chs)
    return s


def pairs(ptype, s, display=False):
    """Canonical ordered (display key, rendered value) pairs for a Struct.

    The single source of display order, shared by format() and by the templates
    that render a spec table straight from the typed tables.

    `display` on renders quantities for reading rather than for parsing back: pass
    it for a page or a label, leave it off for the edit form and for format(),
    whose output is stored and re-parsed on the next save.
    """
    pairs = []
    if ptype in ORDER:
        for key in ORDER[ptype]:
            if key in ("Slots", "RAM slots", "Ports") and key in LIST_KEYS.get(ptype, {}):
                items = getattr(s, LIST_KEYS[ptype][key])
                if items:
                    pairs.append((key, _fmt_counts(items)))
            elif key == "CHS" and ptype == "storage":
                if s.chs:
                    pairs.append(("CHS", "{}/{}/{}".format(*s.chs)))
            else:
                col = SCALARS[ptype].get(key)
                if col and s.scalars.get(col) not in (None, ""):
                    val = s.scalars[col]
                    handler = numeric_handler(col, display)
                    pairs.append((key, handler[1](val)
                                  if handler and isinstance(val, (int, float))
                                  else str(val)))
    pairs.extend(s.attributes)
    return pairs


def join(rendered) -> str:
    """Already-rendered pairs as one specs string. The separator lives here so the
    stored string and any prose built from display pairs read the same."""
    return " | ".join(f"{k}: {v}" if k else str(v) for k, v in rendered)


def format(ptype, s) -> str:
    """Canonical specs string from a Struct (or a mapping produced by main.py)."""
    return join(pairs(ptype, s))
