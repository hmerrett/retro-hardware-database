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


def _machine(fields):
    """Fold the flat machine_* arguments into the nested `machine` object the API
    takes. Left out entirely when none of them were given, which is what tells the
    API to leave a machine's catalogue rows alone; a blank machine_model_key means
    the opposite, forget the catalogue for that machine."""
    machine = {
        k[len("machine_") :]: fields.pop(k) for k in list(fields) if k.startswith("machine_")
    }
    if machine:
        fields["machine"] = machine
    return fields


# --- computers -------------------------------------------------------------


@mcp.tool()
def list_computers() -> list[dict]:
    """List every computer (whole machine) in the asset register."""
    return _request("GET", "/api/computers")


@mcp.tool()
def list_machine_models() -> dict:
    """The catalogue of known home computers and consoles -- three hundred of them
    from seventy-odd makers in Britain, Europe, America and Japan: Sinclair,
    Commodore,
    Atari, Acorn, Amstrad, Oric, Dragon, Thomson, Apple, Tandy, TI, Sega,
    Nintendo, NEC, Sharp, Fujitsu, MSX and more -- and the variations each model
    was built in: its standard memory sizes, board issues, case and keyboard
    styles, regions, and the chip sockets with the part numbers that turn up in
    them.

    Call this before creating or updating one of these machines: `key` is what the
    `machine_model_key` argument takes, and the chip roles it lists are the keys of
    `machine_chips`. Every list names what is commonly seen rather than everything
    that exists, so a board or a chip from outside one can still be recorded as it
    is."""
    return _request("GET", "/api/machines")


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
    serial: str | None = None,
    chassis: str | None = None,
    os: str | None = None,
    cpu: str | None = None,
    topbench: int | None = None,
    installed_ram: str | None = None,
    drives: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    location: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
    machine_model_key: str | None = None,
    machine_issue: str | None = None,
    machine_style: str | None = None,
    machine_region: str | None = None,
    machine_chips: dict[str, str] | None = None,
    work_needed: str | None = None,
    work_project: str | None = None,
) -> dict:
    """Create a computer. The server assigns the asset id from the register shared
    with parts. CPU, installed_ram and drives (floppy/optical/CF-SD, ';'-separated)
    are attributes of the computer, not separate parts. installed_ram takes a
    plain amount ('640KiB'); the per-module breakdown is entered in the GUI.

    topbench is what the machine scores in TopBench, the DOS benchmark -- an x86
    machine only, and only once it has actually been run on this machine. Leave it
    out otherwise: an unmeasured machine has no score, and one must never be
    guessed from the CPU.

    serial is the number stamped on this particular machine, which is the one field
    here that is not a fact about the model. Only ever from the object itself: it
    cannot be inferred from anything else, and a wrong one is worse than none.

    location is where the machine is physically kept, in the owner's own words --
    'Loft, blue crate 3', 'Garage shelf B'. Free text, and only ever what somebody
    has said: it cannot be worked out from anything else in the record.

    For a home computer or a console -- a Spectrum, a C64, an Apple IIe, an MSX --
    the machine_* arguments file it against the catalogue that list_machine_models
    returns: machine_model_key is that model's key, machine_issue the board as its
    make marked it ('Issue 6A', 'ASSY 250425', 'VA6'), machine_style the case or
    keyboard it was built with, machine_region the market it was sold in, and
    machine_chips a {role: part number} map for its sockets ({'ula':
    'Ferranti 6C001E-7'}). A role that model has no socket for is refused.

    work_needed is what the thing needs doing, one job to a line, written at the
    moment it is checked in -- 'recap the PSU', 'new belt', 'keyboard sticks'. It
    raises a project about this item with each line as a job on it, named after the
    item -- what it is called, or its tag where it has no name yet -- and the
    reply's `project` names it. Readable by anybody, like the rest of the register
    (ADR-0004); the tick on a project's own form is what keeps one back. Only what
    somebody actually said is wrong: a fault is an observation, never a guess from
    the age or the model. work_project puts it on a project already going instead of
    raising one -- what a part bought for a build in hand is for -- and takes that
    project's asset id; one that does not exist is refused."""
    return _request("POST", "/api/computers", json=_machine(_clean(locals())))


