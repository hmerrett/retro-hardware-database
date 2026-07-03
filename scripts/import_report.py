#!/usr/bin/env python3
"""Import a machine's hardware report (written by a DOS detector run off a boot
disk) and PROPOSE updates to its computer row + parts. Nothing is written until
you confirm. See imports/README.md for the boot-disk side.

Reports live in imports/ named after the asset id, e.g. imports/RH-0005.txt.

    python scripts/import_report.py            # every report in imports/
    python scripts/import_report.py RH-0005     # just one

The parser is deliberately tolerant (MSD / HWiNFO / AIDA use different layouts).
Once you drop a real report in, the label lists below can be tuned to match it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (PART_COLUMNS, ROOT, display_name, index_by_id,
                    load_computers, load_config, load_parts, next_asset_id,
                    save_computers, save_parts)

IMPORTS_DIR = ROOT / "imports"

# Report label -> our field. Matched case-insensitively; a label "contains"
# match, so short keys are fine. Extend these once you see a real report.
LABELS = {
    "cpu": ["processor", "cpu type", "central processor", "cpu"],
    "ram": ["total memory", "installed memory", "total physical memory",
            "memory total", "base+ext", "conventional+extended"],
    "video": ["video adapter", "display adapter", "video card", "graphics adapter",
              "video"],
    "os": ["operating system", "os version", "dos version"],
}

CHS_RE = re.compile(r"(\d{2,5})\s*[/xX]\s*(\d{1,3})\s*[/xX]\s*(\d{1,4})")


def clean(v):
    return re.sub(r"\s+", " ", v or "").strip()


def parse_pairs(text):
    """Pull 'label <sep> value' lines, where <sep> is a colon, dotted leaders,
    or two-plus spaces (covers the common DOS report layouts)."""
    pairs = []
    for line in text.splitlines():
        m = re.match(r"\s*([A-Za-z][\w ./\-]{1,38}?)\s*(?::|\.{2,}|\s{2,})\s*(\S.*?)\s*$",
                     line)
        if m:
            pairs.append((clean(m.group(1)).lower(), clean(m.group(2))))
    return pairs


def find(pairs, keys):
    for want in keys:
        for k, v in pairs:
            if want in k:
                return v
    return ""


def detect(text):
    pairs = parse_pairs(text)
    found = {field: find(pairs, keys) for field, keys in LABELS.items()}
    disks = []
    for k, v in pairs:
        if ("disk" in k or "drive" in k or "model" in k) and CHS_RE.search(v):
            disks.append(v)
    if not disks:
        m = CHS_RE.search(text)
        if m:
            disks.append(f"CHS {m.group(1)}/{m.group(2)}/{m.group(3)}")
    found["disks"] = disks
    return {k: v for k, v in found.items() if v}


def blank_part(computer_id):
    row = {c: "" for c in PART_COLUMNS}
    row["computer_id"] = computer_id
    row["condition"] = "Working"
    return row


def propose(asset_id, comp, det, existing_types):
    """Return (computer_updates, [candidate part rows]) — nothing written yet."""
    cupd = {}
    if det.get("os") and not comp.get("os"):
        cupd["os"] = det["os"]

    parts_out = []
    if det.get("cpu") and "cpu" not in existing_types:
        r = blank_part(asset_id)
        r.update(type="cpu", name=det["cpu"], notes="detected via boot report")
        parts_out.append(r)
    if det.get("ram") and "ram" not in existing_types:
        r = blank_part(asset_id)
        r.update(type="ram", name="Detected RAM", specs=f"Size: {det['ram']}",
                 notes="detected via boot report")
        parts_out.append(r)
    if det.get("video") and "gpu" not in existing_types:
        r = blank_part(asset_id)
        r.update(type="gpu", name=det["video"], notes="detected via boot report")
        parts_out.append(r)
    if "storage" not in existing_types:
        for d in det.get("disks", []):
            r = blank_part(asset_id)
            chs = CHS_RE.search(d)
            specs = "Interface: IDE"
            if chs:
                specs += f" | CHS: {chs.group(1)}/{chs.group(2)}/{chs.group(3)}"
            r.update(type="storage", name="Detected drive", specs=specs,
                     notes=f"detected via boot report: {d}")
            parts_out.append(r)
    return cupd, parts_out


def ask(q):
    try:
        return input(q).strip().lower().startswith("y")
    except EOFError:
        return False


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if not IMPORTS_DIR.exists():
        print(f"No imports/ folder yet — drop reports in {IMPORTS_DIR}")
        return

    config = load_config()
    computers = load_computers()
    parts = load_parts()
    comp_by_id = index_by_id(computers)
    parts_by_comp = {}
    for p in parts:
        parts_by_comp.setdefault(p.get("computer_id", ""), []).append(p)

    reports = sorted(IMPORTS_DIR.glob("*.txt"))
    if only:
        reports = [r for r in reports if r.stem == only]
        if not reports:
            print(f"No report imports/{only}.txt")
            return

    wrote_c = wrote_p = 0
    for rpt in reports:
        asset_id = rpt.stem
        comp = comp_by_id.get(asset_id)
        if not comp:
            print(f"\n{rpt.name}: no computer {asset_id} in computers.csv — skipping")
            continue
        det = detect(rpt.read_text(encoding="utf-8", errors="replace"))
        if not det:
            print(f"\n{asset_id} ({display_name(comp)}): nothing recognised in {rpt.name}")
            continue

        existing_types = {p.get("type") for p in parts_by_comp.get(asset_id, [])}
        cupd, new_parts = propose(asset_id, comp, det, existing_types)

        print(f"\n=== {asset_id}  {display_name(comp)} ===")
        for k, v in det.items():
            if k != "disks":
                print(f"  detected {k}: {v}")
        for d in det.get("disks", []):
            print(f"  detected disk: {d}")
        if not cupd and not new_parts:
            print("  (already recorded — nothing to add)")
            continue
        if cupd:
            print("  would set on the computer: "
                  + ", ".join(f"{k}={v}" for k, v in cupd.items()))
        for r in new_parts:
            extra = f"  [{r['specs']}]" if r["specs"] else ""
            print(f"  would add part: {r['type']}  {r['name']}{extra}")

        if not ask("  apply these? (y/N) "):
            print("  skipped.")
            continue

        comp.update(cupd)
        for r in new_parts:
            r["asset_id"] = next_asset_id(config, computers, parts)
            parts.append(r)
            parts_by_comp.setdefault(asset_id, []).append(r)
            wrote_p += 1
        if cupd:
            wrote_c += 1
        print(f"  applied ({len(new_parts)} part(s)).")

    if wrote_c:
        save_computers(computers)
    if wrote_p:
        save_parts(parts)
    if wrote_c or wrote_p:
        print(f"\nWrote {wrote_c} computer update(s), {wrote_p} new part(s). "
              "Review with git diff, then ./publish.sh.")
    else:
        print("\nNothing written.")


if __name__ == "__main__":
    main()
