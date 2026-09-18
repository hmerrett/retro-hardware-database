"""The share card for a page that is a wall of photographs (ADR-0017).

An item's link previews as the item, because an item has a photograph. The gallery,
a `/browse` slice, a search on either and the projects list have no single
photograph to be *the* photograph, so they previewed as the logo -- which made a
link to a search for "sound blaster" look like every other link to the site. This
module makes the picture those pages preview as: up to four of the photographs
actually on the page, tiled into one 1200x630 card.

Open Graph takes one image, which is why the tiling has to happen here and not in a
template. What it does *not* do is read a query: a card is named by a hash of the
photographs it is made of, so `/og/{name}` opens a file by hash and never searches,
and two queries landing on the same four machines are one card. The page that names
a card is what makes it, on a miss, from rows it has already loaded.

The resized-copy cache in thumbs.py is deliberately not used. It is keyed on the
photograph and the width and holds the watermarked copy the pages ask for; tiles
are cut from the photographs themselves so the card can be marked once rather than
four times, and a second writer with a different idea of what belongs under that
key would quietly serve the wrong thing on the item pages.
"""

import contextlib
import hashlib
import logging
import os
import re
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .common import IMAGES_DIR
from .photos import WATERMARK, WM_MARGIN, WM_MIN_PX, WM_OPACITY, WM_SCALE, WM_SRC
from .thumbs import _write_atomically

if TYPE_CHECKING:
    # Pillow is opened where it is used, as it is everywhere else here: importing it
    # costs more than this module does.
    from PIL.Image import Image as PilImage

log = logging.getLogger(__name__)

# The 1.91:1 slot every site that shows one of these wants, and the cream the site's
# own card is on (tools/make_icons.py, which says why cream and not white).
SIZE = (1200, 630)
CARD_BG = (244, 240, 226)

# A gutter wide enough to read as a gap at the width a chat client renders a
# preview, which is nearer 500px than 1200.
GUTTER = 12

# Four, because a fifth photograph stops being a photograph at that width. It is
# also what keeps the card of a long result list as cheap as the card of a short
# one: only the first four are ever opened.
MAX_TILES = 4

QUALITY = 82

# Cards kept. A query string is an unbounded key space even when the photographs
# behind it are not, and this cache is filled by an anonymous route.
CAP = 500

# Bumped when something about how these are made changes, so old cards are missed
# rather than served -- the lesson the watermark cache learned twice. The directory
# is named after it for the same reason.
BUILD = 1

# The only shape a card's name has. Nothing else is looked up, so the route that
# serves one has no path in it to traverse.
NAME = re.compile(r"[0-9a-f]{16}\.jpg")


def cache_dir() -> Path:
    return IMAGES_DIR / ".og" / f"b{BUILD}"


def sweep() -> None:
    """Drop cards made by an older build of this module."""
    keep = cache_dir()
    with contextlib.suppress(OSError):
        keep.mkdir(parents=True, exist_ok=True)
        for stale in keep.parent.iterdir():
            if stale.is_dir() and stale != keep:
                shutil.rmtree(stale, ignore_errors=True)


sweep()


def _source(rel: str) -> Path | None:
    """The photograph behind one of a page's image paths, or None if it is not one.

    A row with no photograph carries "", and a project's members hand back a
    placeholder drawing for a thing nobody has been round with a camera for -- an
    outline of a computer reads as a broken image in a preview, which is worse than
    the site's own card. Both are refused here rather than at each caller.
    """
    if not rel or "/placeholders/" in rel:
        return None
    # Callers pass paths relative to the image folder. Anything that could leave it
    # is not one of ours, whatever it turns out to name.
    if rel.startswith("/") or any(seg in ("", ".", "..") for seg in rel.split("/")):
        return None
    path = (IMAGES_DIR / rel).resolve()
    if not str(path).startswith(str(IMAGES_DIR.resolve()) + os.sep):
        return None
    return path if path.is_file() else None


def photographs(rels: Iterable[str], limit: int = MAX_TILES) -> list[tuple[str, Path]]:
    """The first few real photographs among a page's image paths, as (rel, path)."""
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for rel in rels or ():
        if rel in seen:
            continue
        seen.add(rel)
        if (path := _source(rel)) is not None:
            out.append((rel, path))
            if len(out) == limit:
                break
    return out


def _tiles(n: int) -> list[tuple[int, int, int, int]]:
    """Where each photograph goes, for n of them: (x, y, width, height) in reading
    order. Fewer than four fill the space rather than leaving a hole in it."""
    w, h = SIZE
    half_w, half_h = (w - GUTTER) // 2, (h - GUTTER) // 2
    right, lower = w - half_w, h - half_h
    if n == 1:
        return [(0, 0, w, h)]
    if n == 2:
        return [(0, 0, half_w, h), (right, 0, half_w, h)]
    if n == 3:
        return [(0, 0, half_w, h), (right, 0, half_w, half_h), (right, lower, half_w, half_h)]
    return [
        (0, 0, half_w, half_h),
        (right, 0, half_w, half_h),
        (0, lower, half_w, half_h),
        (right, lower, half_w, half_h),
    ]