@mcp.tool()
def update_computer(
    asset_id: str,
    name: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    year: int | None = None,
    serial: str | None = None,
    chassis: str | None = None,
    os: str | None = None,
    cpu: str | None = None,
    topbench: int | None = None,
    installed_ram: str | None = None,
    drives: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    location: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
    machine_model_key: str | None = None,
    machine_issue: str | None = None,
    machine_style: str | None = None,
    machine_region: str | None = None,
    machine_chips: dict[str, str] | None = None,
) -> dict:
    """Partial-update a computer: only the fields you pass are changed. Set
    disposed true to flag it disposed, with disposed_at (ISO date) and
    disposed_note for when and why; set it false to undo.

    The machine_* arguments record a catalogue machine's identity and work the same
    way (see create_computer and list_machine_models): passing one leaves the others
    as they are, and machine_chips replaces the whole set of chips rather than
    merging into it. An empty machine_model_key files the machine out of the
    catalogue, which forgets its board issue and chips with it."""
    fields = _clean(locals())
    fields.pop("asset_id")
    return _request("PATCH", f"/api/computers/{asset_id}", json=_machine(fields))


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
    serial: str | None = None,
    specs: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    location: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
    disk_image: str | None = None,
    machine_model_key: str | None = None,
    machine_issue: str | None = None,
    machine_chips: dict[str, str] | None = None,
    work_needed: str | None = None,
    work_project: str | None = None,
) -> dict:
    """Create a part. The server assigns the asset id. computer_id installs it in a
    computer and parent_id mounts it on another part (a disk on a controller card,
    say); both blank means standalone. specs is free text formatted
    'Key: value | Key: value'. serial is the number marked on this particular one,
    read off the object and never inferred. location is where the part itself is
    kept ('Spares drawer'), which is not computer_id read another way -- a card
    fitted in a machine is wherever that machine is, and a card in a drawer is in
    the drawer. Storage parts are mechanical hard disks
    and tape (type 'storage', with a 'Kind' spec); the motherboard carries Chipset, CPU
    family, Form factor, RAM slots, Slots, Cache, BIOS, Onboard video, Ports; a
    screen (type 'display') carries Type (CRT, LCD, OLED), Panel (the mask or panel
    it is built with -- a Trinitron is a CRT with an aperture grille, and both are
    recorded), Screen size (the diagonal in inches), Aspect, Resolution, Refresh and
    Sync (the rates it will do, comma-separated, or the range a multiscan claims),
    Dot pitch, Interface, Picture (colour, or the phosphor of a monochrome tube),
    Colour and Yellowing.

    A motherboard, and only a motherboard, can also be filed against the catalogue
    that list_machine_models returns: machine_model_key is which machine the board
    is out of, machine_issue the revision as its make marked it ('Rev 6A', 'ASSY
    250425'), and machine_chips a {role: part number} map for its sockets. That is
    how a bare Amiga 500 board on a shelf is recorded as what it is. The case style
    and the region are not asked of a board -- they are facts about a whole machine
    in a case.

    work_needed is what this one needs doing, one job to a line, written as it is
    checked in -- 'pins bent', 'recap'. It raises a project about this part with each
    line as a job on it, named after the item -- what it is called, or its tag where
    it has no name yet -- and the reply's `project` names it. Readable by anybody,
    like the rest of the register (ADR-0004); the tick on a project's own form is
    what keeps one back. Only what somebody actually said is wrong: a fault is an
    observation, never a guess from the age or the model. work_project puts it
    on a project already going instead of raising one -- what a part bought for a
    build in hand is for -- and takes that project's asset id; one that does not
    exist is refused."""
    return _request("POST", "/api/parts", json=_machine(_clean(locals())))


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
    serial: str | None = None,
    specs: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    location: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: bool | None = None,
    disposed_at: str | None = None,
    disposed_note: str | None = None,
    disk_image: str | None = None,
    machine_model_key: str | None = None,
    machine_issue: str | None = None,
    machine_chips: dict[str, str] | None = None,
) -> dict:
    """Partial-update a part: only the fields you pass are changed. To move a part
    to another machine set computer_id, to mount it on another part set parent_id,
    and to make it standalone set either to ''.

    The machine_* arguments file a motherboard against the catalogue and work as
    they do on a computer (see create_part and list_machine_models): passing one
    leaves the others alone, machine_chips replaces the whole set of chips, and an
    empty machine_model_key files the board out of the catalogue."""
    fields = _clean(locals())
    fields.pop("asset_id")
    return _request("PATCH", f"/api/parts/{asset_id}", json=_machine(fields))


