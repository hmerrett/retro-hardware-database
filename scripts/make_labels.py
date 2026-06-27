#!/usr/bin/env python3
"""Generate print-ready 6x4 labels (PDF) for any asset — a whole computer or an
individual part — with the asset number, labelled details and a QR code linking
to that item's page on your GitHub Pages site.

A computer's label lists its own attributes (year, form factor, chassis, OS)
and a build summary (CPU, RAM, video, sound, storage…) pulled from its parts.
A part's label shows its type, maker and specs.

The asset number + title use the TTF set in config.yml (label.font_path, e.g.
Audiowide); if that file is missing they fall back to Helvetica. Output is named
after the asset id(s) by default (RH-0002.pdf, or labels.pdf for everything).

Usage:
    python scripts/make_labels.py                  # every asset -> labels/labels.pdf
    python scripts/make_labels.py RH-0002          # -> labels/RH-0002.pdf
    python scripts/make_labels.py RH-0002 RH-0003  # -> labels/RH-0002_RH-0003.pdf
    python scripts/make_labels.py -o labels/486.pdf RH-0002
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import segno
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from common import (ROOT, display_name, index_by_id, item_url, load_computers,
                    load_config, load_parts, parse_specs, parts_for, type_label)

BUILD_ROWS = [
    ("cpu", "CPU"), ("ram", "Memory"), ("gpu", "Video"), ("sound", "Sound"),
    ("storage", "Storage"), ("network", "Network"), ("optical", "Optical"),
    ("floppy", "Floppy"),
]
SPEC_PICK = {"ram": "Size", "storage": "Capacity", "optical": "Media",
             "floppy": "Media"}

BODY_FONT = "Helvetica"          # spec/body lines (legibility)
FALLBACK_HEADLINE = "Helvetica-Bold"


def register_headline_font(config):
    """Register the configured TTF for the asset number + title. Returns the
    font name to use (the custom one, or Helvetica-Bold if unavailable)."""
    rel = (config.get("label", {}) or {}).get("font_path", "")
    if not rel:
        return FALLBACK_HEADLINE
    path = ROOT / rel
    if not path.exists():
        print(f"  note: label font {rel} not found — using Helvetica. "
              "Drop the TTF there and re-run to use it.")
        return FALLBACK_HEADLINE
    try:
        pdfmetrics.registerFont(TTFont("LabelHeadline", str(path)))
        print(f"  using label font: {rel}")
        return "LabelHeadline"
    except Exception as exc:  # noqa: BLE001
        print(f"  note: could not load {rel} ({exc}) — using Helvetica.")
        return FALLBACK_HEADLINE


def page_size(config):
    lc = config.get("label", {})
    unit = inch if lc.get("units", "in") == "in" else mm
    return float(lc.get("width", 6)) * unit, float(lc.get("height", 4)) * unit


def default_filename(ids):
    if not ids:
        return "labels.pdf"
    if len(ids) == 1:
        return f"{ids[0]}.pdf"
    if len(ids) <= 4:
        return "_".join(ids) + ".pdf"
    return f"{ids[0]}_and_{len(ids) - 1}_more.pdf"


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


def fit_size(c, text, font, start, min_size, max_w):
    size = start
    while size > min_size and c.stringWidth(text, font, size) > max_w:
        size -= 1
    return size


def computer_lines(comp, parts):
    lines = ["Type: Computer"]
    for label, key in (("Manufacturer", "manufacturer"), ("Year", "year"),
                       ("Form factor", "form_factor"), ("Chassis", "chassis"),
                       ("OS", "os")):
        if comp.get(key):
            lines.append(f"{label}: {comp[key]}")

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

    if comp.get("condition"):
        lines.append(f"Condition: {comp['condition']}")
    return lines


def part_lines(part):
    lines = [f"Type: {type_label(part.get('type', ''))}"]
    for label, key in (("Manufacturer", "manufacturer"), ("Year", "year")):
        if part.get(key):
            lines.append(f"{label}: {part[key]}")
    lines += [f"{k}: {v}" if k else v for k, v in parse_specs(part.get("specs", ""))]
    if part.get("computer_id"):
        lines.append(f"Installed in: {part['computer_id']}")
    if part.get("condition"):
        lines.append(f"Condition: {part['condition']}")
    return lines


def render_label(c, W, H, asset_id, title, lines, url, qr_error, headline_font):
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

    # Asset id (display font, shrunk to fit the text column).
    aid_size = fit_size(c, asset_id, headline_font, 26, 12, text_w)
    y = H - margin - aid_size + 4
    c.setFont(headline_font, aid_size)
    c.drawString(margin, y, asset_id)

    # Title (display font, up to 2 wrapped lines).
    c.setFont(headline_font, 13)
    for line in wrap_to_width(c, title, headline_font, 13, text_w)[:2]:
        y -= 17
        c.drawString(margin, y, line)

    # Body / specs (plain font for legibility).
    y -= 4
    c.setFont(BODY_FONT, 9.5)
    for raw in lines:
        for i, line in enumerate(wrap_to_width(c, "• " + raw, BODY_FONT, 9.5, text_w)[:2]):
            if y - 12.5 < bottom:
                break
            y -= 12.5
            c.drawString(margin if i == 0 else margin + 8, y,
                         line if i == 0 else "  " + line)
        if y - 12.5 < bottom:
            break

    qr_y = (H - qr_size) / 2 + 0.10 * inch
    c.drawImage(qr_reader(url, qr_error), qr_x, qr_y, width=qr_size, height=qr_size,
                preserveAspectRatio=True, mask="auto")
    c.setFont(BODY_FONT, 8)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 11, "scan for details")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="asset_ids to print (default: all)")
    ap.add_argument("-o", "--out", default=None,
                    help="output PDF path (default: named after the asset id(s))")
    args = ap.parse_args()

    config = load_config()
    computers = load_computers()
    parts = load_parts()
    comp_by_id = index_by_id(computers)
    part_by_id = index_by_id(parts)
    headline_font = register_headline_font(config)

    all_ids = sorted([c["asset_id"] for c in computers] + [p["asset_id"] for p in parts])
    ids = args.ids if args.ids else all_ids

    qr_error = config.get("label", {}).get("qr_error", "M")
    base_url = config.get("base_url") or ""
    if not base_url or "USERNAME" in base_url:
        print("WARNING: config.yml base_url still has a placeholder.")
        print("         QR codes will not resolve until you set it to your "
              "GitHub Pages URL.\n")

    W, H = page_size(config)
    out_path = Path(args.out) if args.out else ROOT / "labels" / default_filename(args.ids)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=(W, H))

    printed = 0
    for aid in ids:
        if aid in comp_by_id:
            comp = comp_by_id[aid]
            title, lines = display_name(comp), computer_lines(comp, parts)
        elif aid in part_by_id:
            part = part_by_id[aid]
            title, lines = display_name(part), part_lines(part)
        else:
            print(f"  ! unknown asset_id: {aid}")
            continue
        render_label(c, W, H, aid, title, lines, item_url(config, aid), qr_error, headline_font)
        c.showPage()
        printed += 1

    if printed == 0:
        print("No matching items — nothing written.")
        return
    c.save()
    print(f"Wrote {printed} label(s) -> {out_path}")


if __name__ == "__main__":
    main()
