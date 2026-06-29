#!/usr/bin/env python3
"""Guided helper for adding/updating computers, parts, and generic preset parts.

It assigns the next RH-#### asset number across BOTH tables, writes valid CSV
(no quoting/escaping for you to get wrong), and — for a part — lets you link it
to an existing computer. Run it with no arguments for the interactive prompts,
or pass flags to add in one line.

Examples:
    python scripts/add.py                         # interactive add (then walks generics)
    python scripts/add.py computer --name "Amiga 1200" --year 1992
    python scripts/add.py part --type cpu --computer RH-0002 --model "i486 DX2-66"
    python scripts/add.py preset --computer RH-0001          # walk common parts
    python scripts/add.py preset --computer RH-0001 ram:16MB svga:1MB   # one-shot
    python scripts/add.py update RH-0001          # edit an existing computer or part
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap

from common import (COMPUTER_COLUMNS, PART_COLUMNS, TYPE_LABELS, TYPE_ORDER,
                    display_name, item_url, load_computers, load_config,
                    load_parts, load_presets, next_asset_id, parse_specs,
                    save_computers, save_parts, type_label)

# Components walked through (in order) when adding generics to a computer.
# Deliberately excludes keyboard/mouse.
GENERIC_WALK = ["ram", "vga", "hdd", "floppy35", "cdrom", "sound", "nic", "io", "psu"]

# For these part types, a single headline amount lives under this spec key.
PRIMARY_SPEC = {"ram": "Size", "storage": "Capacity", "gpu": "Memory"}
AMOUNT_EG = {"Size": "e.g. 2MB", "Capacity": "e.g. 540MB", "Memory": "e.g. 1MB"}

# Multipliers to normalise a typed amount to KB. Bare numbers are assumed MB.
_KB_UNITS = {"": 1024, "k": 1, "kb": 1, "m": 1024, "mb": 1024,
             "g": 1024 * 1024, "gb": 1024 * 1024,
             "t": 1024 * 1024 * 1024, "tb": 1024 * 1024 * 1024}

SPEC_HINTS = {
    "motherboard": "Chipset, Socket, Slots, RAM, Form factor",
    "cpu": "Socket, Speed, FSB, Cores, Cache",
    "ram": "Type, Size, Speed",
    "gpu": "Memory, Chipset, Type",
    "sound": "Chipset, FM, Ports",
    "network": "Connector, Chipset",
    "io": "Chipset",
    "storage": "Role (interface/capacity/geometry asked separately)",
    "optical": "Media, Interface, Speed",
    "floppy": "Media, Interface",
    "psu": "Form factor, Wattage, Connectors",
    "cooler": "Type, Socket",
    "peripheral": "type-specific (Size, Resolution, …)",
    "other": "free text",
}


# --- tiny input helpers ----------------------------------------------------

def ask(label, default=""):
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {label}{suffix}: ").strip()
    except EOFError:
        return default
    return val or default


def ask_type(default=""):
    print("\n  Part type — choose a number or type a name:")
    for i, t in enumerate(TYPE_ORDER, 1):
        print(f"    {i:>2}. {t:<12} {TYPE_LABELS.get(t, '')}")
    raw = ask("type", default)
    if not raw:
        return "other"
    if raw.isdigit() and 1 <= int(raw) <= len(TYPE_ORDER):
        return TYPE_ORDER[int(raw) - 1]
    return raw.lower()


def ask_computer(computers, default=""):
    if not computers:
        print("  (no computers yet — this will be standalone)")
        return default
    print("\n  Install in which computer? number, asset_id, or blank for standalone:")
    for i, c in enumerate(computers, 1):
        print(f"    {i:>2}. {c['asset_id']}  {display_name(c)}")
    raw = ask("computer", default)
    if not raw:
        return ""
    if raw.isdigit() and 1 <= int(raw) <= len(computers):
        return computers[int(raw) - 1]["asset_id"]
    return raw  # assume they typed an asset_id


# Ordered fields prompted in interactive mode: (key, prompt label, default).
COMPUTER_FIELDS = [
    ("name", "name (e.g. 'Amiga 1200' or build name)", ""),
    ("manufacturer", "manufacturer (or 'Custom build')", ""),
    ("model", "model", ""),
    ("year", "year", ""),
    ("form_factor", "form factor (AT/Baby-AT/ATX/proprietary/all-in-one)", ""),
    ("chassis", "chassis / case (desktop, tower, mini-tower, …)", ""),
    ("os", "operating system", ""),
    ("condition", "condition", "Working"),
    ("source", "source (where/how acquired)", ""),
    ("acquired_date", "acquired date (YYYY-MM-DD)", ""),
    ("theretroweb_url", "theretroweb URL", ""),
    ("wikipedia_url", "wikipedia URL", ""),
    ("notes", "notes", ""),
]

PART_FIELDS = [
    ("manufacturer", "manufacturer", ""),
    ("model", "model", ""),
    ("name", "name (optional; defaults to maker+model)", ""),
    ("year", "year", ""),
    ("specs", "specs", ""),
    ("condition", "condition", "Working"),
    ("source", "source (where/how acquired)", ""),
    ("acquired_date", "acquired date (YYYY-MM-DD)", ""),
    ("theretroweb_url", "theretroweb URL", ""),
    ("notes", "notes", ""),
]


def _short(label):
    return label.split(" (")[0].strip()


def show_field_list(kind_title, leading, fields):
    """Print, up front, the fields this entry will ask for (the reminder)."""
    names = list(leading)
    for _, label, default in fields:
        names.append(f"{_short(label)} [{default}]" if default else _short(label))
    print(f"\nThis {kind_title} entry will ask for, in order "
          "(Enter skips a field; [x] = default):")
    print(textwrap.fill(" · ".join(names), width=78,
                        initial_indent="  ", subsequent_indent="  "))


def prompt_fields(fields, current=None):
    """Ask each field. If `current` (a row) is given, its values are the
    defaults — that's how 'update' keeps existing values on Enter."""
    out = {}
    for key, label, default in fields:
        d = (current.get(key) if current else "") or default
        out[key] = ask(label, d)
    return out


