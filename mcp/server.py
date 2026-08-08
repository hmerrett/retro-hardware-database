"""MCP server for the Retro Hardware Database.

A thin wrapper over the REST API (the single source of truth) that exposes
native tools to list / get / create / update / delete computers and parts over
the Model Context Protocol. It holds no data itself -- every tool call is an HTTP
request to the API, so the MCP server, the GUI and the ported scripts all see
exactly the same data.

Runs over the streamable-HTTP transport so it can live as its own always-on
docker-compose service. Point a client at http://<host>:8001/mcp.

year is an integer, acquired_date and disposed_at are ISO date strings
(YYYY-MM-DD), and disposed is a boolean. Since an omitted argument means "leave
unchanged", the integer and date fields can be set but not cleared from here;
clear them in the GUI.
"""
import os

import httpx
from mcp.server.mcpserver import MCPServer

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

# If the API requires HTTP Basic auth, forward the same credentials.
_AUTH_USER = os.getenv("RHDB_AUTH_USER", "")
_AUTH_PASS = os.getenv("RHDB_AUTH_PASSWORD", "")
API_AUTH = (_AUTH_USER, _AUTH_PASS) if _AUTH_USER and _AUTH_PASS else None

mcp = MCPServer("retro-hardware")

# The host and port belong to the transport, not the server, so they are settled
# where it is started rather than here. The default host is loopback, which inside
# a container means nothing outside it can connect.
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))


def _client():
    return httpx.Client(base_url=API_BASE_URL, timeout=30.0, auth=API_AUTH)


def _request(method, path, *, params=None, json=None):
    """One HTTP call to the API, returning parsed JSON. Raises with the API's
    own error body attached so the caller sees why a call failed (e.g. 404)."""
    with _client() as c:
        resp = c.request(method, path, params=params, json=json)
    if resp.status_code >= 400:
        raise RuntimeError(f"API {method} {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def _clean(fields):
    """Drop unset (None) fields so create/update only send what was supplied --
    this is what makes update a genuine partial (PATCH) of just those columns."""
    return {k: v for k, v in fields.items() if v is not None}


# --- computers -------------------------------------------------------------

@mcp.tool()
def list_computers() -> list[dict]:
    """List every computer (whole machine) in the asset register."""
    return _request("GET", "/api/computers")


@mcp.tool()
def get_computer(asset_id: str) -> dict:
    """Fetch one computer by its asset id, e.g. RH-0001."""
    return _request("GET", f"/api/computers/{asset_id}")


@mcp.tool()
def create_computer(
    name: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    year: int | None = None,
    chassis: str | None = None,
    os: str | None = None,
    cpu: str | None = None,
    installed_ram: str | None = None,
    drives: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
) -> dict:
    """Create a computer. The server assigns the asset id from the register shared
    with parts. CPU, installed_ram and drives (floppy/optical/CF-SD, ';'-separated)
    are attributes of the computer, not separate parts. installed_ram takes a
    plain amount ('640KB'); the per-module breakdown is entered in the GUI."""
    return _request("POST", "/api/computers", json=_clean(locals()))


@mcp.tool()
def update_computer(
    asset_id: str,
    name: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    year: int | None = None,
    chassis: str | None = None,
    os: str | None = None,
    cpu: str | None = None,
    installed_ram: str | None = None,
    drives: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
) -> dict:
    """Partial-update a computer: only the fields you pass are changed. Set
    disposed true to flag it disposed, with disposed_at (ISO date) and
    disposed_note for when and why; set it false to undo."""
    fields = _clean(locals())
    fields.pop("asset_id")
    return _request("PATCH", f"/api/computers/{asset_id}", json=fields)


@mcp.tool()
def delete_computer(asset_id: str) -> dict:
    """Delete a computer by asset id. Its parts are not deleted -- they are
    unlinked and become standalone. Its photos, drive and memory rows and history
    go with it, and none of it comes back; to take a machine out of the
    collection reversibly, set disposed instead."""
    return _request("DELETE", f"/api/computers/{asset_id}")


# --- parts -----------------------------------------------------------------

@mcp.tool()
def list_parts(computer_id: str | None = None, type: str | None = None) -> list[dict]:
    """List parts, optionally filtered. Pass computer_id (e.g. RH-0001) for one
    machine's parts, or an empty string for standalone parts. Pass type to filter
    by kind: motherboard, cpu, ram, video, sound, network, io, storage, cooler,
    peripheral, other."""
    params = {}
    if computer_id is not None:
        params["computer_id"] = computer_id
    if type is not None:
        params["type"] = type
    return _request("GET", "/api/parts", params=params)


@mcp.tool()
def get_part(asset_id: str) -> dict:
    """Fetch one part by its asset id, e.g. RH-0003."""
    return _request("GET", f"/api/parts/{asset_id}")


@mcp.tool()
def create_part(
    computer_id: str | None = None,
    parent_id: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    name: str | None = None,
    year: int | None = None,
    specs: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
    disk_image: str | None = None,
) -> dict:
    """Create a part. The server assigns the asset id. computer_id installs it in a
    computer and parent_id mounts it on another part (a disk on a controller card,
    say); both blank means standalone. specs is free text formatted
    'Key: value | Key: value'. Storage parts are mechanical hard disks and tape
    (type 'storage', with a 'Kind' spec); the motherboard carries Chipset, CPU
    family, Form factor, RAM slots, Slots, Cache, BIOS, Onboard video, Ports."""
    return _request("POST", "/api/parts", json=_clean(locals()))


@mcp.tool()
def update_part(
    asset_id: str,
    computer_id: str | None = None,
    parent_id: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    name: str | None = None,
    year: int | None = None,
    specs: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
    disk_image: str | None = None,
) -> dict:
    """Partial-update a part: only the fields you pass are changed. To move a part
    to another machine set computer_id, to mount it on another part set parent_id,
    and to make it standalone set either to ''."""
    fields = _clean(locals())
    fields.pop("asset_id")
    return _request("PATCH", f"/api/parts/{asset_id}", json=fields)


@mcp.tool()
def delete_part(asset_id: str) -> dict:
    """Delete a part by asset id, with its specs, photos and history. Anything
    mounted on it is unlinked, not deleted. Irreversible; set disposed instead to
    record that it has left the collection."""
    return _request("DELETE", f"/api/parts/{asset_id}")


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=MCP_HOST, port=MCP_PORT)