@mcp.tool()
def delete_part(asset_id: str) -> dict:
    """Delete a part by asset id, with its specs, photos and history. Anything
    mounted on it is unlinked, not deleted. Irreversible; set disposed instead to
    record that it has left the collection."""
    return _request("DELETE", f"/api/parts/{asset_id}")


# --- projects ---------------------------------------------------------------
# The work, as against the things it is done to. A project is the third kind of
# thing in the register: it takes an asset id like a computer or a part, keeps a
# history like one, and is about neither -- it is a repair, a build, or a machine
# still being looked for.
#
# The three lists a project holds are written one row at a time rather than sent
# whole. A task is a row somebody ticks, not a field of the project, and a tool
# that read the list, changed one line and posted the lot back would silently drop
# whatever had been added in between.


@mcp.tool()
def list_projects(status: str | None = None, open: bool | None = None) -> list[dict]:
    """List projects -- repairs, builds and machines still being looked for -- each
    with what it is about, what is still to do and what is on order.

    status is one of planned, active, stalled, done, abandoned. open=true is the
    ones neither finished nor abandoned, which is usually the question being asked;
    call it with no arguments for everything.

    Private ones are listed here like any other: this server talks to the API, which
    is behind the login entire. What `private` governs is what the public site
    shows."""
    return _request("GET", "/api/projects", params=_clean({"status": status, "open": open}))


@mcp.tool()
def get_project(asset_id: str) -> dict:
    """Fetch one project by its asset id, with its items, tasks and orders."""
    return _request("GET", f"/api/projects/{asset_id}")


@mcp.tool()
def create_project(
    name: str,
    status: str | None = None,
    private: bool | None = None,
    summary: str | None = None,
    notes: str | None = None,
    started_at: str | None = None,
    target_date: str | None = None,
    finished_at: str | None = None,
) -> dict:
    """Start a project. Only the name is required -- it is the only thing a project
    can be found by, having no manufacturer or model to fall back on.

    status defaults to planned; the others are planned, active, stalled, done and
    abandoned. The three dates are ISO (YYYY-MM-DD) and independent of each other:
    started_at is when work began, target_date is when it is wanted by, finished_at
    is when it was done, and a project can be finished without ever having been
    recorded as started.

    private=true keeps it off the public site: out of the projects list, out of the
    search, out of the sitemap, off the pages of the machines it is about, and its
    own page answers a stranger as though it were not there. Use it for what is
    wrong with a thing in the owner's own words, which is not finished being decided;
    leave it off for work worth reading about.

    A project need own nothing. Create it first and add the hardware with
    add_project_item as it turns up."""
    fields = _clean(locals())
    return _request("POST", "/api/projects", json=fields)


@mcp.tool()
def update_project(
    asset_id: str,
    name: str | None = None,
    status: str | None = None,
    private: bool | None = None,
    summary: str | None = None,
    notes: str | None = None,
    started_at: str | None = None,
    target_date: str | None = None,
    finished_at: str | None = None,
) -> dict:
    """Partial-update a project: only the fields you pass are changed. Use this to
    move it between states -- status='active' when work starts, 'done' when it is
    over -- and private=false to publish one that was kept back."""
    fields = _clean(locals())
    fields.pop("asset_id")
    return _request("PATCH", f"/api/projects/{asset_id}", json=fields)


