"""Shared helpers for the Retro Hardware Database scripts.

Two tables, one relationship:

    computers.csv (1) ----< (many) parts.csv
        asset_id   <----------  computer_id

Every physical object (a whole computer OR an individual part) has one unique
asset_id from a single shared register. A part's computer_id is a foreign key
to a computer's asset_id (blank = standalone / not installed).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yml"
COMPUTERS_PATH = ROOT / "data" / "computers.csv"
PARTS_PATH = ROOT / "data" / "parts.csv"
IMAGES_DIR = ROOT / "images"

COMPUTER_COLUMNS = [
    "asset_id", "name", "manufacturer", "model", "year", "form_factor",
    "chassis", "os", "condition", "source", "acquired_date",
    "image", "url", "summary", "notes", "disposed",
]

PART_COLUMNS = [
    "asset_id", "computer_id", "type", "manufacturer", "model", "name",
    "year", "specs", "condition", "source", "acquired_date",
    "image", "url", "summary", "notes", "disposed",
    # storage only: filename of the disk image taken on arrival
    "disk_image",
]

# Controls the order parts are grouped/sorted in (build sheets, filters).
TYPE_ORDER = [
    "motherboard", "cpu", "ram", "gpu", "sound", "network", "io",
    "storage", "optical", "floppy", "psu", "cooler", "peripheral", "other",
]

TYPE_LABELS = {
    "motherboard": "Motherboard", "cpu": "CPU", "ram": "Memory", "gpu": "Video",
    "sound": "Sound", "network": "Network", "io": "I/O", "storage": "Storage",
    "optical": "Optical drive", "floppy": "Floppy drive", "psu": "Power supply",
    "cooler": "Cooling", "peripheral": "Peripheral", "other": "Other",
}


# --- config / IO -----------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read(path: Path, columns: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [{c: (row.get(c) or "").strip() for c in columns} for row in reader]


def _write(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


def load_computers() -> list[dict]:
    return _read(COMPUTERS_PATH, COMPUTER_COLUMNS)


def load_parts() -> list[dict]:
    return _read(PARTS_PATH, PART_COLUMNS)


def save_computers(rows: list[dict]) -> None:
    _write(COMPUTERS_PATH, COMPUTER_COLUMNS, rows)


def save_parts(rows: list[dict]) -> None:
    _write(PARTS_PATH, PART_COLUMNS, rows)


# --- helpers ---------------------------------------------------------------

def display_name(row: dict) -> str:
    """Best human label: explicit name, else manufacturer + model, else id."""
    if row.get("name"):
        return row["name"]
    joined = " ".join(p for p in (row.get("manufacturer", ""),
                                  row.get("model", "")) if p).strip()
    return joined or row.get("asset_id", "")


def parse_specs(specs: str) -> list[tuple[str, str]]:
    """Turn 'CPU: x | RAM: y' into [('CPU','x'), ('RAM','y')]."""
    out = []
    for chunk in (specs or "").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            out.append((k.strip(), v.strip()))
        else:
            out.append(("", chunk))
    return out


def type_label(t: str) -> str:
    return TYPE_LABELS.get(t, (t or "other").title())


def type_sort_key(t: str) -> int:
    try:
        return TYPE_ORDER.index(t)
    except ValueError:
        return len(TYPE_ORDER)


def url_source(url: str) -> str:
    """Which recognised site a reference url points at: 'wikipedia',
    'theretroweb', 'other' (some other site), or '' (no url)."""
    u = (url or "").lower()
    if not u:
        return ""
    if "wikipedia.org" in u:
        return "wikipedia"
    if "theretroweb.com" in u:
        return "theretroweb"
    return "other"


def url_label(url: str) -> str:
    """Display label for a reference link, based on its site."""
    return {"wikipedia": "Wikipedia",
            "theretroweb": "The Retro Web"}.get(url_source(url), "Reference")


def is_disposed(row) -> bool:
    """True if this item has been flagged as disposed of (hidden by default)."""
    return bool((row.get("disposed") or "").strip())


# Hardware acronyms of 4+ letters that must stay upper-case when de-shouting.
SHOUT_ACRONYMS = {
    "SCSI", "SATA", "PATA", "EISA", "ESDI", "VESA", "SVGA", "WXGA", "ATAPI",
    "BIOS", "UEFI", "DRAM", "SRAM", "SDRAM", "VRAM", "SIMM", "DIMM", "RIMM",
    "SIPP", "COAST", "CMOS", "MIDI", "EPROM", "EEPROM", "PROM", "MCGA",
    "PLCC", "NTSC", "SECAM", "WLAN", "ASIC",
}
def deshout(text: str) -> str:
    """De-shout a value word by word: a whitespace-delimited token that is
    purely uppercase letters (5+ long) and not a known acronym becomes
    Capitalised. Tokens up to 4 letters (TYPE, IFSP, SCSI), part numbers with
    digits/hyphens (CL-PCIVT6421E, 3C905B-TXNM) and protected acronyms are all
    left untouched."""
    out = []
    for tok in re.split(r"(\s+)", text or ""):
        core = tok.strip(".,:;()[]{}/\\\"'")
        if (core.isalpha() and core.isupper() and len(core) >= 5
                and core not in SHOUT_ACRONYMS):
            i = tok.find(core)
            tok = tok[:i] + core[0] + core[1:].lower() + tok[i + len(core):]
        out.append(tok)
    return "".join(out)


def index_by_id(rows: list[dict]) -> dict:
    return {r["asset_id"]: r for r in rows}


def parts_for(computer_id: str, parts: list[dict]) -> list[dict]:
    """Parts installed in / paired with a computer, sorted by type then name."""
    kids = [p for p in parts if p.get("computer_id") == computer_id]
    kids.sort(key=lambda p: (type_sort_key(p.get("type", "")), display_name(p)))
    return kids


def item_url(config: dict, asset_id: str) -> str:
    base = (config.get("base_url") or "").rstrip("/")
    return f"{base}/items/{asset_id}/"


# Placeholder icon (in assets/placeholders/) shown when an item has no photo.
PLACEHOLDER = {
    "computer": "computer", "motherboard": "board", "cpu": "chip", "ram": "ram",
    "gpu": "card", "sound": "card", "network": "card", "io": "card",
    "storage": "drive", "optical": "disc", "floppy": "floppy", "psu": "psu",
    "cooler": "fan", "peripheral": "keyboard", "other": "box",
}


def placeholder_for(kind_or_type: str) -> str:
    return "placeholders/" + PLACEHOLDER.get(kind_or_type, "box") + ".svg"


def next_asset_id(config: dict, computers: list[dict], parts: list[dict]) -> str:
    """Next free id across BOTH tables, e.g. RH-0012."""
    prefix = config.get("asset_prefix", "RH-")
    pad = int(config.get("asset_pad", 4))
    nums = []
    for r in (*computers, *parts):
        aid = r.get("asset_id", "")
        if aid.startswith(prefix) and aid[len(prefix):].isdigit():
            nums.append(int(aid[len(prefix):]))
    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}{nxt:0{pad}d}"


# Expected specs keys per part type. Types not listed (peripheral, other, or
# any custom type) accept any keys. Used only for gentle build-time warnings —
# storage stays flexible; this just catches typos and crossed data.
KNOWN_SPEC_KEYS = {
    "motherboard": {"Chipset", "Socket", "Form factor", "RAM slots", "Slots",
                    "Cache", "BIOS"},
    "cpu": {"Socket", "Speed", "FSB", "Cores", "Cache", "L1/L2 cache", "L2 cache"},
    "ram": {"Type", "Size", "Speed"},
    "gpu": {"Interface", "Memory", "Chip", "Chipset", "Type", "Connector"},
    "sound": {"Interface", "Chip", "Chipset", "FM", "Ports"},
    "network": {"Interface", "Connector", "Chip", "Chipset"},
    "io": {"Interface", "Ports", "Chip", "Chipset"},
    "storage": {"Interface", "Protocol", "Capacity", "CHS", "Role"},
    "optical": {"Media", "Interface", "Speed"},
    "floppy": {"Media", "Interface", "Speed"},
    "psu": {"Form factor", "Wattage", "Connectors"},
    "cooler": {"Type", "Socket"},
}


def validate(computers: list[dict], parts: list[dict]) -> list[str]:
    """Return a list of human-readable integrity warnings (empty = all good)."""
    warnings = []
    seen = {}
    for label, rows in (("computers.csv", computers), ("parts.csv", parts)):
        for r in rows:
            aid = r.get("asset_id", "")
            if not aid:
                warnings.append(f"{label}: a row has no asset_id")
                continue
            if aid in seen:
                warnings.append(
                    f"duplicate asset_id {aid} (in {seen[aid]} and {label})")
            seen[aid] = label
    comp_ids = {c["asset_id"] for c in computers}
    for p in parts:
        aid = p.get("asset_id", "")
        cid = p.get("computer_id", "")
        if cid and cid not in comp_ids:
            warnings.append(
                f"parts.csv: {aid} references unknown computer_id {cid}")
        ptype = p.get("type", "")
        allowed = KNOWN_SPEC_KEYS.get(ptype)
        seen_keys = set()
        for k, v in parse_specs(p.get("specs", "")):
            if v.strip().lower().startswith("http"):
                warnings.append(
                    f"parts.csv: {aid} has a link in a spec value — put URLs "
                    "in the url column")
            if not k:
                continue
            if k in seen_keys:
                warnings.append(f"parts.csv: {aid} has duplicate spec key '{k}'")
            seen_keys.add(k)
            if allowed is not None and k not in allowed:
                warnings.append(
                    f"parts.csv: {aid} unexpected spec key '{k}' for type '{ptype}'")
    return warnings


# --- presets (generic, reusable components) --------------------------------

PRESETS_PATH = ROOT / "data" / "presets.csv"
PRESET_COLUMNS = ["key", "type", "manufacturer", "name", "specs"]


def load_presets() -> dict:
    """key -> preset row, from data/presets.csv (empty dict if missing)."""
    rows = _read(PRESETS_PATH, PRESET_COLUMNS)
    return {r["key"]: r for r in rows if r.get("key")}
