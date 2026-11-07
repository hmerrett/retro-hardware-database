"""Surveys: a machine's report of itself, filed against it (MANUAL §23; ADR-0043).

A survey program on the machine tests it and writes a report; an agent beside it sends
the report here. Everything the report says the machine has is a *finding*, and every
finding gets one of three answers: left out, part of the machine (written into the
machine's own record or its motherboard's), or a part of its own (a tagged part fitted
in the machine). The machine itself is one the register has, or a new one.

Most answers are the register's own. What it keeps on a machine's record -- the
processor, the memory, the BIOS, the chipset, the floppy drives -- is always part of
the machine; a hard disk is a part or nothing, because the drives rule says so; a disk
or a card the register has met before is recognised. The rest are asked once, at the
machine or on the survey's page, and remembered: by serial number or address for a
thing that has one, wherever it turns up, and otherwise in the machine it was found in.

Nothing new is made without an answer, nothing recorded is overwritten, and a survey
that cannot be sure which machine it is about does nothing and waits.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NamedTuple, TypedDict, cast

from sqlalchemy.orm import Session

from . import (
    drivedb,
    entry,
    filesdb,
    locations,
    machinedb,
    machines,
    pciids,
    printing,
    ramdb,
    romtext,
    specdb,
    surveyreport,
    tree,
)
from .common import to_dict
from .history import SURVEY_ENTRY, add_log
from .ids import exact_tag, next_asset_id
from .models import (
    Computer,
    FileAsset,
    Location,
    Part,
    StoredFile,
    Survey,
    SurveyAnswer,
    SurveySeen,
    Thing,
)

# The three answers, as the register stores them.
PART, MACHINE, OUT = "part", "machine", "out"

# What a survey can be waiting for.
FOR_MACHINE, FOR_ANSWER = "machine", "answer"

# How the machine was found.
TYPED, NEW, RECOGNISED, FILED = "typed", "new", "recognised", "filed"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- the agents --------------------------------------------------------------------


class Agent(NamedTuple):
    """A survey agent, as the environment names it: `name:key`, and a print agent's
    name after them where the labels of the tags its surveys make are printed."""

    name: str
    key: str
    printer: str


def agents() -> dict[str, Agent]:
    """`RHDB_SURVEY_AGENTS=name:key[:printer],...`, read on every call for the reason
    the print agents are: a value read once is one that lies after it is changed."""
    out: dict[str, Agent] = {}
    for item in os.getenv("RHDB_SURVEY_AGENTS", "").split(","):
        bits = [b.strip() for b in item.split(":")]
        if len(bits) < 2 or not bits[0] or not bits[1]:
            continue
        out[bits[0]] = Agent(bits[0], bits[1], bits[2] if len(bits) > 2 else "")
    return out


def agent_for(key: str) -> Agent | None:
    """The agent a key belongs to, compared in constant time against every one."""
    found = None
    for agent in agents().values():
        if secrets.compare_digest(agent.key, key):
            found = agent
    return found


# --- what a report says, in the register's words ----------------------------------------

# What a BIOS writes where it has nothing to say. A survey that copied one of these into
# a serial number would make every machine of that board the same machine.
PLACEHOLDERS = frozenset(
    {
        "to be filled by o.e.m.",
        "to be filled by oem",
        "system product name",
        "system manufacturer",
        "system serial number",
        "system version",
        "base board serial number",
        "chassis serial number",
        "default string",
        "not specified",
        "not applicable",
        "none",
        "n/a",
        "na",
        "oem",
        "o.e.m.",
        "x",
        "-",
        "0123456789",
        "123456789",
        "1234567890",
        "xxxxxxxx",
    }
)


def said(value: str | None) -> str:
    """What a BIOS said, or "" where what it said is a placeholder or nothing."""
    text = " ".join((value or "").split())
    if not text or text.lower() in PLACEHOLDERS or set(text) <= set("0 F"):
        return ""
    return text


def _int(value: str | None) -> int | None:
    text = (value or "").strip()
    return int(text) if text.isdigit() else None


# CPUID's vendor strings, as the maker a person would write.
_CPU_MAKERS = {
    "GENUINEINTEL": "Intel",
    "AUTHENTICAMD": "AMD",
    "CYRIXINSTEAD": "Cyrix",
    "CENTAURHAULS": "IDT",
    "NEXGENDRIVEN": "NexGen",
    "UMCUMCUMC": "UMC",
    "RISERISERISE": "Rise",
    "GENUINETMX86": "Transmeta",
    "SIS SIS SIS": "SiS",
}

# The speeds chips were sold at. A measured speed close to one of these is that one:
# a 486DX2-66 runs at 66.67 MHz and is never called a 486DX2-67.
_NOMINAL_MHZ = (
    4.77,
    6,
    7.16,
    8,
    10,
    12,
    16,
    20,
    25,
    33,
    40,
    50,
    60,
    66,
    75,
    80,
    90,
    100,
    120,
    133,
    150,
    166,
    180,
    200,
    233,
    266,
    300,
    333,
    350,
    366,
    400,
    433,
    450,
    466,
    500,
    533,
    550,
    600,
)


def _mhz(khz: int) -> str:
    measured = khz / 1000
    near = min(_NOMINAL_MHZ, key=lambda n: abs(n - measured))
    value = near if abs(near - measured) <= max(0.04 * near, 0.5) else round(measured)
    return f"{value:g}"


# What CPUID's family and model call a chip, by its maker: the chips a register of old
# machines meets. A survey program says only the family (tinydiag's PENTIUM is anything
# of the Pentium's generation, an AMD K6-2 included), so the model is what tells them
# apart. One the table does not know is called by the family the program said.
_CPU_MODELS: dict[tuple[str, int], dict[int, str]] = {
    ("Intel", 4): {
        0: "486DX",
        1: "486DX",
        2: "486SX",
        3: "486DX2",
        4: "486SL",
        5: "486SX2",
        7: "486DX2",
        8: "486DX4",
        9: "486DX4",
    },
    ("Intel", 5): {
        1: "Pentium",
        2: "Pentium",
        3: "Pentium OverDrive",
        4: "Pentium MMX",
        7: "Pentium",
        8: "Pentium MMX",
    },
    ("Intel", 6): {
        1: "Pentium Pro",
        3: "Pentium II",
        5: "Pentium II",
        6: "Celeron",
        7: "Pentium III",
        8: "Pentium III",
        9: "Pentium M",
        10: "Pentium III",
        11: "Pentium III",
        13: "Pentium M",
    },
    ("AMD", 4): {3: "486DX2", 7: "486DX2", 8: "486DX4", 9: "486DX4", 14: "5x86", 15: "5x86"},
    ("AMD", 5): {0: "K5", 1: "K5", 2: "K5", 3: "K5", 6: "K6", 7: "K6", 8: "K6-2", 9: "K6-III"},
    ("AMD", 6): {1: "Athlon", 2: "Athlon", 3: "Duron", 4: "Athlon", 6: "Athlon XP", 7: "Duron"},
    ("Cyrix", 4): {4: "MediaGX", 9: "5x86"},
    ("Cyrix", 5): {2: "6x86", 4: "MediaGX"},
    ("Cyrix", 6): {0: "6x86MX"},
    ("IDT", 5): {4: "WinChip C6", 8: "WinChip 2", 9: "WinChip 3"},
    ("UMC", 4): {1: "U5D", 2: "U5S"},
    ("NexGen", 5): {0: "Nx586"},
    ("Rise", 5): {0: "mP6", 2: "mP6"},
}

# A family as the program says it, as the CPU box would write it.
_CPU_FAMILIES = {"PENTIUM": "Pentium"}


def _chip(chip: str, maker: str, signature: str) -> str:
    """Which chip it is: from CPUID's family and model where the table knows them,
    otherwise the family the survey program said."""
    sig = signature.strip()
    if len(sig) == 4 and all(c in "0123456789ABCDEFabcdef" for c in sig):
        value = int(sig, 16)
        family, model = (value >> 8) & 0xF, (value >> 4) & 0xF
        named = _CPU_MODELS.get((maker, family), {}).get(model)
        if named:
            return named
    return _CPU_FAMILIES.get(chip.upper(), chip)


def cpu_line(keys: Mapping[str, str]) -> str:
    """The processor the way the CPU box asks for it: maker, model and speed, as
    `Intel 486DX2-66`. A chip that answers CPUID is named by what it answers; one too
    old to say who made it is written without a maker, and the speed is the one
    measured."""
    chip = keys.get("CPU", "").strip()
    if not chip:
        return ""
    vendor = keys.get("CPUVENDOR", "").strip()
    maker = _CPU_MAKERS.get(vendor.replace(" ", "").upper(), "")
    if not maker and vendor and vendor.isalpha() and len(vendor) <= 12:
        maker = vendor
    khz = _int(keys.get("CPUKHZ"))
    line = f"{maker} {_chip(chip, maker, keys.get('CPUSIG', ''))}".strip()
    return f"{line}-{_mhz(khz)}" if khz else line


def memory_kb(keys: Mapping[str, str]) -> int | None:
    """The memory the BIOS counts. Above 1 MiB it is rounded up to whole MiB, because
    an AT's BIOS leaves out the 384 KiB under its ROMs."""
    base, extended = _int(keys.get("RAMKB")), _int(keys.get("EXTKB"))
    if base is None and extended is None:
        return None
    total = (base or 0) + (extended or 0)
    if extended:
        total = -(-total // 1024) * 1024
    return total or None


# A floppy drive as a BIOS reports it, as the drives table holds it.
_FLOPPIES = {
    "160K": ('5.25"', "160K"),
    "180K": ('5.25"', "180K"),
    "320K": ('5.25"', "320K"),
    "360K": ('5.25"', "360K"),
    "1.2M": ('5.25"', "1.2MB"),
    "720K": ('3.5"', "720K"),
    "1.44M": ('3.5"', "1.44MB"),
    "2.88M": ('3.5"', "2.88MB"),
}


def _drive(kind: str, form: str = "", size: str = "", model: str = "") -> drivedb.Drive:
    return drivedb.Drive(
        count=1,
        kind=kind,
        form_factor=form,
        size=size,
        media="",
        speed="",
        model=model,
        colour="",
        yellowing="",
    )


def _numbers(keys: Mapping[str, str], prefix: str) -> list[int]:
    """The numbers a report gives things of one kind: DISK1, DISK2, PCI3..."""
    pattern = re.compile(rf"^{prefix}(\d+)(?:_|$)")
    return sorted({int(m.group(1)) for k in keys if (m := pattern.match(k))})


def drive_rows(keys: Mapping[str, str]) -> list[drivedb.Drive]:
    """The drives a machine keeps as rows on its own record: floppy drives as the
    BIOS has them, CD-ROM drives and CompactFlash cards."""
    rows = []
    for n in _numbers(keys, "FLOPPY"):
        said_as = keys[f"FLOPPY{n}"].strip().upper().replace("MB", "M").replace("KB", "K")
        if said_as:
            form, size = _FLOPPIES.get(said_as, ("", keys[f"FLOPPY{n}"].strip()))
            rows.append(_drive("floppy", form, size))
    for n in _numbers(keys, "DISK"):
        kind = keys.get(f"DISK{n}_TYPE", "").strip().upper()
        model = keys.get(f"DISK{n}_MODEL", "").strip()
        if kind == "ATAPI":
            rows.append(_drive("optical", model=model))
        elif kind == "CFA":
            rows.append(_drive("CF", model=model))
    return rows


def _roms(keys: Mapping[str, str]) -> list[tuple[int, str, int, str]]:
    """Each ROM a report copied, as (n, segment, size, filename)."""
    out = []
    for n in _numbers(keys, "ROM"):
        bits = keys.get(f"ROM{n}", "").split()
        if len(bits) >= 3 and bits[1].isdigit():
            out.append((n, bits[0].upper(), int(bits[1]), bits[2]))
    return out


# The top of the first megabyte, where the system BIOS ends.
_TOP = 0x100000


def _is_bios(segment: str, size: int) -> bool:
    """The system BIOS: the ROM that runs to the top of the first megabyte. An XT's
    starts at F000; a later board's is bigger and starts lower, at E000 or E800, where
    the survey program copied it from. An option ROM never reaches the top."""
    try:
        start = int(segment, 16) * 16
    except ValueError:
        return False
    return start + size >= _TOP


def nic_pci(keys: Mapping[str, str]) -> tuple[int, str, str, str] | None:
    """The network card on the PCI bus that the survey ran through, as (n, vendor,
    device, class): the first one, when a packet driver ran a card at all. The survey
    program counts it as the network card rather than a card of its own (tinydiag's
    docs/survey.md), and so does the register."""
    if not mac(keys.get("NIC_MAC", "")):
        return None
    for n in _numbers(keys, "PCI"):
        vendor, device, cls = pciids.split(keys.get(f"PCI{n}", ""))
        if vendor and device and cls.startswith("02"):
            return n, vendor, device, cls
    return None


def _display(keys: Mapping[str, str]) -> tuple[str, str] | None:
    """The video card on the PCI bus, as (vendor, device): the first display device."""
    for n in _numbers(keys, "PCI"):
        vendor, device, cls = pciids.split(keys.get(f"PCI{n}", ""))
        if vendor and device and cls.startswith("03"):
            return vendor, device
    return None


def rom_texts(keys: Mapping[str, str], roms: Mapping[str, bytes]) -> dict[str, list[str]]:
    """The text in each ROM a report or a question names, by segment, from the copies
    that came with it. A ROM that did not come has no text."""
    by_name = {name.upper(): data for name, data in roms.items()}
    out: dict[str, list[str]] = {}
    for _n, segment, _size, filename in _roms(keys):
        data = by_name.get(filename.replace("\\", "/").rsplit("/", 1)[-1].upper(), b"")
        if data:
            out[segment] = romtext.strings(data)
    return out


def _boot_rom(keys: Mapping[str, str], texts: Mapping[str, list[str]]) -> str:
    """The segment of the network card's boot ROM, where the survey program could not
    tell and the ROM's own text can: in a machine whose card a packet driver ran, the
    one ROM, and only one, that says it starts a machine from the network (ADR-0044).
    netboot's ROM carries neither a PCI class nor a Plug and Play type to know it by."""
    if keys.get("NIC_ROM", "").strip() or not mac(keys.get("NIC_MAC", "")):
        return ""
    found = [
        segment
        for _n, segment, size, _filename in _roms(keys)
        if not _is_bios(segment, size) and romtext.boot_rom(texts.get(segment, []))
    ]
    return found[0] if len(found) == 1 else ""


# --- findings --------------------------------------------------------------------------


class Finding(TypedDict):
    """One thing a survey found, and the answer it was given.

    `thing` is the report's own name for it (DISK1, NIC, VIDEO, PCI3, ROM2, PORTS,
    CPU). A thing that can say which one it is has `id_kind` and `identifier` (a disk's
    serial number, a card's address); one that cannot has `signature`, what it says it
    is, and `nth`, which of the same in the machine it is. `fits` is which of the three
    answers it may have, and `ptype` the type of a part made of it."""

    thing: str
    kind: str
    name: str
    id_kind: str
    identifier: str
    signature: str
    nth: int
    fits: list[str]
    answer: str | None
    part: str | None
    bench: bool
    segment: str
    ptype: str


def _finding(
    thing: str,
    kind: str,
    name: str,
    fits: list[str],
    *,
    id_kind: str = "",
    identifier: str = "",
    signature: str = "",
    segment: str = "",
    ptype: str = "",
) -> Finding:
    answer = MACHINE if fits == [MACHINE] else None
    return Finding(
        thing=thing,
        kind=kind,
        name=name,
        id_kind=id_kind,
        identifier=identifier,
        signature=signature,
        nth=0,
        fits=fits,
        answer=answer,
        part=None,
        bench=False,
        segment=segment,
        ptype=ptype,
    )


ALL = [PART, MACHINE, OUT]
PART_OR_OUT = [PART, OUT]


def mac(value: str) -> str:
    """An Ethernet address in the one spelling the register keeps: six pairs of hex
    digits in capitals, between colons."""
    digits = re.sub(r"[^0-9A-Fa-f]", "", value or "")
    if len(digits) != 12:
        return ""
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2)).upper()