def computer_row_interactive():
    show_field_list("computer", [], COMPUTER_FIELDS)
    print()
    return prompt_fields(COMPUTER_FIELDS)


def part_row_interactive(computers):
    show_field_list("part", ["type", "computer to install in"], PART_FIELDS)
    ptype = ask_type()
    computer_id = ask_computer(computers)
    print(f"\nNew {type_label(ptype).upper()} — specs format 'Key: value | Key: value' "
          f"(suggested: {SPEC_HINTS.get(ptype, 'free text')})\n")
    row = prompt_fields(PART_FIELDS)
    row["type"] = ptype
    row["computer_id"] = computer_id
    apply_type_prompts(row, ptype)
    return row


# --- specs / amount helpers ------------------------------------------------

def split_amount(token):
    """'ram:16MB' -> ('ram', '16MB');  'ram' -> ('ram', '')."""
    if ":" in token:
        k, v = token.split(":", 1)
        return k.strip(), v.strip()
    return token.strip(), ""


def to_kb(text):
    """'2MB'->2048, '512KB'->512, '1GB'->1048576, '2'->2048 (assumes MB).
    Returns None if it can't be parsed."""
    m = re.match(r"^\s*([\d.]+)\s*([a-zA-Z]*)\s*$", text or "")
    if not m:
        return None
    unit = m.group(2).lower()
    if unit not in _KB_UNITS:
        return None
    try:
        return int(round(float(m.group(1)) * _KB_UNITS[unit]))
    except ValueError:
        return None


def normalise_amount(spec_key, amt):
    """Memory amounts (Size/Memory) normalise to KB; others kept as typed."""
    if spec_key in ("Size", "Memory"):
        kb = to_kb(amt)
        if kb is not None:
            return f"{kb} KB"
    return amt


