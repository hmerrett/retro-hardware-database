"""Reports, sent the way the survey agent sends them. Not a test.

Shared by the tests of surveys (MANUAL §23, ADR-0043): a report as a survey
program writes one, the agent's two calls with its own key, and the owner's
answers on a survey's page. Every helper checks the status it was given, so a
route that is not there yet fails here, plainly, rather than as a dictionary
that happens to have the length a test was counting.
"""

AGENTS = "bench:key-one,attic:key-two:workshop-pi"
PRINTERS = "workshop-pi:key-print:dymo-11355:pdf"

MAC = "00:00:C0:12:34:56"

# An IDE disk as ATA IDENTIFY describes it, and the card the survey ran through.
DISK = {
    "DISK1_MODEL": "QUANTUM FIREBALL1080A",
    "DISK1_SERIAL": "QX123",
    "DISK1_KB": "1056768",
    "DISK1_CHS": "2097/16/63",
    "DISK1_TYPE": "ATA",
}
NIC = {"NIC_MAC": MAC, "NIC_DRIVER": "NE2000"}

# The keys every report carries, whatever else it says. A test passes None to
# take one out.
BASE = {
    "TOOL": "DIAG",
    "VERSION": "1.0",
    "DATE": "11/06/2026",
    "TIME": "09:30:00",
    "MODE": "ONCE",
    "RESULT": "PASS",
    "TESTS": "1",
    "PASSED": "1",
    "TEST_CPU": "PASS",
}

# A ROM as a survey copies one: the option ROM signature, then the words in it.
BIOS_ROM = (
    b"\x55\xaa\x80"
    + b"Award Modular BIOS v4.51PG, An Energy Star Ally\0"
    + b"Copyright (C) 1984-98, Award Software, Inc.\0"
    + b"\0" * 200
)
VGA_ROM = b"\x55\xaa\x40" + b"Tseng Labs ET4000 VGA BIOS Version 8.00\0" + b"\0" * 200
BOOT_ROM = b"\x55\xaa\x20" + b"netboot 0.8.1 NE2000 boot ROM\0" + b"\0" * 200
# netboot 0.8.1's ROM as boot-lan builds it: everything but its author's copyright
# line is compressed, and it carries neither a PCI class nor a Plug and Play type.
NETBOOT_ROM = (
    b"\x55\xaa\x20\xeb"
    + b"\0" * 60
    + b"Copyright (C) 1995-1998 G. Kuhlmann\0Uncompressing... \0Press a key to reboot\0"
    + bytes(range(0x80, 0x100)) * 8
)
# A ROM whose only words naming a maker are a message it prints, as QEMU's VGA BIOS
# has: nothing in it is the card's name.
CHATTY_ROM = b"\x55\xaa\x40" + b"cirrus mode switch regular\0set VGA mode %x\0" + b"\0" * 200
# A disk controller's ROM that names nobody.
ANONYMOUS_ROM = b"\x55\xaa\x10" + b"Press F1 to continue\0Drive not ready\0" + b"\0" * 200

# System BIOSes, as the copy of the top of the first megabyte reads. Compaq wrote its
# own, and its words say so; HP and Dell had Phoenix write theirs and put their name
# in it; a clone's carries COMPAQ for software that looks for it.
COMPAQ_BIOS = (
    b"\0" * 16 + b"COMPAQ\0102-System Board Failure\0You must load COMPAQ BASIC\0" + b"\0" * 200
)
HP_BIOS = (
    b"\0" * 16
    + b"Phoenix ROM BIOS PLUS Version 1.10 A.01\0"
    + b"Copyright (C) 1985-1991 Phoenix Technologies Ltd.\0"
    + b"(C) Copyright Hewlett-Packard Company 1991\0"
    + b"\0" * 200
)
DELL_BIOS = (
    b"\0" * 16
    + b"Phoenix ROM BIOS PLUS Version 1.10 A07\0"
    + b"Copyright 1985-1993 Phoenix Technologies Ltd.\0"
    + b"Dell Computer Corporation\0"
    + b"\0" * 200
)
CLONE_BIOS = (
    b"\0" * 16
    + b"Phoenix 80386 ROM BIOS PLUS Version 1.10 22\0"
    + b"Copyright (C) 1985-1990 Phoenix Technologies Ltd.\0COMPAQ\0"
    + b"\0" * 200
)