def findings(
    keys: Mapping[str, str], texts: Mapping[str, list[str]] | None = None
) -> list[Finding]:
    """Everything a report says the machine has, in the register's terms. `texts` is
    the text in its ROMs, by segment, where they came with it: a network boot ROM the
    survey program could not place is known by what it says."""
    out: list[Finding] = []
    roms = _roms(keys)

    def machine_thing(thing: str, name: str) -> None:
        out.append(_finding(thing, MACHINE, name, [MACHINE]))

    if cpu := cpu_line(keys):
        machine_thing("CPU", cpu)
    fpu = keys.get("FPU", "").strip()
    if fpu and fpu.upper() not in ("NONE", "NO", "0", "ABSENT"):
        machine_thing("FPU", fpu)
    if (kb := memory_kb(keys)) is not None:
        machine_thing("MEMORY", entry.fmt_kb(kb))
    if keys.get("OS", "").strip():
        machine_thing("OS", keys["OS"].strip())
    if keys.get("BIOSVENDOR", "").strip() or keys.get("BIOSDATE", "").strip():
        machine_thing(
            "BIOS", " ".join(filter(None, (keys.get("BIOSVENDOR"), keys.get("BIOSDATE"))))
        )
    if any(said(keys.get(k)) for k in ("SYSTEM_MAKER", "SYSTEM_MODEL", "SYSTEM_SERIAL")):
        machine_thing(
            "SYSTEM",
            " ".join(
                filter(None, (said(keys.get("SYSTEM_MAKER")), said(keys.get("SYSTEM_MODEL"))))
            ),
        )
    if any(said(keys.get(k)) for k in ("BOARD_MAKER", "BOARD_MODEL", "BOARD_SERIAL")):
        machine_thing(
            "BOARD",
            " ".join(filter(None, (said(keys.get("BOARD_MAKER")), said(keys.get("BOARD_MODEL"))))),
        )
    for n in _numbers(keys, "FLOPPY"):
        if keys.get(f"FLOPPY{n}", "").strip():
            machine_thing(f"FLOPPY{n}", keys[f"FLOPPY{n}"].strip())

    # The PCI bus: the chipset's bridges are the board's, and say which chipset it is.
    pci = []
    for n in _numbers(keys, "PCI"):
        vendor, device, cls = pciids.split(keys.get(f"PCI{n}", ""))
        if vendor and device:
            pci.append((n, vendor, device, cls))
    bridges = [(v, d) for _, v, d, c in pci if pciids.is_chipset(c)]
    chip_vendors = {v for v, _ in bridges}
    if bridges:
        names = [pciids.chipset(v, d) for v, d in bridges]
        machine_thing("CHIPSET", next((n for n in names if n), pciids.name(*bridges[0])))

    for n in _numbers(keys, "DISK"):
        model = keys.get(f"DISK{n}_MODEL", "").strip()
        serial = said(keys.get(f"DISK{n}_SERIAL"))
        kind = keys.get(f"DISK{n}_TYPE", "").strip().upper() or ("ATA" if serial else "BIOS")
        if kind in ("ATAPI", "CFA"):
            machine_thing(f"DISK{n}", model or kind)
        elif serial:
            out.append(
                _finding(
                    f"DISK{n}",
                    "disk",
                    model or "Hard disk",
                    PART_OR_OUT,
                    id_kind="disk",
                    identifier=serial,
                    ptype="storage",
                )
            )
        else:
            chs = keys.get(f"DISK{n}_CHS", "").strip()
            size = keys.get(f"DISK{n}_KB", "").strip()
            out.append(
                _finding(
                    f"DISK{n}",
                    "disk",
                    model or f"Hard disk {chs}".strip(),
                    PART_OR_OUT,
                    signature=f"disk:{chs}:{size}",
                    ptype="storage",
                )
            )

    nic_rom = keys.get("NIC_ROM", "").strip().upper() or _boot_rom(keys, texts or {})
    on_pci = nic_pci(keys)
    if address := mac(keys.get("NIC_MAC", "")):
        named = pciids.known(on_pci[1], on_pci[2]) if on_pci else False
        out.append(
            _finding(
                "NIC",
                "nic",
                (pciids.name(on_pci[1], on_pci[2]) if on_pci and named else "")
                or keys.get("NIC_DRIVER", "").strip()
                or "Network card",
                ALL,
                id_kind="mac",
                identifier=address,
                segment=nic_rom,
                ptype="network",
            )
        )

    video = keys.get("VIDEO", "").strip()
    display = next(((n, v, d) for n, v, d, c in pci if c.startswith("03")), None)
    if video:
        rom_seg = "C000" if any(seg == "C000" for _, seg, _, _ in roms) else ""
        name = pciids.name(display[1], display[2]) if display else video
        out.append(
            _finding(
                "VIDEO",
                "video",
                name,
                ALL,
                signature=f"video:{video}",
                segment=rom_seg,
                ptype="video",
            )
        )
    for n, vendor, device, cls in pci:
        if pciids.is_chipset(cls):
            continue
        if video and display is not None and n == display[0]:
            continue
        if on_pci is not None and n == on_pci[0]:
            continue
        # The disk and USB controllers built into the chipset are the chipset's too.
        if vendor in chip_vendors and cls[:2] in ("01", "0C"):
            continue
        ptype, _word = pciids.kind(cls)
        out.append(
            _finding(
                f"PCI{n}",
                "card",
                pciids.name(vendor, device),
                ALL,
                signature=f"pci:{vendor}:{device} {cls}",
                ptype=ptype,
            )
        )

    claimed = {f["segment"] for f in out if f["segment"]}
    for rom_n, segment, rom_size, _filename in roms:
        if _is_bios(segment, rom_size) or segment in claimed or (video and segment == "C000"):
            continue
        out.append(
            _finding(
                f"ROM{rom_n}",
                "card",
                f"Card with a ROM at {segment}",
                ALL,
                signature=f"rom:{segment}:{rom_size}",
                segment=segment,
                ptype="io",
            )
        )

    ports = sorted(
        keys[k].split()[0].upper()
        for k in keys
        if re.match(r"^(COM|LPT)\d+$", k) and keys[k].strip()
    )
    if ports:
        out.append(
            _finding(
                "PORTS",
                "ports",
                _ports_words(keys),
                ALL,
                signature="ports:" + ",".join(ports),
                ptype="io",
            )
        )

    # Which of the same in one machine each is: the survey cannot tell two alike apart,
    # so they are counted.
    counted: dict[str, int] = {}
    for f in out:
        if f["signature"]:
            f["nth"] = counted.get(f["signature"], 0)
            counted[f["signature"]] = f["nth"] + 1
    return out