def merge_spec(specs, key, value):
    """Set/replace 'key: value' inside a 'a: b | c: d' specs string."""
    pairs, replaced, out = parse_specs(specs), False, []
    for k, v in pairs:
        if k.lower() == key.lower():
            out.append((key, value))
            replaced = True
        else:
            out.append((k, v))
    if not replaced:
        out.append((key, value))
    return " | ".join(f"{k}: {v}" if k else v for k, v in out)


_DATE_RE = re.compile(r"^(\d{4}([-/]\d{1,2}){0,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})$")


def date_warning(value):
    """Gentle heads-up if acquired_date doesn't look like a date (e.g. an eBay
    order number ran into the field). Non-blocking."""
    v = (value or "").strip()
    if v and not _DATE_RE.match(v):
        return (f"  ! '{v}' doesn't look like a date (e.g. 2026-06-23) — check an "
                "order number didn't run into the acquired-date field.")
    return None


# --- presets (generic, reusable parts) -------------------------------------

def list_presets():
    presets = load_presets()
    if not presets:
        print("No presets found (data/presets.csv).")
        return
    print("Available presets — e.g.  add.py preset --computer RH-0001 ram:16MB svga:1MB floppy525")
    for k, pr in presets.items():
        amt = PRIMARY_SPEC.get(pr["type"])
        hint = f"   (takes {k}:<{amt.lower()}>)" if amt else ""
        print(f"  {k:<10} {pr['type']:<10} {pr['name']}{hint}")


def ask_disk_image(current=""):
    return ask("disk image filename (your image of it as received), blank to skip", current)


def ask_storage_specs(specs, ask_capacity=True):
    """Storage prompts: protocol, capacity and optional CHS geometry, merged in."""
    proto = ask("protocol (ATA, ATAPI, XTA, RLL, MFM, ESDI, SCSI), blank to skip")
    if proto:
        specs = merge_spec(specs, "Protocol", proto)
    if ask_capacity:
        cap = ask("capacity (e.g. 540 MB), blank to skip")
        if cap:
            specs = merge_spec(specs, "Capacity", cap)
    chs = ask("geometry C/H/S — cylinders/heads/sectors (e.g. 1024/16/63), blank to skip")
    if chs:
        specs = merge_spec(specs, "CHS", chs)
    return specs


CARD_TYPES = ("gpu", "sound", "network", "io")


def ask_interface(specs, examples):
    """Prompt how a part connects, merged into specs as 'Interface'."""
    iface = ask(f"interface ({examples}), blank to skip")
    if iface:
        specs = merge_spec(specs, "Interface", iface)
    return specs


PORT_CODES = [("I", "IDE"), ("C", "SCSI"), ("A", "SATA"), ("M", "MFM"),
              ("R", "RLL"), ("F", "Floppy"), ("S", "Serial"), ("P", "Parallel"),
              ("G", "Game")]


def expand_ports(code):
    """'IFSSP' -> ('IDE, Floppy, 2× Serial, Parallel', [unknown letters]).
    Order-independent; repeated letters become a count."""
    from collections import Counter
    counts = Counter(c for c in code.upper() if c.isalpha())
    known = {letter for letter, _ in PORT_CODES}
    out = []
    for letter, name in PORT_CODES:
        n = counts.get(letter, 0)
        if n:
            out.append(f"{n}× {name}" if n > 1 else name)
    unknown = sorted(c for c in counts if c not in known)
    return ", ".join(out), unknown


def ask_ports(specs):
    raw = ask("ports — letters I=IDE C=SCSI A=SATA M=MFM R=RLL F=Floppy "
              "S=Serial P=Parallel G=Game (e.g. IFSSP), blank to skip")
    if not raw:
        return specs
    longform, unknown = expand_ports(raw)
    if unknown:
        print(f"  (ignored unrecognised port letters: {', '.join(unknown)})")
    if longform:
        specs = merge_spec(specs, "Ports", longform)
    return specs