# Card ROMs naming who made the chip or the card: on the banner line itself, on a
# copyright line after the line naming the chip, and on a branded machine's own card,
# whose ROM names its maker and nothing else (the Compaq 286's video BIOS). The XTIDE
# Universal BIOS is a program, on cards anybody might have built.
ADAPTEC_ROM = (
    b"\x55\xaa\x20"
    + b"Adaptec AHA-1540B/1542B BIOS v3.20\0(C) Copyright 1989 Adaptec, Inc.\0"
    + b"\0" * 200
)
CIRRUS_ROM = (
    b"\x55\xaa\x40"
    + b"CL-GD5428 VGA BIOS Version 1.00a\0Copyright 1992-1994 Cirrus Logic, Inc.\0"
    + b"\0" * 200
)
COMPAQ_VGA_ROM = (
    b"\x55\xaa\x30\xeb\x4b"
    + b"\0" * 16
    + b"Copyright COMPAQ Computer Corporation, 1982, 89\0All rights reserved\0"
    + b"\0" * 200
)
XTIDE_ROM = b"\x55\xaa\x10" + b"-=XTIDE Universal BIOS (XT)=-\0" + b"\0" * 200


def report(**keys: str | None) -> str:
    """A report: words for the person reading it, then the [RHDB] section, one
    KEY=VALUE to a line, in DOS's line endings."""
    fields = BASE | keys
    lines = ["DIAG 1.0  hardware report", "", "[RHDB]"]
    lines += [f"{k}={v}" for k, v in fields.items() if v is not None]
    return "\r\n".join(lines) + "\r\n"


def send(client, text, key="key-one", roms=(), taken=None):
    """What the agent does with a report it has found: the report, the ROMs named
    in it, and when it first saw the file, by its own clock."""
    files = [("report", ("RH0001.TXT", text.encode("cp437"), "text/plain"))]
    files += [("roms", (name, data, "application/octet-stream")) for name, data in roms]
    return client.post(
        "/api/survey/agent/surveys",
        files=files,
        data={"taken": taken} if taken else {},
        headers={"Authorization": f"Bearer {key}"},
    )


def survey(client, roms=(), taken=None, key="key-one", **keys) -> dict:
    """Send one report and read back the survey it made."""
    r = send(client, report(**keys), key=key, roms=roms, taken=taken)
    assert r.status_code == 200, r.text
    (made,) = r.json()["surveys"]
    return read(client, made["id"])


def read(client, sid) -> dict:
    r = client.get(f"/api/surveys/{sid}")
    assert r.status_code == 200, r.text
    return r.json()


def ask(client, key="key-one", roms=(), **keys) -> dict[str, str]:
    """The agent's other call: a machine's question, before its tests run, and the
    register's answer, as the KEY=VALUE lines the agent writes beside it. With ROMs,
    as the agent sends one: the question and the ROM copies it names, together; an
    agent from before ROMs went with the question sends the question alone, as
    text."""
    body = ("\r\n".join(["[RHDB]"] + [f"{k}={v}" for k, v in keys.items()]) + "\r\n").encode(
        "cp437"
    )
    headers = {"Authorization": f"Bearer {key}"}
    if roms:
        files = [("question", ("RH0001.ASK", body, "text/plain"))]
        files += [("roms", (name, data, "application/octet-stream")) for name, data in roms]
        r = client.post("/api/survey/agent/ask", files=files, headers=headers)
    else:
        r = client.post(
            "/api/survey/agent/ask",
            content=body,
            headers=headers | {"content-type": "text/plain"},
        )
    assert r.status_code == 200, r.text
    return dict(line.split("=", 1) for line in r.text.splitlines() if "=" in line)


def finding(made: dict, thing: str) -> dict:
    """One thing a survey found, by the name its report gave it (`DISK1`, `NIC`)."""
    found = [f for f in made["findings"] if f["thing"] == thing]
    assert len(found) == 1, f"{thing} is not among {[f['thing'] for f in made['findings']]}"
    return found[0]


def answer(client, made: dict, thing: str, how: str, **extra):
    """An answer given on the survey's page: `new`, `link` (with a `tag`),
    `bench` (with a `bench`), `machine` or `out`."""
    return client.post(
        f"/surveys/{made['id']}/answer",
        data={"thing": thing, "answer": how} | extra,
        follow_redirects=False,
    )


def get(client, kind: str, aid: str) -> dict:
    r = client.get(f"/api/{kind}/{aid}")
    assert r.status_code == 200, r.text
    return r.json()


def parts_in(client, aid: str) -> list[dict]:
    r = client.get(f"/api/parts?computer_id={aid}")
    assert r.status_code == 200, r.text
    return r.json()


def location(client, name: str, kind: str, parent: str | None = None) -> dict:
    r = client.post("/api/locations", json={"name": name, "kind": kind, "parent": parent})
    assert r.status_code == 200, r.text
    return r.json()
