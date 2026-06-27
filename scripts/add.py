#!/usr/bin/env python3
"""Guided helper for adding a computer, a part, or generic preset parts.

It assigns the next RH-#### asset number across BOTH tables, writes valid CSV
(no quoting/escaping for you to get wrong), and — for a part — lets you link it
to an existing computer. Run it with no arguments for the interactive prompts,
or pass flags to add in one line.

Examples:
    python scripts/add.py                         # interactive, asks everything
    python scripts/add.py computer --name "Amiga 1200" --year 1992
    python scripts/add.py part --type cpu --computer RH-0002 \\
        --manufacturer Intel --model "i486 DX2-66" --specs "Socket: 3 | Speed: 66 MHz"
    python scripts/add.py preset --list
    python scripts/add.py preset --computer RH-0001 floppy35 vga ram hdd
    python scripts/add.py preset --computer RH-0001 standard   # a typical PC set
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap

from common import (COMPUTER_COLUMNS, PART_COLUMNS, TYPE_LABELS, TYPE_ORDER,
                    display_name, item_url, load_computers, load_config,
                    load_parts, load_presets, next_asset_id, save_computers,
                    save_parts, type_label)

# A sensible "typical PC" bundle, expanded when the preset key 'standard' is used.
STANDARD_PC = ["psu", "ram", "io", "floppy35", "hdd", "vga", "kbd", "mouse"]

SPEC_HINTS = {
    "motherboard": "Chipset, Socket, Slots, RAM, Form factor",
    "cpu": "Socket, Speed, FSB, Cores, Cache",
    "ram": "Type, Size, Speed",
    "gpu": "Bus, Memory, Chipset, Type",
    "sound": "Bus, Chipset, FM, Ports",
    "network": "Bus, Interface, Chipset",
    "io": "Bus, Ports",
    "storage": "Interface, Capacity, Role",
    "optical": "Media, Interface, Speed",
    "floppy": "Media, Interface",
    "psu": "Form factor, Wattage, Connectors",
    "cooler": "Type, Socket",
    "peripheral": "Interface, plus type-specific (Size, Resolution, ...)",
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


def ask_type():
    print("\n  Part type — choose a number or type a name:")
    for i, t in enumerate(TYPE_ORDER, 1):
        print(f"    {i:>2}. {t:<12} {TYPE_LABELS.get(t, '')}")
    while True:
        raw = ask("type")
        if not raw:
            return "other"
        if raw.isdigit() and 1 <= int(raw) <= len(TYPE_ORDER):
            return TYPE_ORDER[int(raw) - 1]
        return raw.lower()


def ask_computer(computers):
    if not computers:
        print("  (no computers yet — this will be standalone)")
        return ""
    print("\n  Install in which computer? number, asset_id, or blank for standalone:")
    for i, c in enumerate(computers, 1):
        print(f"    {i:>2}. {c['asset_id']}  {display_name(c)}")
    raw = ask("computer")
    if not raw:
        return ""
    if raw.isdigit() and 1 <= int(raw) <= len(computers):
        return computers[int(raw) - 1]["asset_id"]
    return raw  # assume they typed an asset_id


# Ordered fields prompted in interactive mode: (key, prompt label, default).
# The same lists drive both the up-front reminder and the prompts.
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


def prompt_fields(fields):
    return {key: ask(label, default) for key, label, default in fields}


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
    return row


# --- presets (generic, reusable parts) -------------------------------------

def resolve_preset_keys(keys):
    out = []
    for k in keys:
        out.extend(STANDARD_PC if k == "standard" else [k])
    seen = set()
    return [k for k in out if not (k in seen or seen.add(k))]


def list_presets():
    presets = load_presets()
    if not presets:
        print("No presets found (data/presets.csv).")
        return
    print("Available presets — e.g.  add.py preset --computer RH-0001 floppy35 vga ram")
    for k, pr in presets.items():
        print(f"  {k:<10} {pr['type']:<10} {pr['name']}")
    print(f"\n  standard   →  {' '.join(STANDARD_PC)}")


def pick_presets_interactive(presets):
    items = list(presets.items())
    print("\nGeneric components — pick numbers/keys (space or comma separated):")
    for i, (k, pr) in enumerate(items, 1):
        print(f"  {i:>2}. {k:<10} {pr['type']:<10} {pr['name']}")
    print("   or type 'standard' for a typical PC set")
    raw = ask("add which?")
    if not raw:
        return []
    keys = []
    for tok in raw.replace(",", " ").split():
        if tok.isdigit() and 1 <= int(tok) <= len(items):
            keys.append(items[int(tok) - 1][0])
        else:
            keys.append(tok)
    return keys


def add_presets(keys, computer_id, config, dry_run):
    presets = load_presets()
    if not presets:
        print("No presets found (data/presets.csv missing or empty).")
        return []
    added = []
    for k in resolve_preset_keys(keys):
        pr = presets.get(k)
        if not pr:
            print(f"  ! unknown preset: {k}  (run: add.py preset --list)")
            continue
        partial = {
            "type": pr["type"], "manufacturer": pr.get("manufacturer", "Generic"),
            "name": pr.get("name", ""), "specs": pr.get("specs", ""),
            "computer_id": computer_id, "condition": "Working",
        }
        asset_id, row = commit_new("part", partial, config, dry_run)
        added.append(asset_id)
        if not dry_run:
            print(f"  + {asset_id}  {display_name(row)}")
    return added


# --- write a row -----------------------------------------------------------

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


def run_enrich(asset_id):
    script = __file__.replace("add.py", "enrich.py")
    print(f"\nLooking up {asset_id} on Wikipedia…")
    try:
        subprocess.run([sys.executable, script, "--only", asset_id], check=False)
    except Exception as exc:  # noqa: BLE001
        print(f"  enrichment skipped: {exc}")


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
              "source", "acquired_date", "theretroweb_url",
              "wikipedia_url", "notes"):
        pp.add_argument(f"--{f.replace('_', '-')}", dest=f, default="")

    ppre = sub.add_parser("preset",
                          help="add generic/common parts from data/presets.csv")
    ppre.add_argument("keys", nargs="*",
                      help="preset keys (or 'standard'); blank = interactive picker")
    ppre.add_argument("--computer", dest="computer_id", default="")
    ppre.add_argument("--list", action="store_true", dest="list",
                      help="list available presets and exit")

    args = p.parse_args()
    config = load_config()

    # --- preset mode -------------------------------------------------------
    if args.kind == "preset":
        if args.list:
            list_presets()
            return
        computer_id = args.computer_id or ask_computer(load_computers())
        keys = args.keys or pick_presets_interactive(load_presets())
        if not keys:
            print("Nothing selected.")
            return
        added = add_presets(keys, computer_id, config, args.dry_run)
        if added and not args.dry_run:
            print(f"\nAdded {len(added)} generic part(s) to "
                  f"{computer_id or '(standalone)'}. "
                  "Run build_site.py, then commit & push.")
        return

    # --- computer / part ---------------------------------------------------
    interactive = args.kind is None
    if interactive:
        kind = ask("Add a (c)omputer or (p)art?", "c").lower()
        kind = "part" if kind.startswith("p") else "computer"
        if kind == "computer":
            partial = computer_row_interactive()
        else:
            partial = part_row_interactive(load_computers())
        do_enrich = ask("Look up photo + summary on Wikipedia now? (Y/n)", "Y").lower().startswith("y")
    else:
        kind = args.kind
        skip = {"dry_run", "enrich", "kind"}
        partial = {k: v for k, v in vars(args).items() if k not in skip and v}
        do_enrich = args.enrich

    asset_id, row = commit_new(kind, partial, config, args.dry_run)
    if args.dry_run:
        return

    print(f"\nAdded {asset_id}: {display_name(row)}")
    if config.get("base_url") and "USERNAME" not in config.get("base_url", ""):
        print(f"  page will be: {item_url(config, asset_id)}")
    if do_enrich:
        run_enrich(asset_id)

    # Offer to bolt on the generic components every PC has.
    if interactive and kind == "computer":
        if ask("Add typical generic components now "
               "(PSU, RAM, floppy, VGA, HDD, keyboard, mouse, I/O)? (y/N)",
               "N").lower().startswith("y"):
            add_presets(["standard"], asset_id, config, False)

    print("\nNext:")
    print("  python scripts/build_site.py            # refresh the site")
    print(f"  python scripts/make_labels.py {asset_id}   # print its label")
    print("  git add -A && git commit -m \"Add "
          f"{display_name(row)}\" && git push")


if __name__ == "__main__":
    main()