def apply_type_prompts(row, ptype):
    """Type-specific extra prompts run after the standard part fields."""
    if ptype in CARD_TYPES or ptype == "peripheral":
        row["specs"] = ask_interface(row.get("specs", ""),
                                     "ISA, PCI, VLB, AGP, USB, parallel, serial, PS/2")
        if ptype == "io":
            row["specs"] = ask_ports(row.get("specs", ""))
    elif ptype == "storage":
        row["specs"] = ask_interface(row.get("specs", ""), "IDE, SCSI, MFM, CF, SD")
        row["specs"] = ask_storage_specs(row.get("specs", ""))
        row["disk_image"] = ask_disk_image(row.get("disk_image", ""))


def _add_preset_part(pr, computer_id, config, specs, extra=None):
    partial = {"type": pr["type"], "manufacturer": pr.get("manufacturer", "Generic"),
               "name": pr.get("name", ""), "specs": specs,
               "computer_id": computer_id, "condition": "Working"}
    if extra:
        partial.update(extra)
    asset_id, row = commit_new("part", partial, config, dry_run=False)
    print(f"  + {asset_id}  {display_name(row)}" + (f"  ({specs})" if specs else ""))
    return asset_id


def detailed_part(ptype, computer_id, config, seed):
    """Full part entry for one slot (type + computer fixed), pre-seeded from the
    preset, with optional enrichment. Used by the walk's 'advanced' option."""
    print(f"\n  Advanced {type_label(ptype)} — enter the real card's details "
          "(Enter keeps the suggested value):")
    # Don't pre-seed the name — leaving it blank makes it default to maker+model.
    seed_row = {"specs": seed.get("specs", "")}
    fields = prompt_fields(PART_FIELDS, current=seed_row)
    fields["type"] = ptype
    fields["computer_id"] = computer_id
    apply_type_prompts(fields, ptype)
    asset_id, row = commit_new("part", fields, config, dry_run=False)
    print(f"  + {asset_id}  {display_name(row)}")
    if ask("Fetch photo + specs now (Retro Web if linked, else Wikipedia)? (y/N)",
           "N").lower().startswith("y"):
        run_enrich(asset_id, "part", row.get("theretroweb_url", ""))
    return asset_id


def walk_generics(computer_id, config):
    """Go through the common components one at a time. For RAM/video/disk ask the
    amount (blank skips); others are yes/no. Type 'a' at any prompt to enter the
    full details of a real (branded) card for that slot. Memory is stored in KB."""
    presets = load_presets()
    added = []
    for key in GENERIC_WALK:
        pr = presets.get(key)
        if not pr:
            continue
        spec_key = PRIMARY_SPEC.get(pr["type"])
        if spec_key:
            ans = ask(f"{pr['name']} — amount ({AMOUNT_EG.get(spec_key, '')}), "
                      "'a' for advanced, blank to skip")
            if not ans:
                continue
            if ans.lower() in ("a", "adv", "advanced"):
                added.append(detailed_part(pr["type"], computer_id, config, pr))
            else:
                specs = merge_spec(pr.get("specs", ""), spec_key,
                                   normalise_amount(spec_key, ans))
                extra = None
                if pr["type"] == "storage":
                    specs = ask_storage_specs(specs, ask_capacity=False)  # capacity already asked
                    di = ask_disk_image()
                    extra = {"disk_image": di} if di else None
                added.append(_add_preset_part(pr, computer_id, config, specs, extra))
        else:
            ans = ask(f"Add {pr['name']}? (y / a=advanced / N)", "N").lower()
            if ans in ("a", "adv", "advanced"):
                added.append(detailed_part(pr["type"], computer_id, config, pr))
            elif ans.startswith("y"):
                added.append(_add_preset_part(pr, computer_id, config, pr.get("specs", "")))
    if added:
        print(f"\nAdded {len(added)} part(s).")
    return added