def _ports(keys: Mapping[str, str]) -> tuple[int, int]:
    serial = sum(1 for k in keys if re.match(r"^COM\d+$", k) and keys[k].strip())
    parallel = sum(1 for k in keys if re.match(r"^LPT\d+$", k) and keys[k].strip())
    return serial, parallel


def _ports_words(keys: Mapping[str, str]) -> str:
    serial, parallel = _ports(keys)
    bits = []
    if serial:
        bits.append(f"{serial} serial")
    if parallel:
        bits.append(f"{parallel} parallel")
    return "Ports: " + ", ".join(bits)


def _ports_spec(keys: Mapping[str, str]) -> str:
    serial, parallel = _ports(keys)
    bits = []
    if serial:
        bits.append(f"{serial}x Serial")
    if parallel:
        bits.append(f"{parallel}x Parallel")
    return ", ".join(bits)


def name_of(keys: Mapping[str, str], f: Finding, texts: Mapping[str, list[str]]) -> str:
    """What the register can call a thing found, from what the thing says of itself
    and nothing else: a disk by its own model, a card on the PCI bus by its chip where
    the table knows both maker and chip, a card or a video card by its ROM's banner.
    "" for a thing it can only describe (a card with a ROM at C800, VGA, the ports, a
    disk the BIOS knows by its size), whose make and model the machine asks when it
    is made (ADR-0044)."""
    kind = f["kind"]
    if kind == "disk":
        return keys.get(f"{f['thing']}_MODEL", "").strip()
    if kind == "nic":
        on_pci = nic_pci(keys)
        if on_pci is not None and pciids.known(on_pci[1], on_pci[2]):
            return pciids.name(on_pci[1], on_pci[2])
        return ""
    if f["signature"].startswith("pci:"):
        vendor, device, _cls = pciids.split(f["signature"][4:])
        return pciids.name(vendor, device) if pciids.known(vendor, device) else ""
    if kind == "video":
        display = _display(keys)
        if display is not None and pciids.known(*display):
            return pciids.name(*display)
    if kind in ("video", "card") and f["segment"]:
        return romtext.card(texts.get(f["segment"], []))
    return ""


def _typed(keys: Mapping[str, str], thing: str) -> tuple[str, str]:
    """The make and model typed at the machine for a new thing nobody could name: what
    a person said, so what the record is called, and never how the thing is known the
    next time (ADR-0044)."""

    def said_at(key: str) -> str:
        return " ".join(keys.get(key, "").split())[:64]

    return said_at(f"{thing}_MAKER"), said_at(f"{thing}_MODEL")


def answer_in(keys: Mapping[str, str], f: Finding) -> tuple[str, str]:
    """The answer given at the machine for a finding, as (how, tag): `link` with the
    tag typed, `new`, `machine` or `out` -- or ("", "") for none, or one that does not
    fit it."""
    value = keys.get(f"{f['thing']}_ANSWER", "").strip().upper()
    if not value:
        return "", ""
    if value == "NEW" and PART in f["fits"]:
        return "new", ""
    if value == "MACHINE" and MACHINE in f["fits"]:
        return MACHINE, ""
    if value == "OUT" and OUT in f["fits"]:
        return OUT, ""
    tag = exact_tag(value.split()[0])
    if tag and PART in f["fits"]:
        return "link", tag
    return "", ""


# --- what the register already knows ------------------------------------------------------


def _part(db: Session, tag: str | None) -> Part | None:
    found = db.get(Thing, tag.upper()) if tag else None
    return found if isinstance(found, Part) and not found.disposed else None


def known_part(db: Session, f: Finding) -> Part | None:
    """The part a finding that can say which one it is turns out to be, by its serial
    number or its address, or by what it was answered as before."""
    if f["id_kind"] == "disk":
        found = (
            db.query(Part).filter(Part.serial == f["identifier"], Part.disposed.is_(False)).first()
        )
    elif f["id_kind"] == "mac":
        found = (
            db.query(Part)
            .filter(Part.ethernet_address == f["identifier"], Part.disposed.is_(False))
            .first()
        )
    else:
        return None
    if found is not None:
        return found
    row = seen_row(db, f["id_kind"], f["identifier"])
    if row is not None and row.answer == PART:
        return _part(db, row.asset_id)
    return None


def seen_row(db: Session, kind: str, value: str) -> SurveySeen | None:
    return db.query(SurveySeen).filter(SurveySeen.kind == kind, SurveySeen.value == value).first()


def _bench_kinds(db: Session, tags: Iterable[str]) -> dict[str, str]:
    wanted = list(tags)
    if not wanted:
        return {}
    return {
        loc.asset_id.upper(): loc.kind
        for loc in db.query(Location).filter(Location.asset_id.in_(wanted))
    }


def on_bench(db: Session, t: tree.Tree, tag: str) -> bool:
    """Whether a part is the bench's own equipment: kept on a bench, or in something
    that is, and not fitted in a machine. A machine standing on a bench keeps its own
    parts, because what is fitted in it is not kept anywhere."""
    chain = t.up(tag.upper())
    kinds = _bench_kinds(db, [up for up in chain if t.what(up) == tree.LOCATION])
    for up in chain:
        what = t.what(up)
        if what == tree.COMPUTER:
            return False
        if what == tree.LOCATION and kinds.get(up) == locations.BENCH:
            return True
    return False


def _board_of(db: Session, t: tree.Tree, machine: str) -> Part | None:
    """The motherboard fitted in a machine, if one is on record."""
    for child in t.children(machine):
        found = db.get(Thing, child)
        if isinstance(found, Part) and found.type == "motherboard":
            return found
    return None


