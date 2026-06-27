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
    "image", "theretroweb_url", "wikipedia_url", "summary", "notes",
]

PART_COLUMNS = [
    "asset_id", "computer_id", "type", "manufacturer", "model", "name",
    "year", "specs", "condition", "source", "acquired_date",
    "image", "theretroweb_url", "wikipedia_url", "summary", "notes",
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
        cid = p.get("computer_id", "")
        if cid and cid not in comp_ids:
            warnings.append(
                f"parts.csv: {p['asset_id']} references unknown computer_id {cid}")
    return warnings


# --- presets (generic, reusable components) --------------------------------

PRESETS_PATH = ROOT / "data" / "presets.csv"
PRESET_COLUMNS = ["key", "type", "manufacturer", "name", "specs"]


def load_presets() -> dict:
    """key -> preset row, from data/presets.csv (empty dict if missing)."""
    rows = _read(PRESETS_PATH, PRESET_COLUMNS)
    return {r["key"]: r for r in rows if r.get("key")}
