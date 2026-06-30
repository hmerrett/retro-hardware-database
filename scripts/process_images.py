#!/usr/bin/env python3
"""Optimise photos in images/ so the repo stays small and pages load fast.

Drop a photo named after the asset (e.g. RH-0021.jpg) into images/computers/ or
images/parts/, then run this (publish.sh does it for you). It downsizes anything
larger than config.yml's enrich.image_max_px and converts to JPEG. Idempotent —
already-small JPEGs are left alone. Cropping is NOT needed: the website crops
thumbnails itself and shows the whole image on the item page.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES_DIR, load_config

SOURCE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def main():
    max_px = int((load_config().get("enrich") or {}).get("image_max_px", 1000))
    optimised = 0
    for sub in ("computers", "parts"):
        folder = IMAGES_DIR / sub
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            if f.name == ".gitkeep" or f.suffix.lower() not in SOURCE_EXTS:
                continue
            try:
                img = Image.open(f)
            except Exception as exc:
                print(f"  skip {f.name}: {exc}")
                continue
            too_big = max(img.size) > max_px
            not_jpeg = f.suffix.lower() not in (".jpg", ".jpeg")
            if not (too_big or not_jpeg):
                # already a reasonably-sized JPEG
                continue
            img = img.convert("RGB")
            if too_big:
                img.thumbnail((max_px, max_px))
            dest = f.with_suffix(".jpg")
            img.save(dest, "JPEG", quality=85)
            # converted from another format — drop the original
            if dest != f:
                try:
                    f.unlink()
                except OSError as exc:
                    print(f"  (couldn't remove {f.name}: {exc})")
            print(f"  optimised {f.name} -> {dest.name}  {img.size[0]}x{img.size[1]}")
            optimised += 1
    print(f"Images: {optimised} optimised.")


if __name__ == "__main__":
    main()