def _subject(db: Session, tag: str) -> Computer | Part | None:
    found = db.get(Thing, tag.upper())
    if isinstance(found, Computer) and not found.disposed:
        return found
    if isinstance(found, Part) and found.type == "motherboard" and not found.disposed:
        return found
    return None


def pointed_at(
    db: Session, keys: Mapping[str, str], found: list[Finding], t: tree.Tree
) -> dict[str, str]:
    """{machine: what says so} for everything inside that names a machine: a disk or a
    card the register has fitted in one, an address recorded as part of one, and a
    serial number from the BIOS that matches a machine's or a fitted board's. Anything
    kept on a bench says nothing: it goes into every machine on the bench in turn."""
    out: dict[str, str] = {}
    for f in found:
        if not f["identifier"]:
            continue
        part = known_part(db, f)
        if part is not None:
            tag = part.asset_id.upper()
            if on_bench(db, t, tag):
                continue
            if (machine := t.machine(tag)) is not None:
                out.setdefault(machine, tag)
            continue
        row = seen_row(db, f["id_kind"], f["identifier"])
        if row is not None and row.answer == MACHINE and row.asset_id:
            out.setdefault(row.asset_id.upper(), f["identifier"])
    if serial := said(keys.get("SYSTEM_SERIAL")):
        for c in db.query(Computer).filter(Computer.serial == serial, Computer.disposed.is_(False)):
            out.setdefault(c.asset_id.upper(), serial)
    if serial := said(keys.get("BOARD_SERIAL")):
        boards = db.query(Part).filter(
            Part.serial == serial, Part.type == "motherboard", Part.disposed.is_(False)
        )
        for board in boards:
            tag = board.asset_id.upper()
            out.setdefault(t.machine(tag) or tag, serial)
    return out


class Identity(NamedTuple):
    """Which machine a survey is about, how that was found, and, when it cannot be
    sure, why."""

    machine: str | None
    how: str
    by: str
    reason: str


def identify(db: Session, keys: Mapping[str, str], found: list[Finding], t: tree.Tree) -> Identity:
    """The answer at the machine first, then what is inside it; and where those
    disagree, or point at two machines, or name something that is not a machine,
    nothing (MANUAL §23, "Which machine it is")."""
    pointed = pointed_at(db, keys, found, t)
    typed = keys.get("TAG", "").strip().upper()
    if typed == "NEW":
        if pointed:
            machine, by = next(iter(pointed.items()))
            return Identity(None, "", "", f"N was answered, and {by} says this is {machine}.")
        return Identity(NEW, NEW, "", "")
    if typed:
        tag = exact_tag(typed) or typed
        thing = db.get(Thing, tag)
        subject = _subject(db, tag) if thing is not None else None
        if thing is None or thing.what == tree.DELETED:
            return Identity(None, "", "", f"{typed} is not a tag the register has issued.")
        if subject is None:
            return Identity(
                None, "", "", f"{tag} is not a machine or a motherboard in the register."
            )
        machine = tag
        if isinstance(subject, Part):
            machine = t.machine(tag) or tag
        others = {m: by for m, by in pointed.items() if m != machine}
        if others:
            other, by = next(iter(others.items()))
            return Identity(None, "", "", f"{tag} was typed, and {by} says this is {other}.")
        return Identity(machine, TYPED, tag, "")
    if not pointed:
        return Identity(None, "", "", "Nothing was typed, and nothing inside it is known.")
    if len(pointed) > 1:
        return Identity(None, "", "", "What is inside it points at " + " and ".join(pointed) + ".")
    machine, by = next(iter(pointed.items()))
    return Identity(machine, RECOGNISED, by, "")


# --- taking a report --------------------------------------------------------------------------


@dataclass
class Filing:
    """What filing one survey did, for the receipt, the history line and the labels."""

    filled: list[str] = field(default_factory=list)
    differs: list[dict[str, str]] = field(default_factory=list)
    made: list[tuple[str, str]] = field(default_factory=list)


def _clock(keys: Mapping[str, str]) -> str:
    return " ".join(filter(None, (keys.get("DATE", "").strip(), keys.get("TIME", "").strip())))[:32]


def take(
    db: Session,
    agent: Agent,
    raw: bytes,
    roms: Mapping[str, bytes],
    taken: datetime | None,
) -> list[tuple[Survey, Filing]]:
    """A file of reports, as an agent sent it: each report a survey, filed as far as it
    can be, with what filing it did. Raises surveyreport.Unreadable for a file that is
    not a report. The caller commits, and then queues the labels (`labels_for`)."""
    reports = surveyreport.read(surveyreport.decode(raw))
    when = taken or _now()
    made: list[tuple[Survey, Filing]] = []
    for report in reports:
        keys = report.keys
        texts = rom_texts(keys, roms)
        s = Survey(
            agent=agent.name,
            taken=when,
            clock=_clock(keys),
            report=report.text,
            keys=json.dumps(keys),
            result=keys.get("RESULT", "").strip().upper()[:16],
            findings=json.dumps(findings(keys, texts)),
            filled="[]",
            differs="[]",
            missing="[]",
            roms="[]",
        )
        db.add(s)
        db.flush()
        _keep_rom_text(s, keys, roms)
        made.append((s, settle(db, s, roms, who=agent.name)))
    return made


def _keep_rom_text(s: Survey, keys: Mapping[str, str], roms: Mapping[str, bytes]) -> None:
    """The text in each ROM, kept with the survey whatever becomes of the ROM itself."""
    by_name = {name.upper(): data for name, data in roms.items()}
    kept = []
    for n, segment, size, filename in _roms(keys):
        data = by_name.get(filename.upper(), b"")
        kept.append(
            {
                "thing": f"ROM{n}",
                "segment": segment,
                "size": size,
                "filename": filename,
                "file": None,
                "text": romtext.strings(data) if data else [],
            }
        )
    s.roms = json.dumps(kept)


def keys_of(s: Survey) -> dict[str, str]:
    return cast(dict[str, str], json.loads(s.keys or "{}"))


def findings_of(s: Survey) -> list[Finding]:
    return cast(list[Finding], json.loads(s.findings or "[]"))


def roms_of(s: Survey) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], json.loads(s.roms or "[]"))


def settle(
    db: Session,
    s: Survey,
    roms: Mapping[str, bytes],
    who: str,
    machine: str | None = None,
    how: str = "",
    by: str = "",
) -> Filing:
    """File a survey: against `machine` when the caller has settled which it is (the
    page's File, a new computer's form), and otherwise against the machine the report
    and the register agree on, or nothing, in which case it waits."""
    keys = keys_of(s)
    found = findings_of(s)
    t = tree.load(db)
    done = Filing()
    if machine is None:
        who_is = identify(db, keys, found, t)
        machine, how, by = who_is.machine, who_is.how, who_is.by
        if machine is None:
            s.waiting, s.reason = FOR_MACHINE, who_is.reason[:255]
            _record_seen(db, s, found, None)
            return done
    if machine == NEW:
        made = Computer(asset_id=next_asset_id(db))
        db.add(made)
        db.flush()
        made_line = add_log(db, made.asset_id, "created by a survey", "created")
        # Dated with the survey, as the survey's own line is, so the history reads in the
        # order it happened: made, then surveyed.
        if made_line is not None and made_line.created_at is not None:
            made_line.created_at = min(made_line.created_at, s.taken)
        done.made.append(("computer", made.asset_id))
        machine = made.asset_id
        t = tree.load(db)
    s.machine, s.how, s.by, s.reason = machine, how, by[:128], ""
    _apply(db, s, keys, found, roms, who, t, done)
    return done


def _apply(
    db: Session,
    s: Survey,
    keys: Mapping[str, str],
    found: list[Finding],
    roms: Mapping[str, bytes],
    who: str,
    t: tree.Tree,
    done: Filing,
) -> None:
    machine = s.machine or ""
    subject = _subject(db, machine)
    if subject is None:
        s.waiting, s.reason = FOR_MACHINE, f"{machine} is not a machine or a motherboard."
        return
    board = subject if isinstance(subject, Part) else _board_of(db, t, machine)
    texts = _rom_texts(s)
    for f in found:
        if f["kind"] == MACHINE:
            continue
        if f["identifier"]:
            _answer_identified(db, keys, f, machine, who, t, done, texts)
        else:
            _answer_remembered(db, keys, f, machine, who, t, done, texts)
        if f["kind"] == "nic" and f["bench"] and f["part"]:
            s.bench_card = f["part"]
    _fill(db, s, keys, found, subject, board, texts, done)
    _condition(keys, subject, done)
    _keep_roms(db, s, keys, found, roms, subject, board, texts)
    s.missing = json.dumps(_missing(db, t, machine, found))
    s.filled = json.dumps(done.filled)
    s.differs = json.dumps(done.differs)
    s.findings = json.dumps(found)
    s.waiting = FOR_ANSWER if any(f["answer"] is None for f in found) else None
    _history(db, s, keys, done)
    _record_seen(db, s, found, machine)