def add_presets(items, computer_id, config, dry_run):
    """Non-interactive one-shot: keys, optionally key:amount (ram:16MB)."""
    presets = load_presets()
    if not presets:
        print("No presets found (data/presets.csv missing or empty).")
        return []
    seen, added = set(), []
    for tok in items:
        key, amt = split_amount(tok)
        if key in seen:
            continue
        seen.add(key)
        pr = presets.get(key)
        if not pr:
            print(f"  ! unknown preset: {key}  (run: add.py preset --list)")
            continue
        specs = pr.get("specs", "")
        spec_key = PRIMARY_SPEC.get(pr["type"])
        if spec_key and amt:
            specs = merge_spec(specs, spec_key, normalise_amount(spec_key, amt))
        if dry_run:
            print(f"[dry-run] {key} -> type {pr['type']}, specs: {specs}")
            continue
        added.append(_add_preset_part(pr, computer_id, config, specs))
    return added


def offer_generic(computer_id, config):
    if ask("Add generic components now? (y/N)", "N").lower().startswith("y"):
        return walk_generics(computer_id, config)
    return []


# --- write / update a row --------------------------------------------------

def commit_new(kind, partial, config, dry_run):
    computers = load_computers()
    parts = load_parts()
    asset_id = next_asset_id(config, computers, parts)

    columns = COMPUTER_COLUMNS if kind == "computer" else PART_COLUMNS
    row = {c: "" for c in columns}
    row.update(partial)
    row["asset_id"] = asset_id

    if kind == "part" and row.get("computer_id"):
        if row["computer_id"] not in {c["asset_id"] for c in computers}:
            print(f"  ! warning: computer_id {row['computer_id']} is not an existing "
                  "computer — saving anyway (fix later or leave blank for standalone).")

    dw = date_warning(row.get("acquired_date", ""))
    if dw:
        print(dw)

    if dry_run:
        print(f"\n[dry-run] would add to {kind}s.csv as {asset_id}:")
        for c in columns:
            if row[c]:
                print(f"    {c}: {row[c]}")
        return asset_id, row

    if kind == "computer":
        computers.append(row)
        save_computers(computers)
    else:
        parts.append(row)
        save_parts(parts)
    return asset_id, row


def find_asset(asset_id):
    computers, parts = load_computers(), load_parts()
    for c in computers:
        if c["asset_id"] == asset_id:
            return "computer", c, computers, parts
    for p in parts:
        if p["asset_id"] == asset_id:
            return "part", p, computers, parts
    return None, None, computers, parts


def update_interactive(asset_id, config, dry_run):
    kind, row, computers, parts = find_asset(asset_id)
    if not row:
        print(f"No asset '{asset_id}' found in computers.csv or parts.csv.")
        return
    print(f"\nUpdating {kind} {asset_id} — press Enter to keep the current value.")
    if kind == "part":
        row["type"] = ask_type(row.get("type", "") or "other")
        row["computer_id"] = ask_computer(computers, row.get("computer_id", ""))
        row.update(prompt_fields(PART_FIELDS, current=row))
        apply_type_prompts(row, row.get("type", ""))
    else:
        show_field_list("computer", [], COMPUTER_FIELDS)
        print()
        row.update(prompt_fields(COMPUTER_FIELDS, current=row))

    dw = date_warning(row.get("acquired_date", ""))
    if dw:
        print(dw)

    if dry_run:
        print(f"\n[dry-run] would update {asset_id}:")
        for k, v in row.items():
            if v:
                print(f"    {k}: {v}")
        return

    save_computers(computers) if kind == "computer" else save_parts(parts)
    print(f"\nUpdated {asset_id}: {display_name(row)}")
    touched = [asset_id]
    if kind == "computer":
        touched += offer_generic(asset_id, config)
    regenerate_labels(touched)
    print("\nNext: ./publish.sh   (build, commit, push)")


def run_enrich(asset_id, kind, theretroweb_url):
    script = __file__.replace("add.py", "enrich.py")
    cmd = [sys.executable, script, "--only", asset_id]
    if kind == "part" and theretroweb_url:
        cmd += ["--source", "theretroweb", "--browser"]
        print(f"\nFetching {asset_id} photo + specs from Retro Web (browser)…")
    else:
        print(f"\nLooking up {asset_id} on Wikipedia…")
    try:
        subprocess.run(cmd, check=False)
    except Exception as exc:  # noqa: BLE001
        print(f"  enrichment skipped: {exc}")


