#!/usr/bin/env python3
"""Generate print-ready labels (PDF) for any asset — a whole computer or an
individual part — with a QR code linking to that item's page on your GitHub
Pages site.

Two sizes:
  * full (default, 6x4 in)  — asset number, title and all the details.
  * small (--small, e.g. 19x51 mm) — just the QR, asset number and make/model.

All text uses the TTF set in config.yml (label.font_path, e.g. Audiowide); if
that file is missing the label falls back to Helvetica. Output is named after
the asset id(s) by default.

Usage:
    python scripts/make_labels.py                  # full labels, everything
    python scripts/make_labels.py RH-0002          # -> labels/RH-0002.pdf
    python scripts/make_labels.py --small RH-0002  # -> labels/RH-0002-small.pdf
    python scripts/make_labels.py --small          # small labels for everything
    python scripts/make_labels.py -o labels/x.pdf RH-0002
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


def register_fonts(config):
    rel = (config.get("label", {}) or {}).get("font_path", "")
    if rel:
        path = ROOT / rel
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("LabelFont", str(path)))
                print(f"  using label font: {rel}")
                return "LabelFont", "LabelFont"
            except Exception as exc:  # noqa: BLE001
                print(f"  note: could not load {rel} ({exc}) — using Helvetica.")
        else:
            print(f"  note: label font {rel} not found — using Helvetica. "
                  "Drop the TTF there to use it.")
    return "Helvetica-Bold", "Helvetica"


def page_size(lc):
    unit = inch if lc.get("units", "in") == "in" else mm
    return float(lc.get("width", 6)) * unit, float(lc.get("height", 4)) * unit


def default_filename(ids, suffix=""):
    if not ids:
        return f"labels{suffix}.pdf"
    if len(ids) == 1:
        return f"{ids[0]}{suffix}.pdf"
    if len(ids) <= 4:
        return "_".join(ids) + f"{suffix}.pdf"
    return f"{ids[0]}_and_{len(ids) - 1}_more{suffix}.pdf"


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


def render_label(c, W, H, asset_id, title, lines, url, qr_error, hfont, bfont):
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

    aid_size = fit_size(c, asset_id, hfont, 24, 12, text_w)
    y = H - margin - aid_size + 4
    c.setFont(hfont, aid_size)
    c.drawString(margin, y, asset_id)

    c.setFont(hfont, 12)
    for line in wrap_to_width(c, title, hfont, 12, text_w)[:2]:
        y -= 16
        c.drawString(margin, y, line)

    y -= 5
    bsize = 9
    for raw in lines:
        for i, line in enumerate(wrap_to_width(c, "• " + raw, bfont, bsize, text_w)[:2]):
            if y - 12 < bottom:
                break
            y -= 12
            c.setFont(bfont, bsize)
            c.drawString(margin if i == 0 else margin + 8, y,
                         line if i == 0 else "  " + line)
        if y - 12 < bottom:
            break

    qr_y = (H - qr_size) / 2 + 0.10 * inch
    c.drawImage(qr_reader(url, qr_error), qr_x, qr_y, width=qr_size, height=qr_size,
                preserveAspectRatio=True, mask="auto")
    c.setFont(bfont, 7.5)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 11, "scan for details")


def render_small_label(c, W, H, asset_id, title, url, qr_error, hfont, bfont):
    """Compact label: QR + asset number + make/model. Adapts to orientation."""
    m = 1.2 * mm
    c.setLineWidth(0.5)
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.rect(0.5 * mm, 0.5 * mm, W - 1.0 * mm, H - 1.0 * mm, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)

    if W >= H:  # landscape: QR left, text right
        qr = H - 2 * m
        c.drawImage(qr_reader(url, qr_error), m, m, width=qr, height=qr,
                    preserveAspectRatio=True, mask="auto")
        tx = m + qr + 1.5 * mm
        tw = W - tx - m
        aid_size = fit_size(c, asset_id, hfont, 11, 5, tw)
        y = H - m - aid_size
        c.setFont(hfont, aid_size)
        c.drawString(tx, y, asset_id)
        bsize = 6.5
        for line in wrap_to_width(c, title, bfont, bsize, tw)[:3]:
            if y - (bsize + 1.5) < m:
                break
            y -= bsize + 1.5
            c.setFont(bfont, bsize)
            c.drawString(tx, y, line)
    else:  # portrait: QR top, text below
        qr = W - 2 * m
        c.drawImage(qr_reader(url, qr_error), m, H - m - qr, width=qr, height=qr,
                    preserveAspectRatio=True, mask="auto")
        tw = W - 2 * m
        y = H - m - qr - 1.5 * mm
        aid_size = fit_size(c, asset_id, hfont, 10, 5, tw)
        y -= aid_size
        c.setFont(hfont, aid_size)
        c.drawCentredString(W / 2, y, asset_id)
        bsize = 6
        for line in wrap_to_width(c, title, bfont, bsize, tw)[:3]:
            if y - (bsize + 1.5) < m:
                break
            y -= bsize + 1.5
            c.setFont(bfont, bsize)
            c.drawCentredString(W / 2, y, line)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="asset_ids to print (default: all)")
    ap.add_argument("--small", action="store_true",
                    help="compact QR + number + make/model label (config: label_small)")
    ap.add_argument("-o", "--out", default=None,
                    help="output PDF path (default: named after the asset id(s))")
    args = ap.parse_args()

    config = load_config()
    computers = load_computers()
    parts = load_parts()
    comp_by_id = index_by_id(computers)
    part_by_id = index_by_id(parts)
    hfont, bfont = register_fonts(config)

    all_ids = sorted([c["asset_id"] for c in computers] + [p["asset_id"] for p in parts])
    ids = args.ids if args.ids else all_ids

    if args.small:
        lc = config.get("label_small") or {"width": 51, "height": 19, "units": "mm"}
    else:
        lc = config.get("label") or {}
    qr_error = lc.get("qr_error", "M")

    base_url = config.get("base_url") or ""
    if not base_url or "USERNAME" in base_url:
        print("WARNING: config.yml base_url still has a placeholder.")
        print("         QR codes will not resolve until you set it to your "
              "GitHub Pages URL.\n")

    W, H = page_size(lc)
    suffix = "-small" if args.small else ""
    out_path = Path(args.out) if args.out else ROOT / "labels" / default_filename(args.ids, suffix)
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
        if args.small:
            render_small_label(c, W, H, aid, title, item_url(config, aid),
                               qr_error, hfont, bfont)
        else:
            render_label(c, W, H, aid, title, lines, item_url(config, aid),
                         qr_error, hfont, bfont)
        c.showPage()
        printed += 1

    if printed == 0:
        print("No matching items — nothing written.")
        return
    c.save()
    print(f"Wrote {printed} {'small ' if args.small else ''}label(s) -> {out_path}")


if __name__ == "__main__":
    main()