def _place(db: Session, f: Finding, part: Part, machine: str, who: str, t: tree.Tree) -> None:
    """A part the register has, found in this machine: left where it is when it is kept
    on a bench, confirmed when it is fitted here, moved in from a shelf or from nowhere
    -- and never taken out of another machine."""
    tag = part.asset_id.upper()
    if on_bench(db, t, tag):
        f["answer"], f["part"], f["bench"] = PART, tag, True
        return
    here = t.machine(tag) or (t.holder(tag) if t.what(t.holder(tag)) == tree.PART else None)
    if here == machine or t.holder(tag) == machine:
        f["answer"], f["part"] = PART, tag
        return
    if t.machine(tag) is not None:
        f["answer"], f["part"] = None, None
        return
    try:
        tree.put(db, part, machine, tree.SURVEY, who, t)
    except tree.Refused:
        f["answer"], f["part"] = None, None
        return
    f["answer"], f["part"] = PART, tag


def _identify_part(part: Part, f: Finding) -> None:
    """Give a part the serial number or the address a survey read off it, where its
    record has none."""
    if f["id_kind"] == "disk" and not part.serial:
        part.serial = f["identifier"][:64]
    if f["id_kind"] == "mac" and not part.ethernet_address:
        part.ethernet_address = f["identifier"]


def _answer_identified(
    db: Session,
    keys: Mapping[str, str],
    f: Finding,
    machine: str,
    who: str,
    t: tree.Tree,
    done: Filing,
    texts: Mapping[str, list[str]],
) -> None:
    part = known_part(db, f)
    if part is not None:
        _identify_part(part, f)
        _place(db, f, part, machine, who, t)
        if f["answer"] == PART and not f["bench"] and f["kind"] == "disk":
            _fill_disk(db, part, keys, f)
        return
    row = seen_row(db, f["id_kind"], f["identifier"])
    if row is not None and row.answer in (MACHINE, OUT) and row.answer in f["fits"]:
        f["answer"] = row.answer
        return
    how, tag = answer_in(keys, f)
    if how == "link" and (linked := _part(db, tag)) is not None:
        _identify_part(linked, f)
        _place(db, f, linked, machine, who, t)
    elif how == "new":
        made = _new_part(db, keys, f, machine, who, t, done, texts=texts)
        f["answer"], f["part"] = PART, made.asset_id
    elif how in (MACHINE, OUT):
        f["answer"] = how


def _answer_remembered(
    db: Session,
    keys: Mapping[str, str],
    f: Finding,
    machine: str,
    who: str,
    t: tree.Tree,
    done: Filing,
    texts: Mapping[str, list[str]],
) -> None:
    row = (
        db.query(SurveyAnswer)
        .filter(
            SurveyAnswer.machine == machine,
            SurveyAnswer.thing == f["signature"][:191],
            SurveyAnswer.nth == f["nth"],
        )
        .first()
    )
    if row is not None:
        if row.answer != PART:
            f["answer"] = row.answer
            return
        part = _part(db, row.part)
        if part is not None:
            tag = part.asset_id.upper()
            if on_bench(db, t, tag):
                f["answer"], f["part"], f["bench"] = PART, tag, True
                return
            if t.machine(tag) == machine or t.holder(tag) == machine:
                f["answer"], f["part"] = PART, tag
                return
        # The part it named has been taken out since: the answer no longer holds, and
        # is asked again.
        db.delete(row)
        db.flush()
    how, tag = answer_in(keys, f)
    if how == "link" and (linked := _part(db, tag)) is not None:
        _place(db, f, linked, machine, who, t)
    elif how == "new":
        made = _new_part(db, keys, f, machine, who, t, done, texts=texts)
        f["answer"], f["part"] = PART, made.asset_id
    elif how in (MACHINE, OUT):
        f["answer"] = how
    if f["answer"] is not None:
        remember(db, machine, f)


def remember(db: Session, machine: str, f: Finding) -> None:
    """Keep the answer for a thing with no serial number, for the machine it is in."""
    if not f["signature"] or f["answer"] is None:
        return
    row = (
        db.query(SurveyAnswer)
        .filter(
            SurveyAnswer.machine == machine,
            SurveyAnswer.thing == f["signature"][:191],
            SurveyAnswer.nth == f["nth"],
        )
        .first()
    )
    if row is None:
        row = SurveyAnswer(machine=machine, thing=f["signature"][:191], nth=f["nth"], answer="")
        db.add(row)
    row.answer, row.part = f["answer"], f["part"]
    db.flush()


def _new_part(
    db: Session,
    keys: Mapping[str, str],
    f: Finding,
    into: str,
    who: str,
    t: tree.Tree,
    done: Filing,
    how: str = tree.SURVEY,
    texts: Mapping[str, list[str]] | None = None,
) -> Part:
    """A new part for a finding, fitted in the machine (or put where `into` is), named
    as it names itself: a disk by what IDENTIFY says, a card by its ROM or by its chip
    on the PCI bus, a network card by its chip or by the driver it was run with. What
    was typed at the machine for one that names nothing is its name instead."""
    part = Part(asset_id=next_asset_id(db), type=f["ptype"] or "other")
    if f["kind"] == "disk":
        part.model = f["name"]
        part.serial = f["identifier"][:64]
        part.specs = _disk_specs(keys, f)
    elif f["kind"] == "nic":
        on_pci = nic_pci(keys)
        if on_pci is not None and pciids.known(on_pci[1], on_pci[2]):
            part.manufacturer = pciids.maker(on_pci[1])
            part.model = pciids.model(on_pci[1], on_pci[2])
        else:
            part.model = f["name"]
        part.ethernet_address = f["identifier"]
    elif f["kind"] == "ports":
        part.model = "I/O card"
        part.specs = f"Ports: {_ports_spec(keys)}"
    elif f["signature"].startswith("pci:"):
        vendor, device, _cls = pciids.split(f["signature"][4:])
        part.manufacturer = pciids.maker(vendor)
        part.model = pciids.model(vendor, device)
    else:
        own = (texts or {}).get(f["segment"], []) if f["segment"] else []
        part.model = romtext.card(own) or f["name"]
    maker, model = _typed(keys, f["thing"])
    if maker:
        part.manufacturer = maker
    if model:
        part.model = model
    db.add(part)
    db.flush()
    specdb.write(db, part)
    add_log(db, part.asset_id, "created by a survey", "created")
    # A machine that has been disposed of takes nothing in. The part is still made, and
    # is kept where any new part is kept, rather than the survey failing over it.
    with contextlib.suppress(tree.Refused):
        tree.put(db, part, into, how, who, t)
    done.made.append(("part", part.asset_id))
    return part


def _disk_specs(keys: Mapping[str, str], f: Finding) -> str:
    n = f["thing"].removeprefix("DISK")
    pairs = [("Kind", "Hard disk")]
    if keys.get(f"DISK{n}_TYPE", "").strip().upper() in ("ATA", "") and f["identifier"]:
        pairs.append(("Interface", "IDE"))
    if (kb := _int(keys.get(f"DISK{n}_KB"))) is not None:
        pairs.append(("Capacity", entry.fmt_kb(kb)))
    if chs := keys.get(f"DISK{n}_CHS", "").strip():
        pairs.append(("CHS", chs))
    return entry.build_specs(pairs)


def _fill_disk(db: Session, part: Part, keys: Mapping[str, str], f: Finding) -> None:
    """What a disk's record is missing, from what it said about itself: its capacity
    and its geometry."""
    have = {k.lower() for k, _ in entry.parse_specs(part.specs or "")}
    specs = part.specs or ""
    for k, v in entry.parse_specs(_disk_specs(keys, f)):
        if k.lower() not in have:
            specs = entry.merge_spec(specs, k, v)
    if specs != (part.specs or ""):
        part.specs = specs
        specdb.write(db, part)


def _rom_texts(s: Survey) -> dict[str, list[str]]:
    """The text in each ROM, by segment."""
    out: dict[str, list[str]] = {}
    for rom in roms_of(s):
        text = rom.get("text")
        if isinstance(text, list):
            out[str(rom.get("segment", ""))] = [str(x) for x in text]
    return out


# --- filling in what is empty --------------------------------------------------------------

_FILLED_WORDS = {
    "cpu": "CPU",
    "installed_ram": "memory",
    "os": "operating system",
    "manufacturer": "maker",
    "model": "model",
    "serial": "serial number",
    "drives": "drives",
    "BIOS": "BIOS",
    "FPU": "FPU",
    "Chipset": "chipset",
}


def _fill_field(obj: Computer | Part, name: str, value: str, done: Filing, word: str = "") -> None:
    """Fill one field when it is empty, and otherwise note what was read if it differs."""
    if not value:
        return
    recorded = getattr(obj, name) or ""
    if not recorded:
        setattr(obj, name, value)
        done.filled.append(word or _FILLED_WORDS.get(name, name))
    elif str(recorded).strip().lower() != value.strip().lower():
        done.differs.append({"field": name, "recorded": str(recorded), "found": value})


def _bios_line(keys: Mapping[str, str], texts: Mapping[str, list[str]]) -> str:
    """The BIOS as the motherboard's BIOS line says it: maker, version and date, the
    date as the BIOS writes it, month first."""
    bios_text = [
        line
        for _, segment, size, _ in _roms(keys)
        if _is_bios(segment, size)
        for line in texts.get(segment, [])
    ]
    maker, version = romtext.bios(bios_text)
    maker = maker or keys.get("BIOSVENDOR", "").strip()
    date = keys.get("BIOSDATE", "").strip()
    return " ".join(filter(None, (maker, version, date)))