def regenerate_labels(asset_ids):
    """Auto-(re)generate labels for these assets (and parent computers, whose
    build summary may have changed). Computers get full+small, peripherals small."""
    ids = [a for a in asset_ids if a]
    if not ids:
        return
    try:
        import make_labels
        make_labels.regenerate(ids, load_config())
    except Exception as exc:  # noqa: BLE001
        print(f"  (label generation skipped: {exc})")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="preview, don't write")
    p.add_argument("--enrich", action="store_true",
                   help="run Wikipedia enrichment on the new item afterwards")
    sub = p.add_subparsers(dest="kind")

    pc = sub.add_parser("computer", help="add a computer (non-interactive)")
    for f in ("name", "manufacturer", "model", "year", "form_factor", "chassis",
              "os", "condition", "source", "acquired_date",
              "theretroweb_url", "wikipedia_url", "notes"):
        pc.add_argument(f"--{f.replace('_', '-')}", dest=f, default="")

    pp = sub.add_parser("part", help="add a part (non-interactive)")
    pp.add_argument("--type", dest="type", default="other")
    pp.add_argument("--computer", dest="computer_id", default="",
                    help="asset_id of the computer it's installed in (blank = standalone)")
    for f in ("manufacturer", "model", "name", "year", "specs", "condition",
              "source", "acquired_date", "theretroweb_url", "wikipedia_url",
              "notes", "disk_image"):
        pp.add_argument(f"--{f.replace('_', '-')}", dest=f, default="")

    ppre = sub.add_parser("preset",
                          help="add generic parts: walk interactively, or pass keys/key:amount")
    ppre.add_argument("keys", nargs="*",
                      help="preset keys, optionally key:amount (ram:16MB); blank = guided walk")
    ppre.add_argument("--computer", dest="computer_id", default="")
    ppre.add_argument("--list", action="store_true", dest="list",
                      help="list available presets and exit")

    pud = sub.add_parser("update", help="update an existing computer or part by asset_id")
    pud.add_argument("asset_id")

    args = p.parse_args()
    config = load_config()

    if args.kind == "update":
        update_interactive(args.asset_id, config, args.dry_run)
        return

    if args.kind == "preset":
        if args.list:
            list_presets()
            return
        computer_id = args.computer_id or ask_computer(load_computers())
        if args.keys:
            added = add_presets(args.keys, computer_id, config, args.dry_run)
        else:
            added = walk_generics(computer_id, config)
        if added and not args.dry_run:
            regenerate_labels(added)
            print(f"\nAdded {len(added)} generic part(s) to {computer_id or '(standalone)'}. "
                  "Run build_site.py, then commit & push.")
        return

    interactive = args.kind is None
    if interactive:
        kind = ask("Add a (c)omputer or (p)art?", "c").lower()
        kind = "part" if kind.startswith("p") else "computer"
        if kind == "computer":
            partial = computer_row_interactive()
        else:
            partial = part_row_interactive(load_computers())
        do_enrich = ask("Look up photo/specs now (Wikipedia, or Retro Web for a linked part)? (Y/n)",
                        "Y").lower().startswith("y")
    else:
        kind = args.kind
        skip = {"dry_run", "enrich", "kind"}
        partial = {k: v for k, v in vars(args).items() if k not in skip and v}
        do_enrich = args.enrich

    asset_id, row = commit_new(kind, partial, config, args.dry_run)
    if args.dry_run:
        return

    touched = [asset_id]
    print(f"\nAdded {asset_id}: {display_name(row)}")
    if config.get("base_url") and "USERNAME" not in config.get("base_url", ""):
        print(f"  page will be: {item_url(config, asset_id)}")
    if do_enrich:
        run_enrich(asset_id, kind, row.get("theretroweb_url", ""))
    if interactive and kind == "computer":
        touched += offer_generic(asset_id, config)

    regenerate_labels(touched)
    print("\nNext: ./publish.sh   (build, commit, push)")


if __name__ == "__main__":
    main()