@mcp.tool()
def delete_project(asset_id: str) -> dict:
    """Delete a project with its tasks, orders and history. The computers and parts
    it was about are untouched -- deleting the plan is not disposing of the
    hardware. Irreversible; set status='abandoned' to record that it was given up
    on instead."""
    return _request("DELETE", f"/api/projects/{asset_id}")


@mcp.tool()
def add_project_item(project_id: str, asset_id: str, note: str | None = None) -> dict:
    """Say that a project is about a computer or a part, e.g. the machine being
    repaired or the board being used as a donor. note says why it is there.

    The asset must already be in the register: a project is about things that
    exist. Returns the project as it now stands."""
    return _request(
        "POST",
        f"/api/projects/{project_id}/items",
        json=_clean({"asset_id": asset_id, "note": note}),
    )


@mcp.tool()
def remove_project_item(project_id: str, asset_id: str) -> dict:
    """Take a computer or part out of a project. The item itself is untouched."""
    return _request("DELETE", f"/api/projects/{project_id}/items/{asset_id}")


@mcp.tool()
def add_project_task(project_id: str, text: str, done: bool = False) -> dict:
    """Add a job to a project's list. Deliberately just a sentence and a tick --
    write it in the words it will be recognised by."""
    return _request("POST", f"/api/projects/{project_id}/tasks", json={"text": text, "done": done})


@mcp.tool()
def update_project_task(
    project_id: str, task_id: int, text: str | None = None, done: bool | None = None
) -> dict:
    """Tick a job off, put it back, or reword it. Ticking dates it with today;
    un-ticking clears that date, because a job that is not done has no day it was
    done on."""
    return _request(
        "PATCH",
        f"/api/projects/{project_id}/tasks/{task_id}",
        json=_clean({"text": text, "done": done}),
    )


@mcp.tool()
def delete_project_task(project_id: str, task_id: int) -> dict:
    """Remove a job from a project's list altogether. To record that it was done,
    tick it with update_project_task instead."""
    return _request("DELETE", f"/api/projects/{project_id}/tasks/{task_id}")


@mcp.tool()
def add_project_order(
    project_id: str,
    description: str,
    supplier: str | None = None,
    url: str | None = None,
    qty: int | None = None,
    cost_p: int | None = None,
    ordered_at: str | None = None,
    expected_at: str | None = None,
    note: str | None = None,
) -> dict:
    """Record something bought for a project.

    cost_p is PENCE, as a whole number: £12.99 is 1299. It is the cost of the whole
    line as paid, not a unit price -- four SIMMs for twelve pounds is qty=4 and
    cost_p=1200. Leave it out for a cost not written down, which is not the same as
    free: the totals count unpriced lines separately rather than as zero.

    ordered_at defaults to today. Nothing here becomes a part: when it arrives, tick
    it with mark_project_order_delivered and add the item to the register the
    ordinary way with create_part."""
    fields = _clean(locals())
    fields.pop("project_id")
    return _request("POST", f"/api/projects/{project_id}/orders", json=fields)


@mcp.tool()
def mark_project_order_delivered(project_id: str, order_id: int, delivered: bool = True) -> dict:
    """Tick an order as arrived, dating it today; pass delivered=false to put it
    back to still coming, which clears that date."""
    return _request(
        "PATCH", f"/api/projects/{project_id}/orders/{order_id}", json={"delivered": delivered}
    )


@mcp.tool()
def delete_project_order(project_id: str, order_id: int) -> dict:
    """Remove an order from a project -- a cancelled order, or one entered by
    mistake. To record that it arrived, tick it instead."""
    return _request("DELETE", f"/api/projects/{project_id}/orders/{order_id}")


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=MCP_HOST, port=MCP_PORT)
