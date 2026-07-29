"""API-backed data access + shared helpers for the ported utilities.

A drop-in successor to the flat-file system's scripts/common.py: it exposes the
same helper names, but instead of reading/writing CSVs it talks to the REST API
(the single source of truth). The label maker and the report importer both
import from here, so they read/write exactly what the GUI and MCP server do.

Point it at the API with, in order of precedence: --api on the command line
(scripts set RHDB_API before importing), the RHDB_API env var, config.yml's
api_url, else http://localhost:8000.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests
import yaml

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR
CONFIG_PATH = BASE_DIR / "config.yml"

TIMEOUT = 30

PART_COLUMNS = [
    "asset_id", "computer_id", "type", "manufacturer", "model", "name",
    "year", "specs", "condition", "source", "acquired_date",
    "image", "url", "summary", "notes", "disposed", "disk_image",
]

TYPE_ORDER = [
    "motherboard", "cpu", "ram", "video", "sound", "network", "io",
    "storage", "cooler", "peripheral", "other",
]

TYPE_LABELS = {
    "motherboard": "Motherboard", "cpu": "CPU", "ram": "Memory", "video": "Video",
    "sound": "Sound", "network": "Network", "io": "I/O", "storage": "Storage",
    "optical": "Optical drive", "floppy": "Floppy drive", "psu": "Power supply",
    "cooler": "Cooling", "peripheral": "Peripheral", "other": "Other",
}


# --- config ----------------------------------------------------------------

_config_cache = None


def load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    return _config_cache


def api_base() -> str:
    url = (os.getenv("RHDB_API") or load_config().get("api_url")
           or "http://localhost:8000")
    return url.rstrip("/")


def api_auth():
    """HTTP Basic credentials for the API, if it requires them. From
    RHDB_AUTH_USER / RHDB_AUTH_PASSWORD (env) or config; None if unset."""
    cfg = load_config()
    user = os.getenv("RHDB_AUTH_USER") or cfg.get("auth_user") or ""
    pw = os.getenv("RHDB_AUTH_PASSWORD") or cfg.get("auth_password") or ""
    return (user, pw) if user and pw else None


# --- HTTP / data access ----------------------------------------------------

def _request(method, path, **kwargs):
    resp = requests.request(method, f"{api_base()}{path}", timeout=TIMEOUT,
                            auth=api_auth(), **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"API {method} {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def load_computers() -> list[dict]:
    return _request("GET", "/api/computers")


def load_parts() -> list[dict]:
    return _request("GET", "/api/parts")


def update_computer(asset_id: str, fields: dict) -> dict:
    return _request("PATCH", f"/api/computers/{asset_id}", json=fields)


def update_part(asset_id: str, fields: dict) -> dict:
    return _request("PATCH", f"/api/parts/{asset_id}", json=fields)


def create_part(fields: dict) -> dict:
    return _request("POST", "/api/parts", json=fields)


# --- pure helpers (verbatim from the flat-file common.py) ------------------

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


def add_api_arg(parser):
    """Give a script a --api flag; when passed, it wins over env/config by
    setting RHDB_API before any request is made."""
    parser.add_argument("--api", default="",
                        help="REST API base URL (default: RHDB_API / config api_url)")


def apply_api_arg(args):
    if getattr(args, "api", ""):
        os.environ["RHDB_API"] = args.api
