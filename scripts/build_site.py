#!/usr/bin/env python3
"""Build the static website from the two CSVs into ./site/.

Every computer and every part gets a page at  site/items/<asset_id>/index.html
so the QR codes (which encode <base_url>/items/<asset_id>/) resolve uniformly,
whatever the item is. A computer's page lists its parts; a part's page links
back to the computer it's installed in.

Usage:
    python scripts/build_site.py
"""
from __future__ import annotations

import shutil
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common import (IMAGES_DIR, ROOT, TYPE_ORDER, display_name, index_by_id,
                    load_computers, load_config, load_parts, parse_specs,
                    parts_for, placeholder_for, type_label, type_sort_key,
                    validate)

TEMPLATES_DIR = ROOT / "templates"
SITE_DIR = ROOT / "site"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def detect_image(kind, asset_id):
    """Find a photo dropped in by hand as images/<kind>/<asset_id>.<ext>
    (so you don't have to edit the CSV). kind is 'computers' or 'parts'."""
    folder = IMAGES_DIR / kind
    for ext in IMAGE_EXTS:
        f = folder / f"{asset_id}{ext}"
        if f.exists():
            return f"{kind}/{f.name}"
    return ""


def build():
    config = load_config()
    computers = load_computers()
    parts = load_parts()

    warnings = validate(computers, parts)
    for w in warnings:
        print(f"  ! {w}", file=sys.stderr)
    if warnings:
        print(f"  ({len(warnings)} integrity warning(s) above — building anyway)\n",
              file=sys.stderr)

    # Derived fields.
    for c in computers:
        c["display_name"] = display_name(c)
        c["placeholder"] = placeholder_for("computer")
        if not c.get("image"):
            c["image"] = detect_image("computers", c["asset_id"])
    computers_by_id = index_by_id(computers)

    for p in parts:
        p["display_name"] = display_name(p)
        p["type_label"] = type_label(p.get("type", ""))
        p["spec_pairs"] = parse_specs(p.get("specs", ""))
        p["parent"] = computers_by_id.get(p.get("computer_id", "")) or None
        p["placeholder"] = placeholder_for(p.get("type", ""))
        if not p.get("image"):
            p["image"] = detect_image("parts", p["asset_id"])
    for c in computers:
        c["parts"] = parts_for(c["asset_id"], parts)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    # Fresh output.
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True)
    if IMAGES_DIR.exists():
        shutil.copytree(IMAGES_DIR, SITE_DIR / "images",
                        ignore=shutil.ignore_patterns(".gitkeep"))
    placeholders = ROOT / "assets" / "placeholders"
    if placeholders.exists():
        shutil.copytree(placeholders, SITE_DIR / "placeholders")

    # --- index: unified list of computers + parts ---
    assets = []
    for c in computers:
        assets.append({
            "asset_id": c["asset_id"], "cat": "computer", "cat_label": "Computer",
            "display_name": c["display_name"], "image": c.get("image", ""),
            "year": c.get("year", ""), "parent": "", "generic": False,
            "placeholder": c["placeholder"],
            "search_text": " ".join([c["display_name"], c.get("manufacturer", ""),
                                     c.get("model", ""), c.get("os", ""),
                                     c["asset_id"]]).lower(),
        })
    for p in parts:
        assets.append({
            "asset_id": p["asset_id"], "cat": p.get("type", "other"),
            "cat_label": p["type_label"], "display_name": p["display_name"],
            "image": p.get("image", ""), "year": p.get("year", ""),
            "parent": p.get("computer_id", ""),
            "generic": (p.get("manufacturer", "").strip().lower() == "generic"),
            "placeholder": p["placeholder"],
            "search_text": " ".join([p["display_name"], p.get("manufacturer", ""),
                                     p.get("model", ""), p.get("specs", ""),
                                     p.get("type", ""), p["asset_id"]]).lower(),
        })
    assets.sort(key=lambda a: a["asset_id"])

    present_types = {p.get("type", "other") for p in parts}
    categories = [{"key": "computer", "label": "Computers"}]
    for t in sorted(present_types, key=type_sort_key):
        categories.append({"key": t, "label": type_label(t) + "s"})

    (SITE_DIR / "index.html").write_text(
        env.get_template("index.html").render(
            config=config, assets=assets, categories=categories, root=""),
        encoding="utf-8")

    # --- one page per computer and per part ---
    comp_tpl = env.get_template("computer.html")
    for c in computers:
        out = SITE_DIR / "items" / c["asset_id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            comp_tpl.render(config=config, c=c, root="../../"), encoding="utf-8")

    part_tpl = env.get_template("part.html")
    for p in parts:
        out = SITE_DIR / "items" / p["asset_id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            part_tpl.render(config=config, p=p, root="../../"), encoding="utf-8")

    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built {len(computers)} computer page(s) + {len(parts)} part page(s) "
          f"-> {SITE_DIR}")
    print("Open site/index.html in a browser to preview.")


if __name__ == "__main__":
    build()