def _spec_fill(db: Session, board: Part, pairs: list[tuple[str, str]], done: Filing) -> None:
    """Lines of a board's specification, each written where the board has none."""
    have = {k.lower(): v for k, v in entry.parse_specs(board.specs or "")}
    specs = board.specs or ""
    for key, value in pairs:
        if not value:
            continue
        if key.lower() in have and have[key.lower()]:
            if have[key.lower()].strip().lower() != value.strip().lower() and key in (
                "BIOS",
                "Chipset",
            ):
                done.differs.append({"field": key, "recorded": have[key.lower()], "found": value})
            continue
        specs = entry.merge_spec(specs, key, value)
        have[key.lower()] = value
        done.filled.append(_FILLED_WORDS.get(key, key))
    if specs != (board.specs or ""):
        board.specs = specs
        specdb.write(db, board)


def _socket(key: str, role: str, wanted: str) -> str:
    """The catalogue's own spelling of a chip for a socket, where one of its variants
    is the chip read off the machine (`BIOS 10/27/82`, `Intel 8087`)."""
    found = machines.chip(key, role)
    for variant in found["variants"] if found else []:
        if wanted and wanted.lower() in variant.lower():
            return variant
    return ""


def _fill(
    db: Session,
    s: Survey,
    keys: Mapping[str, str],
    found: list[Finding],
    subject: Computer | Part,
    board: Part | None,
    texts: Mapping[str, list[str]],
    done: Filing,
) -> None:
    on_board: list[tuple[str, str]] = []
    bios_line = _bios_line(keys, texts)
    fpu = next((f["name"] for f in found if f["thing"] == "FPU"), "")
    bios_in_socket = fpu_in_socket = False
    if isinstance(subject, Computer):
        c = subject
        _fill_field(c, "cpu", cpu_line(keys), done)
        if (kb := memory_kb(keys)) is not None:
            mods, ram_chips = ramdb.read(db, c)
            if not mods and not ram_chips and not c.installed_ram_note and not c.installed_ram_kb:
                ramdb.write(db, c, total_kb=kb)
                done.filled.append("memory")
            elif c.installed_ram_kb != kb:
                done.differs.append(
                    {
                        "field": "installed_ram",
                        "recorded": c.installed_ram or "",
                        "found": entry.fmt_kb(kb),
                    }
                )
        _fill_field(c, "os", keys.get("OS", "").strip(), done)
        _fill_field(c, "manufacturer", said(keys.get("SYSTEM_MAKER")), done)
        _fill_field(c, "model", said(keys.get("SYSTEM_MODEL")), done)
        _fill_field(c, "serial", said(keys.get("SYSTEM_SERIAL")), done)
        rows = drive_rows(keys)
        if rows and not drivedb.read(db, c):
            drivedb.write(db, c, rows)
            done.filled.append("drives")
        identity = machinedb.read(db, c)
        model_key = identity["model_key"]
        if model_key:
            roles = machines.roles(model_key)
            chips: dict[str, str] = {}
            date = keys.get("BIOSDATE", "").strip()
            if "bios" in roles and date:
                bios_in_socket = True
                if not identity["chips"].get("bios"):
                    chips["bios"] = _socket(model_key, "bios", date) or f"BIOS {date}"
            if "fpu" in roles and fpu:
                fpu_in_socket = True
                if not identity["chips"].get("fpu"):
                    chips["fpu"] = _socket(model_key, "fpu", fpu) or fpu
            if chips:
                machinedb.write(db, c, chips=chips)
                done.filled += ["BIOS" if role == "bios" else "FPU" for role in chips]
    if board is not None:
        if not bios_in_socket:
            on_board.append(("BIOS", bios_line))
        if fpu and not fpu_in_socket:
            on_board.append(("FPU", fpu))
        chipset = next((f["name"] for f in found if f["thing"] == "CHIPSET"), "")
        on_board.append(("Chipset", chipset))
        for f in found:
            if f["answer"] != MACHINE or f["kind"] == MACHINE:
                continue
            if f["kind"] == "video":
                on_board.append(("Onboard video", _video_name(f, texts)))
            elif f["kind"] == "ports":
                on_board.append(("Ports", _ports_spec(keys)))
            elif f["kind"] in ("card", "nic"):
                word = "network" if f["kind"] == "nic" else _built_in_word(f)
                on_board.append((f"Onboard {word}", _card_name(f, texts)))
        _spec_fill(db, board, on_board, done)
        if serial := said(keys.get("BOARD_SERIAL")):
            _fill_field(board, "serial", serial, done, "board's serial number")


def _built_in_word(f: Finding) -> str:
    if f["signature"].startswith("pci:"):
        _vendor, _device, cls = pciids.split(f["signature"][4:])
        return pciids.kind(cls)[1]
    return "card"


def _video_name(f: Finding, texts: Mapping[str, list[str]]) -> str:
    named = romtext.card(texts.get(f["segment"], [])) if f["segment"] else ""
    return named or f["name"]


def _card_name(f: Finding, texts: Mapping[str, list[str]]) -> str:
    named = romtext.card(texts.get(f["segment"], [])) if f["segment"] else ""
    if f["kind"] == "nic":
        return named or f["name"]
    return named or f["name"]


# --- Working, from the tests ---------------------------------------------------------------


def full_pass(keys: Mapping[str, str]) -> bool:
    """Every test passed, apart from those that do not apply to the machine. A test
    that was skipped counts against it, because it has not been run."""
    if keys.get("RESULT", "").strip().upper() != "PASS":
        return False
    results = [v.strip().upper() for k, v in keys.items() if k.startswith("TEST_")]
    return any(r == "PASS" for r in results) and all(r in ("PASS", "NA") for r in results)


def _condition(keys: Mapping[str, str], subject: Computer | Part, done: Filing) -> None:
    if not full_pass(keys):
        return
    recorded = subject.condition or ""
    if recorded in ("", "Untested"):
        subject.condition = "Working"
        done.filled.append("condition")
    elif recorded == "Faulty":
        done.differs.append(
            {"field": "condition", "recorded": recorded, "found": "every test passed"}
        )


# --- ROMs ------------------------------------------------------------------------------------


def _owner(f: Finding | None, subject: Computer | Part, board: Part | None) -> str | None:
    """What a ROM's file is linked to: the card it is on, or the machine (or its board)
    when the card is part of it. None where it is not decided yet, or left out."""
    if f is None or f["answer"] is None or f["answer"] == OUT:
        return None
    if f["answer"] == PART:
        return f["part"]
    return (board or subject).asset_id


def _keep_roms(
    db: Session,
    s: Survey,
    keys: Mapping[str, str],
    found: list[Finding],
    roms: Mapping[str, bytes],
    subject: Computer | Part,
    board: Part | None,
    texts: Mapping[str, list[str]],
) -> None:
    by_name = {name.upper(): data for name, data in roms.items()}
    by_segment = {f["segment"]: f for f in found if f["segment"]}
    kept = roms_of(s)
    for rom in kept:
        segment = str(rom.get("segment", ""))
        data = by_name.get(str(rom.get("filename", "")).upper(), b"")
        if not data:
            continue
        size = rom.get("size")
        if _is_bios(segment, size if isinstance(size, int) else len(data)):
            owner: str | None = (board or subject).asset_id
            note = "BIOS, " + (_bios_line(keys, texts) or "as read by a survey")
        else:
            f = by_segment.get(segment)
            if f is not None and f["answer"] == OUT:
                continue
            owner = _owner(f, subject, board)
            what = romtext.card(texts.get(segment, []))
            note = f"option ROM at {segment}" + (f", {what}" if what else "")
        stored = filesdb.keep(db, str(rom.get("filename", "ROM.BIN")), data, note)
        if stored is None:
            continue
        rom["file"] = stored.id
        if owner:
            filesdb.link(db, stored.id, owner)
    s.roms = json.dumps(kept)


# --- what was expected and not found ------------------------------------------------------------


def _missing(db: Session, t: tree.Tree, machine: str, found: list[Finding]) -> list[str]:
    """What the register has in the machine that the survey would have seen and did
    not: a hard disk with a serial number, when the survey read the disks; a part a
    remembered answer named, when the survey did not find that thing again."""
    out: list[str] = []
    serials = {f["identifier"] for f in found if f["id_kind"] == "disk"}
    if any(f["kind"] == "disk" for f in found):
        for tag in t.within(machine):
            part = db.get(Thing, tag)
            if (
                isinstance(part, Part)
                and part.type == "storage"
                and part.serial
                and part.serial not in serials
                and not on_bench(db, t, tag)
            ):
                out.append(tag)
    signatures = {(f["signature"][:191], f["nth"]) for f in found if f["signature"]}
    for row in db.query(SurveyAnswer).filter(
        SurveyAnswer.machine == machine, SurveyAnswer.answer == PART
    ):
        if (
            (row.thing, row.nth) not in signatures
            and row.part
            and row.part not in out
            and t.machine(row.part.upper()) == machine
        ):
            out.append(row.part)
    return out


# --- the history line ----------------------------------------------------------------------------

# What a test is called in a history line, where its key is not a word a reader knows.
_TEST_WORDS = {
    "FDC": "floppy",
    "KBD": "keyboard",
    "COM": "serial",
    "LPT": "parallel",
    "RTC": "clock",
    "VRAM": "video memory",
    "RAMSYS": "memory in use",
    "OPTROM": "option ROMs",
    "TICK": "timer tick",
}


def _hours(elapsed: str) -> str:
    bits = [int(b) for b in elapsed.split(":") if b.isdigit()]
    if len(bits) == 3:
        h, m, _ = bits
    elif len(bits) == 2:
        h, m = 0, bits[0]
    else:
        return ""
    if h:
        return f"{h} hour{'s' if h != 1 else ''}"
    return f"{m} minute{'s' if m != 1 else ''}"


