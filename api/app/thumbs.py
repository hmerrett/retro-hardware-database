"""Smaller copies of the photographs, made once and kept.

Every photograph here came off a phone, which means two to seven megabytes and
three to five thousand pixels across. The gallery draws them into cards a couple
of hundred pixels wide, and until this existed it drew them from the originals:
403 photographs and 265 MB of them on one page, to fill a space that needs about
nine. A card-sized copy of the same photograph is 21 KB.

So the same trick the watermark cache already plays. A request for a width makes
the copy if it is not there, writes it under the cache directory, and serves it;
every later request finds it made. Nothing is generated ahead of being asked for,
except by warm() below, and nothing is thrown away when it could be reused --
the copy is rebuilt only when the photograph behind it changes.

    served_path(rel, 400)      the path to serve, made if need be
    forget(rel)                drop a photograph's copies (it was deleted, or moved)
    warm(rels)                 make them all now, rather than on the first visit

Three rules that matter:

  * Only the widths in WIDTHS are made. The width arrives in a URL, and a URL a
    stranger can put any number in is a URL that fills the disk with nine hundred
    copies of the same photograph.
  * A photograph already smaller than the width asked for is served as it is.
    Blowing a 320px scan up to 800px would cost bytes to lose detail.
  * The copy is made from whatever the site would otherwise serve -- the
    watermarked version where there is one -- so the mark survives the resize and
    scales with it.

The originals are still there and still served: the lightbox opens one, which is
the whole point of having a 24-megapixel photograph of a motherboard.
"""
from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

# What the templates may ask for, and why each one is there. The card in the
# gallery measures 229px on every desktop width (the page is capped at 1000px) and
# 364px on a phone; the strip of small ones on an item page is 150px; the main
# photograph on an item page gets around 620px.
#
#   300   a card, and a strip thumbnail at 2x
#   500   a card on a retina screen, which is every phone and most laptops
#   800   a card filling the width of a phone at 2x
#  1200   the main photograph on an item page, at 2x
#
# The gaps matter as much as the sizes. A ladder of 400 and 800 sounds sensible and
# is not: a 229px card on a retina screen needs 458, finds nothing between 400 and
# 800, and takes the 800 -- four times the pixels it can show. Measured on the live
# gallery that was 10.7 MB of photographs where 4 would do.
WIDTHS = (300, 500, 800, 1200)

# JPEG quality for the copies. 80 is where a photograph of a circuit board stops
# looking any better and the file carries on getting larger.
QUALITY = 80

# Bumped when something about how these are made changes, so old copies are missed
# rather than served -- the same reasoning as the watermark cache's directory name,
# which learned it the hard way twice. 3: these are made from the watermarked copy,
# and every one of those made before photographs were written atomically may have
# been composited from a photograph a crop was half way through writing. A fragment
# of a JPEG decodes to a picture rather than to an error, so a bad copy cannot be
# told from a good one; they all go and are made again.
BUILD = 3


def cache_dir(images_dir: Path) -> Path:
    return Path(images_dir) / ".sized" / f"q{QUALITY}-b{BUILD}"


def sweep(images_dir: Path):
    """Drop copies made by an older build of this module."""
    keep = cache_dir(images_dir)
    with contextlib.suppress(OSError):
        keep.mkdir(parents=True, exist_ok=True)
        for stale in keep.parent.iterdir():
            if stale.is_dir() and stale != keep:
                shutil.rmtree(stale, ignore_errors=True)


def _make(src: Path, dst: Path, width: int) -> bool:
    """Write a copy of `src` no wider than `width`. False if the source is already
    that small, which is not a failure -- it means serve the source."""
    from PIL import Image
    with Image.open(src) as im:
        if im.width <= width:
            return False
        im = im.convert("RGB") if im.mode in ("RGBA", "P", "LA") else im
        im.thumbnail((width, width), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        # Written aside and moved into place, so a second request arriving while
        # this one is still encoding never reads a half-written file.
        im.save(tmp, "JPEG", quality=QUALITY, optimize=True)
        tmp.replace(dst)
    return True


def served_path(images_dir: Path, rel: str, width, source: Path) -> Path:
    """The path to serve for one photograph at one width: the cached copy, made now
    if it is missing or older than the photograph behind it. Falls back to `source`
    for a width nobody asked to support, a photograph already smaller than that, or
    anything at all going wrong -- a slow, large photograph beats a broken one."""
    if width not in WIDTHS:
        return source
    dst = cache_dir(images_dir) / str(width) / rel
    # .jpg whatever the original was: these are photographs, and a PNG of one is
    # several times the size for no gain.
    dst = dst.with_suffix(".jpg")
    try:
        # Read before the copy is made and stamped onto it after, so a copy says
        # which version of the photograph it was made from rather than when it
        # happened to finish. A photograph replaced while this was encoding would
        # otherwise leave a copy of the old one dated later than the new original,
        # and it would look fresh forever. (main._watermarked_file does the same.)
        stamp = source.stat().st_mtime
        if dst.exists() and dst.stat().st_mtime >= stamp:
            return dst
        if not _make(source, dst, width):
            return source
        with contextlib.suppress(OSError):
            os.utime(dst, (stamp, stamp))
        return dst
    except Exception:
        return source


def forget(images_dir: Path, rel: str):
    """Drop every copy of one photograph, for when it is deleted or replaced."""
    for width in WIDTHS:
        with contextlib.suppress(OSError):
            (cache_dir(images_dir) / str(width) / rel).with_suffix(".jpg").unlink(
                missing_ok=True)


def warm(images_dir: Path, pairs, widths=WIDTHS, log=None):
    """Make the copies for a list of (rel, source path) now.

    Generating on demand means whoever opens the gallery first after a deploy pays
    for four hundred photographs at once. This is what the deploy runs instead.
    Returns (copies now on disk, photographs too small to need one).
    """
    made = small = 0
    for rel, source in pairs:
        for width in widths:
            if served_path(images_dir, rel, width, source) == source:
                small += 1
            else:
                made += 1
        if log:
            log(rel)
    return made, small


def _main(argv=None):
    """`python -m app.thumbs` -- make every copy the site will ask for.

    Run after a deploy, and after a bulk import: otherwise whoever opens the
    gallery first waits while four hundred photographs are resized, and every one
    of those resizes competes with the page they are waiting for.
    """
    import argparse
    import os
    import sys
    import time

    args = argparse.ArgumentParser(description=_main.__doc__.splitlines()[0])
    args.add_argument("--images", default=os.getenv("RHDB_IMAGES_DIR", "/app/images"))
    args.add_argument("--quiet", action="store_true")
    opts = args.parse_args(argv)

    root = Path(opts.images)
    sweep(root)
    # The originals only: not the watermark cache, not our own copies, not the
    # reference-marker sidecars.
    rels = sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.is_file() and not any(s.startswith(".") for s in
                                             p.relative_to(root).parts)
                  and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not rels:
        print("no photographs found under", root)
        return 0

    # Made from what the site would serve, which for a photograph of this
    # collection means the watermarked copy. Imported here so the module stays
    # importable without the app.
    from .main import IMAGES_DIR, _is_own_photo, _watermarked_file
    started = time.time()
    made, small = warm(
        IMAGES_DIR, [(rel, _watermarked_file(rel) if _is_own_photo(rel)
                      else IMAGES_DIR / rel) for rel in rels],
        log=None if opts.quiet else lambda rel: print(rel, file=sys.stderr))
    took = time.time() - started
    print(f"{len(rels)} photographs, {made} copies ready, {small} already small"
          f" enough, in {took:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
