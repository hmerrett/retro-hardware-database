#!/usr/bin/env python3
"""Generate print-ready labels (PDF) for any asset — a whole computer or an
individual part — with a QR code linking to that item's page on your GitHub
Pages site.

Two sizes:
  * full (default, 6x4 in)  — asset number, title and all the details.
  * small (--small, e.g. 19x51 mm) — just the QR, asset number and make/model.

Automatic set (--auto): computers get BOTH sizes, any real (non-generic) part
gets the small one, generic filler gets none. `add.py` calls this on create/update.

All text uses the TTF set in config.yml (label.font_path, e.g. Audiowide); if
that file is missing the label falls back to Helvetica.

Usage:
    python scripts/make_labels.py                  # full labels, everything
    python scripts/make_labels.py RH-0002          # -> labels/RH-0002.pdf
    python scripts/make_labels.py --small RH-0002  # -> labels/RH-0002-small.pdf
    python scripts/make_labels.py --auto           # auto set for every device
    python scripts/make_labels.py --auto RH-0010   # auto set for one device
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

LABELS_DIR = ROOT / "labels"

BUILD_ROWS = [
    ("cpu", "CPU"), ("ram", "Memory"), ("gpu", "Video"), ("sound", "Sound"),
    ("storage", "Storage"), ("network", "Network"), ("optical", "Optical"),
    ("floppy", "Floppy"),
]
SPEC_PICK = {"ram": "Size", "storage": "Capacity", "optical": "Media",
             "floppy": "Media"}


def register_fonts(config, quiet=False):
    rel = (config.get("label", {}) or {}).get("font_path", "")
    if rel:
        path = ROOT / rel
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("LabelFont", str(path)))
                if not quiet:
                    print(f"  using label font: {rel}")
                return "LabelFont", "LabelFont"
            except Exception as exc:  # noqa: BLE001
                print(f"  note: could not load {rel} ({exc}) — using Helvetica.")
        elif not quiet:
            print(f"  note: label font {rel} not found — using Helvetica.")
    return "Helvetica-Bold", "Helvetica"


def page_size(lc):
    unit = inch if lc.get("units", "in") == "in" else mm
    return float(lc.get("width", 6)) * unit, float(lc.get("height", 4)) * unit


def label_geom(config, small):
    if small:
        lc = config.get("label_small") or {"width": 51, "height": 19, "units": "mm"}
    else:
        lc = config.get("label") or {}
    w, h = page_size(lc)
    return w, h, lc.get("qr_error", "M")


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


# --- shared content + drawing ----------------------------------------------

def asset_content(aid, comp_by_id, part_by_id, parts):
    """(title, lines) for an asset, or None if the id is unknown."""
    if aid in comp_by_id:
        c = comp_by_id[aid]
        return display_name(c), computer_lines(c, parts)
    if aid in part_by_id:
        p = part_by_id[aid]
        return display_name(p), part_lines(p)
    return None


def draw_one(c, W, H, aid, small, config, title, lines, qr_error, hfont, bfont):
    url = item_url(config, aid)
    if small:
        render_small_label(c, W, H, aid, title, url, qr_error, hfont, bfont)
    else:
        render_label(c, W, H, aid, title, lines, url, qr_error, hfont, bfont)
    c.showPage()


# --- automatic labels ------------------------------------------------------

def auto_plan(aid, comp_by_id, part_by_id):
    """Which labels a device gets: computers -> full + small; any real (non-
    generic) part -> small; generic filler -> none. Returns (suffix, small) list."""
    if aid in comp_by_id:
        return [("", False), ("-small", True)]
    p = part_by_id.get(aid)
    if p and p.get("manufacturer", "").strip().lower() not in ("", "generic"):
        return [("-small", True)]
    return []


def auto_labels(asset_ids, config=None, announce=True):
    """Write the automatic label set for the given assets (overwriting). Returns
    the list of files written."""
    config = config or load_config()
    computers, parts = load_computers(), load_parts()
    comp_by_id, part_by_id = index_by_id(computers), index_by_id(parts)
    hfont, bfont = register_fonts(config, quiet=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)

    written = []
    for aid in asset_ids:
        plan = auto_plan(aid, comp_by_id, part_by_id)
        if not plan:
            continue
        content = asset_content(aid, comp_by_id, part_by_id, parts)
        if not content:
            continue
        title, lines = content
        for suffix, small in plan:
            out = LABELS_DIR / f"{aid}{suffix}.pdf"
            W, H, qr = label_geom(config, small)
            c = canvas.Canvas(str(out), pagesize=(W, H))
            draw_one(c, W, H, aid, small, config, title, lines, qr, hfont, bfont)
            c.save()
            written.append(out)
    if announce and written:
        print("  labels: " + ", ".join(p.name for p in written))
    return written


def regenerate(asset_ids, config=None):
    """Auto-label the given assets, and any parent computers of changed parts
    (whose build summary may have changed). Returns files written."""
    pbi = index_by_id(load_parts())
    targets = set()
    for aid in asset_ids:
        targets.add(aid)
        p = pbi.get(aid)
        if p and p.get("computer_id"):
            targets.add(p["computer_id"])
    return auto_labels(sorted(targets), config)


def all_auto_ids():
    computers, parts = load_computers(), load_parts()
    return ([c["asset_id"] for c in computers]
            + [p["asset_id"] for p in parts
               if p.get("manufacturer", "").strip().lower() not in ("", "generic")])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="asset_ids to print (default: all)")
    ap.add_argument("--small", action="store_true",
                    help="compact QR + number + make/model label (config: label_small)")
    ap.add_argument("--auto", action="store_true",
                    help="auto set: computers full+small, real (non-generic) parts small")
    ap.add_argument("-o", "--out", default=None,
                    help="output PDF path (default: named after the asset id(s))")
    args = ap.parse_args()

    config = load_config()

    if args.auto:
        ids = args.ids if args.ids else all_auto_ids()
        written = auto_labels(ids, config, announce=False)
        print(f"Wrote {len(written)} label file(s) -> {LABELS_DIR}")
        return

    computers, parts = load_computers(), load_parts()
    comp_by_id, part_by_id = index_by_id(computers), index_by_id(parts)
    hfont, bfont = register_fonts(config)

    all_ids = sorted([c["asset_id"] for c in computers] + [p["asset_id"] for p in parts])
    ids = args.ids if args.ids else all_ids

    base_url = config.get("base_url") or ""
    if not base_url or "USERNAME" in base_url:
        print("WARNING: config.yml base_url still has a placeholder.")
        print("         QR codes will not resolve until you set it to your "
              "GitHub Pages URL.\n")

    small = args.small
    W, H, qr_error = label_geom(config, small)
    suffix = "-small" if small else ""
    out_path = Path(args.out) if args.out else LABELS_DIR / default_filename(args.ids, suffix)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=(W, H))

    printed = 0
    for aid in ids:
        content = asset_content(aid, comp_by_id, part_by_id, parts)
        if not content:
            print(f"  ! unknown asset_id: {aid}")
            continue
        title, lines = content
        draw_one(c, W, H, aid, small, config, title, lines, qr_error, hfont, bfont)
        printed += 1

    if printed == 0:
        print("No matching items — nothing written.")
        return
    c.save()
    print(f"Wrote {printed} {'small ' if small else ''}label(s) -> {out_path}")


if __name__ == "__main__":
    main()