def _tile(path: Path, box_w: int, box_h: int) -> "PilImage":
    """One photograph cropped to fill one tile. Filled, not letterboxed: bands of
    cream inside a montage read as a broken image rather than as a tall photo."""
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        # JPEG decoding at a fraction of full size, which is most of what this costs
        # -- a phone photograph is 5712px wide and the tile it is going into is 594.
        # Twice the tile, so the LANCZOS resize below still has pixels to work with.
        im.draft("RGB", (box_w * 2, box_h * 2))
        # Upright, as the photograph is served: one lying on its side and saying so
        # only in its EXIF block would otherwise be tiled on its side.
        upright = ImageOps.exif_transpose(im) or im
        return ImageOps.fit(upright.convert("RGB"), (box_w, box_h), Image.Resampling.LANCZOS)


def _stamp(card: "PilImage") -> None:
    """The site's mark in the card's own corner, at the card's scale.

    Once, not once per tile: the tiles come from the photographs rather than from
    the watermarked copies precisely so that a montage carries one mark instead of
    four, each cropped to wherever its tile's corner happened to fall.

    A card without a mark beats no card, so a missing or unreadable logo is logged
    and stepped over -- an installation supplies its own branding (ADR-0011).
    """
    if not WATERMARK:
        return
    try:
        from PIL import Image

        mark = Image.open(WM_SRC).convert("RGBA")
        target = max(WM_MIN_PX, int(min(card.size) * WM_SCALE))
        mark.thumbnail((target, target), Image.Resampling.LANCZOS)
        mark.putalpha(mark.getchannel("A").point(lambda a: int(a * WM_OPACITY)))
        margin = max(6, int(min(card.size) * WM_MARGIN))
        card.paste(
            mark, (card.width - mark.width - margin, card.height - mark.height - margin), mark
        )
    except Exception:
        log.warning("share card made without the site's mark", exc_info=True)


def _key(found: Sequence[tuple[str, Path]]) -> str:
    """A card's name: what went into it, hashed.

    The photographs and their modification times, so a crop is a new name rather
    than something that has to be invalidated -- the bargain img_url's ?v= stamp
    already makes, and what lets a card be served immutable for a year. The numbers
    that decide how a card is drawn are in here too, so changing one of them is
    also a new name.
    """
    h = hashlib.sha256()
    h.update(f"b{BUILD}|{SIZE}|{GUTTER}|q{QUALITY}|w{int(WATERMARK)}".encode())
    for rel, path in found:
        h.update(f"|{rel}|{path.stat().st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def _build(found: Sequence[tuple[str, Path]], dst: Path) -> None:
    from PIL import Image

    card = Image.new("RGB", SIZE, CARD_BG)
    for (_rel, path), (x, y, w, h) in zip(found, _tiles(len(found)), strict=True):
        card.paste(_tile(path, w, h), (x, y))
    _stamp(card)
    # Full chroma. A card is flat cream meeting photographs along hard straight
    # edges, and 4:2:0 smears a saturated tile across the gutter beside it -- the
    # one artefact this picture is shaped to show off.
    _write_atomically(
        dst, lambda tmp: card.save(tmp, "JPEG", quality=QUALITY, subsampling=0, optimize=True)
    )


def _prune() -> None:
    """Keep the newest CAP cards. Only ever runs after a miss, so the cost sits with
    whoever is filling the cache rather than with every reader."""
    with contextlib.suppress(OSError):
        kept = sorted(cache_dir().glob("*.jpg"), key=lambda p: p.stat().st_mtime_ns)
        for stale in kept[: max(0, len(kept) - CAP)]:
            with contextlib.suppress(OSError):
                stale.unlink()


def montage(rels: Iterable[str]) -> tuple[str, int, int] | None:
    """The share card for a page showing these photographs, as (path, width,
    height), or None to fall back to the site's own card.

    `rels` is whatever the page is showing, in the order it shows it -- a generator
    off the rows is fine, since only the first few that are photographs are opened.
    None means there were none, which is the case SITE_CARD was added for.
    """
    found = photographs(rels)
    if not found:
        return None
    try:
        key = _key(found)
    except OSError:
        # A photograph deleted between the page reading the folder and this looking
        # at it. The site card is the right answer to "no photographs".
        return None
    dst = cache_dir() / f"{key}.jpg"
    if not dst.exists():
        try:
            _build(found, dst)
        except Exception:
            log.warning(
                "could not make a share card from %s", [rel for rel, _ in found], exc_info=True
            )
            return None
        _prune()
    return (f"/og/{key}.jpg", *SIZE)


def card_file(name: str) -> Path | None:
    """The card by that name, or None. A name is one of this module's own hashes and
    nothing else, so there is no path here for a caller to traverse."""
    if not NAME.fullmatch(name or ""):
        return None
    path = cache_dir() / name
    return path if path.is_file() else None
