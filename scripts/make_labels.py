#!/usr/bin/env python3
"""Generate print-ready 6x4 labels (PDF) for any asset — a whole computer or an
individual part — with the asset number, key details and a QR code linking to
that item's page on your GitHub Pages site.

A computer's label summarises its build (CPU, RAM, video, sound, storage…)
pulled from its parts. A part's label shows its own specs.

Usage:
    python scripts/make_labels.py                  # every asset -> labels/labels.pdf
    python scripts/make_labels.py RH-0002 RH-0003  # only these
    python scripts/make_labels.py -o labels/486.pdf RH-0002
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import segno
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from common import (ROOT, display_name, index_by_id, item_url, load_computers,
                    load_config, load_parts, parse_specs, parts_for, type_label)

# For a computer label: which part types to surface, in order, and how to
# render each as one short line.
BUILD_ROWS = [
    ("cpu", "CPU"), ("ram", "Memory"), ("gpu", "Video"), ("sound", "Sound"),
    ("storage", "Storage"), ("network", "Network"), ("optical", "Optical"),
    ("floppy", "Floppy"),
]
SPEC_PICK = {"ram": "Size", "storage": "Capacity", "optical": "Media",
             "floppy": "Media"}


def page_size(config):
    lc = config.get("label", {})
    unit = inch if lc.get("units", "in") == "in" else mm
    return float(lc.get("width", 6)) * unit, float(lc.get("height", 4)) * unit


def qr_reader(data, error="M"):
    buf = io.BytesIO()
    segno.make(data, error=error.lower()).save(buf, kind="png", scale=10, border=1)
    buf.seek(0)
    return ImageReader(buf)


def wrap_to_width(c, text, font, size, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def computer_lines(comp, parts):
    """Short build-summary lines for a computer label."""
    lines = []
    if comp.get("os"):
        lines.append(f"OS: {comp['os']}")
    kids = parts_for(comp["asset_id"], parts)
    by_type = {}
    for p in kids:
        by_type.setdefault(p.get("type", ""), []).append(p)
    for ptype, label in BUILD_ROWS:
        if ptype not in by_type:
            continue
        members = by_type[ptype]
        if ptype in SPEC_PICK:
            specs = dict(parse_specs(members[0].get("specs", "")))
            value = specs.get(SPEC_PICK[ptype]) or display_name(members[0])
        else:
            value = " + ".join(display_name(m) for m in members)
        lines.append(f"{label}: {value}")
    if not kids:
        lines.append("No parts recorded")
    return lines


def part_lines(part):
    lines = [f"{k}: {v}" if k else v for k, v in parse_specs(part.get("specs", ""))]
    if part.get("computer_id"):
        lines.append(f"Installed in: {part['computer_id']}")
    return lines


def render_label(c, W, H, asset_id, title, sub_bits, lines, url, qr_error):
    margin = 0.22 * inch
    qr_size = min(H - 2 * margin, 2.1 * inch)
    qr_x = W - margin - qr_size
    text_w = qr_x - margin - 0.10 * inch
    bottom = margin + 0.16 * inch

    c.setLineWidth(1)
    c.setStrokeColorRGB(0.65, 0.65, 0.65)
    c.roundRect(0.10 * inch, 0.10 * inch, W - 0.20 * inch, H - 0.20 * inch,
                8, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)

    # Asset id (big)
    y = H - margin - 22
    c.setFont("Helvetica-Bold", 26)
    c.drawString(margin, y, asset_id)

    # Title (name), up to 2 lines
    c.setFont("Helvetica-Bold", 13)
    for line in wrap_to_width(c, title, "Helvetica-Bold", 13, text_w)[:2]:
        y -= 17
        c.drawString(margin, y, line)

    # subtitle bits
    bits = [b for b in sub_bits if b]
    if bits:
        c.setFont("Helvetica-Oblique", 9.5)
        y -= 14
        c.drawString(margin, y, "   ·   ".join(bits))

    # body lines (bulleted, wrapped)
    c.setFont("Helvetica", 9.5)
    y -= 6
    for raw in lines:
        for i, line in enumerate(wrap_to_width(c, "• " + raw, "Helvetica", 9.5, text_w)[:2]):
            if y - 12.5 < bottom:
                break
            y -= 12.5
            c.drawString(margin if i == 0 else margin + 8, y,
                         line if i == 0 else "  " + line)
        if y - 12.5 < bottom:
            break

    # QR
    qr_y = (H - qr_size) / 2 + 0.10 * inch
    c.drawImage(qr_reader(url, qr_error), qr_x, qr_y, width=qr_size, height=qr_size,
                preserveAspectRatio=True, mask="auto")
    c.setFont("Helvetica", 8)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 11, "scan for details")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ids", nargs="*", help="asset_ids to print (default: all)")
    ap.add_argument("-o", "--out", default=str(ROOT / "labels" / "labels.pdf"))
    args = ap.parse_args()

    config = load_config()
    computers = load_computers()
    parts = load_parts()
    comp_by_id = index_by_id(computers)
    part_by_id = index_by_id(parts)

    # Determine which assets to print, preserving id order.
    all_ids = [c["asset_id"] for c in computers] + [p["asset_id"] for p in parts]
    all_ids.sort()
    ids = args.ids if args.ids else all_ids

    qr_error = config.get("label", {}).get("qr_error", "M")
    base_url = config.get("base_url") or ""
    if not base_url or "USERNAME" in base_url:
        print("WARNING: config.yml base_url still has a placeholder.")
        print("         QR codes will not resolve until you set it to your "
              "GitHub Pages URL.\n")

    W, H = page_size(config)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=(W, H))

    printed = 0
    for aid in ids:
        if aid in comp_by_id:
            comp = comp_by_id[aid]
            title = display_name(comp)
            sub_bits = ["computer", comp.get("form_factor", ""), comp.get("year", "")]
            lines = computer_lines(comp, parts)
        elif aid in part_by_id:
            part = part_by_id[aid]
            title = display_name(part)
            sub_bits = [type_label(part.get("type", "")),
                        part.get("manufacturer", ""), part.get("year", "")]
            lines = part_lines(part)
        else:
            print(f"  ! unknown asset_id: {aid}")
            continue
        render_label(c, W, H, aid, title, sub_bits, lines,
                     item_url(config, aid), qr_error)
        c.showPage()
        printed += 1

    c.save()
    print(f"Wrote {printed} label(s) -> {out_path}")


if __name__ == "__main__":
    main()