def _joined(words: list[str]) -> str:
    unique = list(dict.fromkeys(words))
    if len(unique) <= 1:
        return "".join(unique)
    return ", ".join(unique[:-1]) + " and " + unique[-1]


def tests_line(keys: Mapping[str, str]) -> str:
    """How the tests went, as the start of the history line."""
    result = keys.get("RESULT", "").strip().upper()
    tests = {k[5:]: v.strip().upper() for k, v in keys.items() if k.startswith("TEST_")}
    failed = [_TEST_WORDS.get(name, name) for name, v in tests.items() if v == "FAIL"]
    total = _int(keys.get("TESTS")) or len(tests)
    if result == "ABORTED":
        return "the tests were stopped before they finished"
    if failed or result == "FAIL":
        n = _int(keys.get("FAILED")) or len(failed) or 1
        named = f" ({', '.join(failed)})" if failed else ""
        return f"{n} of {total} test{'s' if total != 1 else ''} failed{named}"
    if result == "PASS":
        # Every test that applies, that is: one that was skipped or never run has not
        # passed, and the line says so rather than calling the run clean.
        passed = sum(1 for v in tests.values() if v == "PASS")
        skipped = sum(1 for v in tests.values() if v == "SKIP")
        not_run = sum(1 for v in tests.values() if v == "NOTRUN")
        if skipped or not_run:
            bits = [f"{passed} of {total} test{'s' if total != 1 else ''} passed"]
            bits += [f"{skipped} skipped"] if skipped else []
            bits += [f"{not_run} not run"] if not_run else []
            line = ", ".join(bits)
        else:
            line = "every test passed"
        if keys.get("MODE", "").strip().upper() == "SOAK":
            passes = _int(keys.get("PASSES"))
            how_long = _hours(keys.get("ELAPSED", ""))
            if passes and how_long:
                line += f", {passes} passes over {how_long}"
        return line
    return "no tests were run"


def _history(db: Session, s: Survey, keys: Mapping[str, str], done: Filing) -> None:
    """One line on the machine's history, marked survey and dated when it was taken.
    It is public, as every history line is, and says nothing that is not: no serial
    number, no address, nowhere anything is kept."""
    if s.log_id is not None or not s.machine:
        return
    words = [w for w in done.filled if w != "condition"]
    line = f"Surveyed: {tests_line(keys)}."
    if words:
        line += f" Filled in {_joined(words)}."
    if "condition" in done.filled:
        line += " Marked Working."
    row = add_log(db, s.machine, line, SURVEY_ENTRY)
    if row is not None:
        row.created_at = s.taken
        db.flush()
        s.log_id = row.id


# --- what surveys have seen ---------------------------------------------------------------------


def _record_seen(db: Session, s: Survey, found: list[Finding], machine: str | None) -> None:
    """Every serial number and address the survey read, recorded whatever its answer,
    with the machine it was in and when (MANUAL §23, "Serial numbers and addresses")."""
    keys = keys_of(s)
    seen: list[tuple[str, str, str | None, str | None]] = []
    for f in found:
        if f["identifier"]:
            owner = (
                f["part"] if f["answer"] == PART else machine if f["answer"] == MACHINE else None
            )
            seen.append((f["id_kind"], f["identifier"], f["answer"], owner))
    if serial := said(keys.get("SYSTEM_SERIAL")):
        seen.append(("system", serial, MACHINE if machine else None, machine))
    if serial := said(keys.get("BOARD_SERIAL")):
        seen.append(("board", serial, MACHINE if machine else None, machine))
    for kind, value, answer, owner in seen:
        row = seen_row(db, kind, value[:128])
        if row is None:
            row = SurveySeen(kind=kind, value=value[:128], first_seen=s.taken, last_seen=s.taken)
            db.add(row)
        if answer is not None:
            row.answer, row.asset_id = answer, owner
        if s.taken >= row.last_seen or row.last_survey is None:
            row.last_seen, row.last_in, row.last_survey = s.taken, machine, s.id
    db.flush()


# --- the machine's question, and the register's answers -----------------------------------------


def _shown(text: str) -> str:
    """A name as the machine shows it: printable ASCII, no `=` to end the key early,
    and short enough for the line it is shown on."""
    plain = "".join(c if " " <= c <= "~" else "?" for c in text.replace("=", "-"))
    return " ".join(plain.split())[:60]


def answer_question(db: Session, text: str, roms: Mapping[str, bytes] | None = None) -> str:
    """The answer to a machine's question before its tests (MANUAL §23, "At the
    machine"): which machine this is, when the register can tell, the answer it
    already has for each thing found, what it can call each thing, and which ROM is
    the network card's where the ROM says so. `roms` are the copies the question
    names, as the agent sends them; an agent from before they came with it sends none.
    Asking writes nothing: the ROMs are read for their text and kept nowhere."""
    keys = surveyreport.question(text)
    texts = rom_texts(keys, roms or {})
    found = findings(keys, texts)
    t = tree.load(db)
    lines = ["[RHDB]"]
    machine: str | None = None
    typed = keys.get("TAG", "").strip().upper()
    if typed and typed != "NEW":
        tag = exact_tag(typed) or typed
        if (subject := _subject(db, tag)) is not None:
            machine = (t.machine(tag) or tag) if isinstance(subject, Part) else tag
    if machine is None and not typed:
        pointed = pointed_at(db, keys, found, t)
        if len(pointed) == 1:
            machine = next(iter(pointed))
    if machine is not None:
        lines.append(f"TAG={machine}")
    for f in found:
        if f["kind"] == MACHINE:
            continue
        value = _held(db, f, machine, t)
        if value:
            lines.append(f"{f['thing']}_ANSWER={value}")
    # What each thing is called, for the machine to show it by, and so that it asks the
    # make and model only of what nobody can name (ADR-0044). The machine itself is
    # named by its BIOS only when the BIOS says both who made it and what it is.
    for f in found:
        if f["kind"] != MACHINE and (named := name_of(keys, f, texts)):
            lines.append(f"{f['thing']}_NAME={_shown(named)}")
    maker, model = said(keys.get("SYSTEM_MAKER")), said(keys.get("SYSTEM_MODEL"))
    if maker and model:
        lines.append(f"SYSTEM_NAME={_shown(f'{maker} {model}')}")
    nic = next((f for f in found if f["kind"] == "nic"), None)
    if nic is not None and nic["segment"] and not keys.get("NIC_ROM", "").strip():
        lines.append(f"NIC_ROM={nic['segment']}")
    return "\r\n".join(lines) + "\r\n"


def _held(db: Session, f: Finding, machine: str | None, t: tree.Tree) -> str:
    if f["identifier"]:
        part = known_part(db, f)
        if part is not None:
            tag = part.asset_id.upper()
            return f"{tag} BENCH" if on_bench(db, t, tag) else tag
        row = seen_row(db, f["id_kind"], f["identifier"])
        if row is not None and row.answer in (MACHINE, OUT):
            return row.answer.upper()
        return ""
    if machine is None:
        return ""
    kept = (
        db.query(SurveyAnswer)
        .filter(
            SurveyAnswer.machine == machine,
            SurveyAnswer.thing == f["signature"][:191],
            SurveyAnswer.nth == f["nth"],
        )
        .first()
    )
    if kept is None:
        return ""
    if kept.answer == PART:
        if kept.part and (part := _part(db, kept.part)) is not None:
            tag = part.asset_id.upper()
            if on_bench(db, t, tag):
                return f"{tag} BENCH"
            if t.machine(tag) == machine or t.holder(tag) == machine:
                return tag
        return ""
    return kept.answer.upper()


def receipt(db: Session, made: list[Survey]) -> str:
    """The register's answer, for the agent to leave beside the report and the survey
    program to show as it is: short lines a DOS screen can show."""
    lines: list[str] = []
    for s in made:
        keys = keys_of(s)
        if s.machine:
            subject = db.get(Thing, s.machine)
            name = (
                entry.display_name(to_dict(subject)) if isinstance(subject, Computer | Part) else ""
            )
            # A machine with nothing to be called but its tag is named by the tag once.
            if name.strip().upper() == s.machine.upper():
                name = ""
            lines.append(f"{s.machine} {name}".strip())
        else:
            lines.append("Not filed yet: which machine this is waits on the Surveys page.")
        # Only the first letter: capitalize() would also lower the tests' own names.
        said_of_tests = tests_line(keys)
        lines.append(said_of_tests[:1].upper() + said_of_tests[1:] + ".")
        filled = [w for w in cast(list[str], json.loads(s.filled or "[]")) if w != "condition"]
        if filled:
            lines.append(f"Filled in {_joined(filled)}.")
        waiting = sum(1 for f in findings_of(s) if f["answer"] is None)
        if s.machine and waiting:
            are = "is" if waiting == 1 else "are"
            lines.append(
                f"{waiting} thing{'s' if waiting != 1 else ''} {are} waiting for you on the Surveys page."
            )
    return (
        "\r\n".join(line.encode("ascii", "replace").decode("ascii")[:79] for line in lines) + "\r\n"
    )


def labels_for(db: Session, agent: Agent, made: Iterable[tuple[str, str]]) -> None:
    """Print the label of every tag a survey made on the agent's printer, if it names
    one the register knows. Called after the survey is saved, because putting a job on
    the queue saves it."""
    printer = printing.agents().get(agent.printer) if agent.printer else None
    if printer is None:
        return
    for kind, tag in made:
        printing.add(db, printer, kind, tag)


