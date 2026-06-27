#!/usr/bin/env python3
"""Guided helper for adding/updating computers, parts, and generic preset parts.

It assigns the next RH-#### asset number across BOTH tables, writes valid CSV
(no quoting/escaping for you to get wrong), and — for a part — lets you link it
to an existing computer. Run it with no arguments for the interactive prompts,
or pass flags to add in one line.

Examples:
    python scripts/add.py                         # interactive add
    python scripts/add.py computer --name "Amiga 1200" --year 1992
    python scripts/add.py part --type cpu --computer RH-0002 --model "i486 DX2-66"
    python scripts/add.py preset --computer RH-0001 ram:16MB hdd:540MB vga:1MB floppy35
    python scripts/add.py preset --computer RH-0001 standard
    python scripts/add.py update RH-0001          # edit an existing computer or part
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap

from common import (COMPUTER_COLUMNS, PART_COLUMNS, TYPE_LABELS, TYPE_ORDER,
                    display_name, item_url, load_computers, load_config,
                    load_parts, load_presets, next_asset_id, parse_specs,
                    save_computers, save_parts, type_label)

# A sensible "typical PC" bundle, expanded when the preset key 'standard' is used.
STANDARD_PC = ["psu", "ram", "io", "floppy35", "hdd", "vga", "kbd", "mouse"]

# For these part types, a single headline amount lives under this spec key,
# so presets can take "key:amount" (ram:16MB) and we can prompt for it.
PRIMARY_SPEC = {"ram": "Size", "storage": "Capacity", "gpu": "Memory"}
PRIMARY_PROMPT = {"Size": "amount (e.g. 16 MB)",
                  "Capacity": "capacity (e.g. 540 MB)",
                  "Memory": "video memory (e.g. 1 MB)"}

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
    return row


# --- specs helpers ---------------------------------------------------------

def split_amount(token):
    """'ram:16MB' -> ('ram', '16MB');  'ram' -> ('ram', '')."""
    if ":" in token:
        k, v = token.split(":", 1)
        return k.strip(), v.strip()
    return token.strip(), ""


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


# --- presets (generic, reusable parts) -------------------------------------

def list_presets():
    presets = load_presets()
    if not presets:
        print("No presets found (data/presets.csv).")
        return
    print("Available presets — e.g.  add.py preset --computer RH-0001 ram:16MB vga:1MB floppy35")
    for k, pr in presets.items():
        amt = PRIMARY_SPEC.get(pr["type"])
        hint = f"   (takes {k}:<{amt.lower()}>)" if amt else ""
        print(f"  {k:<10} {pr['type']:<10} {pr['name']}{hint}")
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


def add_presets(items, computer_id, config, dry_run, prompt_amounts=False):
    presets = load_presets()
    if not presets:
        print("No presets found (data/presets.csv missing or empty).")
        return []

    # Expand 'standard' and carry any "key:amount" amounts.
    expanded = []
    for tok in items:
        key, amt = split_amount(tok)
        if key == "standard":
            expanded.extend((k, "") for k in STANDARD_PC)
        else:
            expanded.append((key, amt))
    seen, ordered = set(), []
    for key, amt in expanded:
        if key not in seen:
            seen.add(key)
            ordered.append((key, amt))

    added = []
    for key, amt in ordered:
        pr = presets.get(key)
        if not pr:
            print(f"  ! unknown preset: {key}  (run: add.py preset --list)")
            continue
        specs = pr.get("specs", "")
        spec_key = PRIMARY_SPEC.get(pr["type"])
        if spec_key:
            if not amt and prompt_amounts and not dry_run:
                amt = ask(f"{pr['name']} — {PRIMARY_PROMPT.get(spec_key, spec_key)}")
            if amt:
                specs = merge_spec(specs, spec_key, amt)
        partial = {"type": pr["type"], "manufacturer": pr.get("manufacturer", "Generic"),
                   "name": pr.get("name", ""), "specs": specs,
                   "computer_id": computer_id, "condition": "Working"}
        asset_id, row = commit_new("part", partial, config, dry_run)
        added.append(asset_id)
        if not dry_run:
            print(f"  + {asset_id}  {display_name(row)}" + (f"  ({specs})" if specs else ""))
    return added


def offer_generic(computer_id, config):
    if ask("Add generic components now (RAM, floppy, VGA, HDD, PSU, …)? (y/N)",
           "N").lower().startswith("y"):
        keys = pick_presets_interactive(load_presets())
        if keys:
            add_presets(keys, computer_id, config, dry_run=False, prompt_amounts=True)


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
    else:
        show_field_list("computer", [], COMPUTER_FIELDS)
        print()
        row.update(prompt_fields(COMPUTER_FIELDS, current=row))

    if dry_run:
        print(f"\n[dry-run] would update {asset_id}:")
        for k, v in row.items():
            if v:
                print(f"    {k}: {v}")
        return

    save_computers(computers) if kind == "computer" else save_parts(parts)
    print(f"\nUpdated {asset_id}: {display_name(row)}")
    if kind == "computer":
        offer_generic(asset_id, config)
    print("\nNext: python scripts/build_site.py   then commit & push")


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
              "source", "acquired_date", "theretroweb_url", "wikipedia_url", "notes"):
        pp.add_argument(f"--{f.replace('_', '-')}", dest=f, default="")

    ppre = sub.add_parser("preset",
                          help="add generic/common parts from data/presets.csv")
    ppre.add_argument("keys", nargs="*",
                      help="preset keys, optionally key:amount (ram:16MB); 'standard'; blank = picker")
    ppre.add_argument("--computer", dest="computer_id", default="")
    ppre.add_argument("--list", action="store_true", dest="list",
                      help="list available presets and exit")

    pud = sub.add_parser("update", help="update an existing computer or part by asset_id")
    pud.add_argument("asset_id")

    args = p.parse_args()
    config = load_config()

    # --- update ------------------------------------------------------------
    if args.kind == "update":
        update_interactive(args.asset_id, config, args.dry_run)
        return

    # --- presets -----------------------------------------------------------
    if args.kind == "preset":
        if args.list:
            list_presets()
            return
        computer_id = args.computer_id or ask_computer(load_computers())
        if args.keys:
            added = add_presets(args.keys, computer_id, config, args.dry_run)
        else:
            keys = pick_presets_interactive(load_presets())
            if not keys:
                print("Nothing selected.")
                return
            added = add_presets(keys, computer_id, config, args.dry_run, prompt_amounts=True)
        if added and not args.dry_run:
            print(f"\nAdded {len(added)} generic part(s) to {computer_id or '(standalone)'}. "
                  "Run build_site.py, then commit & push.")
        return

    # --- add computer / part ----------------------------------------------
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
    if interactive and kind == "computer":
        offer_generic(asset_id, config)

    print("\nNext:")
    print("  python scripts/build_site.py            # refresh the site")
    print(f"  python scripts/make_labels.py {asset_id}   # print its label")
    print(f"  git add -A && git commit -m \"Add {display_name(row)}\" && git push")


if __name__ == "__main__":
    main()