# --- the survey's page: filing, answering, deleting ------------------------------------------------


class Refused(ValueError):
    """What was asked of a survey cannot be done, and why, in words for the page."""


def machine_for(db: Session, tag: str) -> str | None:
    """The machine a tag typed on the page names: a computer, or a motherboard -- the
    machine it is fitted in, or itself on its own. None for anything else."""
    tag = (exact_tag(tag) or tag or "").strip().upper()
    subject = _subject(db, tag) if tag else None
    if subject is None:
        return None
    return (tree.load(db).machine(tag) or tag) if isinstance(subject, Part) else tag


def taken_out(db: Session, s: Survey, machine: str) -> list[tuple[str, str]]:
    """The parts filing a survey against `machine` would take out of another machine,
    as (part, machine): what the page says before it does it."""
    t = tree.load(db)
    out = []
    for f in findings_of(s):
        if not f["identifier"]:
            continue
        part = known_part(db, f)
        if part is None:
            continue
        tag = part.asset_id.upper()
        here = t.machine(tag)
        if here is not None and here != machine and not on_bench(db, t, tag):
            out.append((tag, here))
    return out


def file_against(db: Session, s: Survey, tag: str, who: str) -> Filing:
    """File a survey that waits for a machine against the one named, as if the tag had
    been typed at the machine. The parts it would take out of another machine are moved
    first, by edit, because a person has said so."""
    if s.waiting != FOR_MACHINE:
        raise Refused("This survey is not waiting for a machine.")
    tag = (exact_tag(tag) or tag).strip().upper()
    subject = _subject(db, tag)
    if subject is None:
        raise Refused(f"{tag or 'That'} is not a machine or a motherboard in the register.")
    t = tree.load(db)
    machine = (t.machine(tag) or tag) if isinstance(subject, Part) else tag
    for part_tag, _here in taken_out(db, s, machine):
        part = _part(db, part_tag)
        if part is not None:
            tree.put(db, part, machine, tree.EDIT, who, t)
    return settle(db, s, {}, who, machine=machine, how=FILED, by=who)


def answer_on_page(
    db: Session, s: Survey, thing: str, how: str, tag: str, bench: str, who: str
) -> Filing:
    """An answer given on the survey's page for one thing it found, done as if it had
    been given at the machine; an answer already given is changed."""
    if not s.machine:
        raise Refused("This survey is waiting for a machine first.")
    found = findings_of(s)
    f = next((x for x in found if x["thing"] == thing), None)
    if f is None or f["kind"] == MACHINE:
        raise Refused("That is not something this survey can be asked about.")
    wanted = {"new": PART, "link": PART, "bench": PART, MACHINE: MACHINE, OUT: OUT}.get(how)
    if wanted is None or wanted not in f["fits"]:
        raise Refused("That answer does not fit it.")
    machine = s.machine
    t = tree.load(db)
    done = Filing()
    keys = keys_of(s)
    f["bench"] = False
    texts = _rom_texts(s)
    if how == "new":
        made = _new_part(db, keys, f, machine, who, t, done, tree.EDIT, texts)
        f["answer"], f["part"] = PART, made.asset_id
    elif how == "bench":
        place = db.get(Thing, (bench or "").strip().upper())
        if not isinstance(place, Location) or place.kind != locations.BENCH:
            raise Refused("Choose a bench to put it on.")
        made = _new_part(db, keys, f, place.asset_id, who, t, done, tree.EDIT, texts)
        f["answer"], f["part"], f["bench"] = PART, made.asset_id, True
    elif how == "link":
        part = _part(db, exact_tag(tag) or tag)
        if part is None:
            raise Refused(f"{tag or 'That'} is not a part in the register.")
        _identify_part(part, f)
        if on_bench(db, t, part.asset_id):
            f["answer"], f["part"], f["bench"] = PART, part.asset_id.upper(), True
        else:
            if t.holder(part.asset_id.upper()) != machine:
                tree.put(db, part, machine, tree.EDIT, who, t)
            f["answer"], f["part"] = PART, part.asset_id.upper()
    else:
        f["answer"], f["part"] = how, None
    if f["identifier"]:
        _record_answer(db, f, machine)
    else:
        remember(db, machine, f)
    subject = _subject(db, machine)
    if f["answer"] == MACHINE and subject is not None:
        board = subject if isinstance(subject, Part) else _board_of(db, t, machine)
        if board is not None:
            if f["kind"] == "video":
                _spec_fill(db, board, [("Onboard video", _video_name(f, texts))], done)
            elif f["kind"] == "ports":
                _spec_fill(db, board, [("Ports", _ports_spec(keys))], done)
            else:
                word = "network" if f["kind"] == "nic" else _built_in_word(f)
                _spec_fill(db, board, [(f"Onboard {word}", _card_name(f, texts))], done)
    if subject is not None:
        _link_rom(db, s, f, subject)
    if f["kind"] == "nic":
        s.bench_card = f["part"] if f["bench"] else None
    s.findings = json.dumps(found)
    s.waiting = FOR_ANSWER if any(x["answer"] is None for x in found) else None
    return done


def _record_answer(db: Session, f: Finding, machine: str) -> None:
    row = seen_row(db, f["id_kind"], f["identifier"])
    if row is None:
        return
    row.answer = f["answer"]
    row.asset_id = f["part"] if f["answer"] == PART else machine if f["answer"] == MACHINE else None


def _link_rom(db: Session, s: Survey, f: Finding, subject: Computer | Part) -> None:
    """A ROM whose card has just been answered for: linked to what it now belongs to,
    and a file nothing else uses forgotten when the card is left out."""
    if not f["segment"]:
        return
    t = tree.load(db)
    board = subject if isinstance(subject, Part) else _board_of(db, t, subject.asset_id)
    for rom in roms_of(s):
        if rom.get("segment") != f["segment"] or not isinstance(rom.get("file"), int):
            continue
        file_id = cast(int, rom["file"])
        owner = _owner(f, subject, board)
        if owner:
            filesdb.link(db, file_id, owner)
        elif f["answer"] == OUT:
            stored = db.get(StoredFile, file_id)
            linked = db.query(FileAsset).filter(FileAsset.file_id == file_id).count()
            if stored is not None and not linked:
                filesdb.remove(db, stored)


def delete(db: Session, s: Survey) -> None:
    """Delete a survey and its report. What it filled in stays, since that is the record
    now, and so do its ROM files and the serial numbers it recorded."""
    db.delete(s)
    db.flush()


# --- reading back -------------------------------------------------------------------------------


def as_dict(s: Survey) -> dict[str, object]:
    """A survey as the API answers with it."""
    return {
        "id": s.id,
        "agent": s.agent,
        "taken": s.taken.isoformat() if s.taken else None,
        "clock": s.clock,
        "machine": s.machine,
        "how": s.how,
        "by": s.by,
        "waiting": s.waiting,
        "reason": s.reason,
        "result": s.result,
        "bench_card": s.bench_card,
        "findings": [
            {
                "thing": f["thing"],
                "kind": f["kind"],
                "name": f["name"],
                "identifier": f["identifier"],
                "answer": f["answer"],
                "part": f["part"],
                "bench": f["bench"],
                "fits": f["fits"],
            }
            for f in findings_of(s)
        ],
        "filled": json.loads(s.filled or "[]"),
        "differs": json.loads(s.differs or "[]"),
        "missing": json.loads(s.missing or "[]"),
        "roms": [
            {k: rom.get(k) for k in ("segment", "size", "filename", "file", "text")}
            for rom in roms_of(s)
        ],
        "report": s.report,
    }


def listing(db: Session) -> list[Survey]:
    """Every survey: waiting first, then newest first."""
    rows = db.query(Survey).order_by(Survey.taken.desc(), Survey.id.desc()).all()
    return [s for s in rows if s.waiting] + [s for s in rows if not s.waiting]


def seen(db: Session) -> list[SurveySeen]:
    return db.query(SurveySeen).order_by(SurveySeen.last_seen.desc(), SurveySeen.id.desc()).all()


def seen_matching(db: Session, q: str) -> list[SurveySeen]:
    """What surveys have seen with `q` in it: a serial number or an address, for a
    search by somebody signed in."""
    needle = " ".join((q or "").split())
    if len(needle) < 3:
        return []
    return (
        db.query(SurveySeen)
        .filter(SurveySeen.value.contains(needle))
        .order_by(SurveySeen.last_seen.desc())
        .limit(20)
        .all()
    )


def history_links(db: Session, log_ids: Iterable[int]) -> dict[int, int]:
    """{history line: survey} for survey lines, so a line can link to its survey."""
    ids = list(log_ids)
    if not ids:
        return {}
    return {
        s.log_id: s.id
        for s in db.query(Survey).filter(Survey.log_id.in_(ids))
        if s.log_id is not None
    }


def prefill(s: Survey) -> dict[str, str]:
    """What a new machine's form starts with, from a survey that waits for one."""
    keys = keys_of(s)
    kb = memory_kb(keys)
    return {
        "cpu": cpu_line(keys),
        "os": keys.get("OS", "").strip(),
        "manufacturer": said(keys.get("SYSTEM_MAKER")),
        "model": said(keys.get("SYSTEM_MODEL")),
        "serial": said(keys.get("SYSTEM_SERIAL")),
        "installed_ram": entry.fmt_kb(kb) if kb else "",
    }


def benches(db: Session) -> list[Location]:
    return db.query(Location).filter(Location.kind == locations.BENCH).order_by(Location.name).all()
