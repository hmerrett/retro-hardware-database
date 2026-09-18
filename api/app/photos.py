"""Photo and image helpers: watermarking, upload and content-verification,
reference photos and their cached favicons, the kept-original/revert
machinery, and the crop/rotate/tuneup edit operations.

Lifted out of main.py so the register's image handling -- everything from a
raw upload to the watermarked, cached copy a page actually serves -- is one
cohesive module rather than scattered through the largest file in the app.
Routes, the change-log helpers (`add_log`, `get_or_404`) and the photo-edit
orchestrators stay in main: this module only ever touches the filesystem and
the photo/log-photo rows, never the log itself.
"""

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from . import enrich, entry, thumbs
from .common import IMAGES_DIR, IMAGE_EXTS, branded, _file_ver, folder_images
from .models import LogEntry, LogPhoto


def _image_size(image_rel: str):
    """(width, height) of a stored image, or None. Lets link previews (Discord
    especially) render the large image immediately without a probe fetch."""
    try:
        from PIL import Image, ImageOps

        with Image.open(IMAGES_DIR / image_rel) as im:
            # As served, which is upright: a photo lying on its side in the file
            # would otherwise be announced to a preview the wrong way round.
            return ImageOps.exif_transpose(im).size
    except Exception:
        return None


# Pillow's format names for those extensions, so an upload can be checked for what
# it actually is rather than only for what it is named.
#
# MPO is on the list because a phone camera puts one out and calls it .jpg. A
# Multi-Picture Object is a JPEG with a second image appended -- what a portrait or
# HDR shot writes -- and every viewer, this site included, shows the first frame and
# ignores the rest. Pillow reports the format as MPO, so a photograph uploaded
# straight off a phone was refused as "unsupported image type: MPO", which is the
# one source most photographs here come from. Nothing else changes: it is stored as
# it arrived, and the edit path re-encodes a rotated or cropped copy as an ordinary
# single-frame JPEG, which is what one image is.
IMAGE_FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "GIF"}

# The three folders photographs live in, and why the third is not one of the first
# two. A folder under here is read by filename: everything in computers/ whose stem
# is an asset id belongs to that asset, and the first of them is its portrait. That
# is exactly what a photograph hung on a history entry must not be -- a picture of
# a recap is not a picture of the part -- so it is filed under the entry's own id
# in a folder nothing scans by asset id. See models.LogPhoto.
LOG_KIND = "log"


# Our own photos are served with a small RHDB watermark composited in a corner,
# so shared/saved copies carry attribution. Originals on disk are never altered;
# the watermarked version is cached next to a mtime check. Reference (not-ours)
# images and favicons are served untouched. Toggle with RHDB_WATERMARK=0.
WATERMARK = os.getenv("RHDB_WATERMARK", "1").lower() not in ("0", "false", "no", "off")
# The logo at its own proportions (tools/make_icons.py writes it), not the squared
# app icon: a mark letterbox-padded inside a square would sit on the photo smaller
# than the numbers below ask for. Falls back to the square icon if it is missing.
WM_SRC = branded("logo-512.png")
if not WM_SRC.exists():
    WM_SRC = branded("icon-512.png")

# A proportion of the photo's short edge, so the mark stays legible on a 5712px
# photo and unobtrusive on a small one, with a floor for the very small.
WM_SCALE = 0.216
WM_MIN_PX = 41
WM_OPACITY = 0.55
WM_MARGIN = 0.03
# Bumped when the compositing itself changes rather than the numbers above, so the
# cache misses and every copy is rebuilt. 2: EXIF orientation is baked in, which
# every photo cached before it was is missing. 3: every copy made before photographs
# were written atomically may have been composited from a fragment of one -- a
# photograph half-written by a crop happening at that moment -- and a fragment
# decodes to a picture that is half grey rather than to an error. Nothing can tell
# those copies from the good ones by looking at them, so they all go.
WM_BUILD = 3

# The cache lives under a directory named after those numbers, and after the mark
# itself. A cached copy is otherwise only rebuilt when its source photo changes, so
# changing the size here left every existing watermark at the old one until its
# photo was next edited -- twice now. Naming the directory after what went into it
# means a change simply misses the old cache instead of needing anyone to remember;
# the artwork's hash is in there because a new site icon is a new watermark, and
# every photo already served carries the old one.
WM_CACHE = (
    IMAGES_DIR / ".wm" / f"s{WM_SCALE}-m{WM_MIN_PX}-o{WM_OPACITY}-b{WM_BUILD}-i{_file_ver(WM_SRC)}"
)

if WATERMARK:
    WM_CACHE.mkdir(parents=True, exist_ok=True)
    for stale in WM_CACHE.parent.iterdir():
        if stale.is_dir() and stale != WM_CACHE:
            shutil.rmtree(stale, ignore_errors=True)

# The resized copies keep their own cache beside it, swept the same way.
thumbs.sweep(IMAGES_DIR)


def _write_atomically(dst: Path, write):
    """Write an image file by way of a temporary one beside it, then move it into
    place. `write` is handed the temporary path.

    Every image here is read while something else is writing it: a photograph is
    served to one browser while another crops it, and both caches are built from
    whatever the file says at the moment they look at it. Saving straight onto the
    path truncates it first, so for as long as the encoder is running -- a tenth of
    a second for a phone photograph, and longer for a big one -- what is on disk is
    a fragment of a JPEG. A reader that arrives in that window does not get an
    error it can retry: it gets a fragment, and a fragment decodes to a picture
    that is half grey. Served under a `?v=` URL, which is `immutable` for a year,
    that half-grey picture is then kept by the browser and never asked for again.

    os.replace is atomic on POSIX: a reader holds either the whole old file or the
    whole new one and never half of either, and one that opened the old file keeps
    reading it safely after the swap. thumbs._write_atomically is the same function
    for the copies thumbs makes, which cannot import this one.

    And a temporary of its own for every writer, rather than one name they all
    share. Two writers arrive at the same destination whenever a cached copy goes
    stale, which is what every copy of a photograph does the moment it is cropped:
    the reloaded page asks for the same photograph at several widths at once, and
    each of those requests rebuilds the same watermarked file. Sharing `<name>.part`
    meant the second writer truncated the first's file underneath it -- and once the
    first renamed that file into place, the second went on writing into the file now
    being served. What a reader got in that window was a fragment, and a fragment
    decodes to a picture that is half grey. A refresh a moment later found the
    copies settled and looked fine, which is what made it look like the browser's
    fault. With a temporary each, os.replace is last-writer-wins with whole files,
    and nothing ever writes into the file being read.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Not a .jpeg/.png: folder_images picks photographs out of the directory by
    # extension, so a half-written one must not look like a photograph to it.
    fd, name = tempfile.mkstemp(dir=dst.parent, prefix=f"{dst.name}.", suffix=".part")
    os.close(fd)
    tmp = Path(name)
    try:
        write(tmp)
        os.replace(tmp, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


def _image_format(path: Path, opened=None) -> str:
    """The format to encode as. Taken from the file that was opened where there is
    one, and from the extension otherwise -- it cannot be left to Pillow to infer,
    because what it would infer it from is the temporary name ending in .part."""
    from PIL import Image

    return (
        opened.format
        if opened is not None and opened.format
        else Image.registered_extensions().get(path.suffix.lower(), "JPEG")
    )


def _make_watermark(src_path: Path, dst_path: Path):
    from PIL import Image, ImageOps

    # Bake in EXIF orientation, exactly as editing a photo does. This copy is
    # re-encoded without the EXIF block, so a photo whose pixels lie on their side
    # and say so only in that block would be served -- and shown -- on its side.
    # Worse than looking wrong: a crop dragged on that view was being mapped onto
    # the upright original, so it kept a different region of the photo altogether.
    with Image.open(src_path) as src:
        base = ImageOps.exif_transpose(src).convert("RGBA")
    w, h = base.size
    mark = Image.open(WM_SRC).convert("RGBA")
    target = max(WM_MIN_PX, int(min(w, h) * WM_SCALE))
    mark.thumbnail((target, target), Image.Resampling.LANCZOS)
    mark.putalpha(mark.getchannel("A").point(lambda a: int(a * WM_OPACITY)))
    margin = max(6, int(min(w, h) * WM_MARGIN))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(mark, (w - mark.width - margin, h - mark.height - margin), mark)
    out = Image.alpha_composite(base, layer)
    if dst_path.suffix.lower() in (".jpg", ".jpeg"):
        rgb = out.convert("RGB")
        _write_atomically(dst_path, lambda tmp: rgb.save(tmp, "JPEG", quality=88))
    else:
        fmt = _image_format(dst_path)
        _write_atomically(dst_path, lambda tmp: out.save(tmp, fmt))


def _watermarked_file(rel: str) -> Path:
    """Path to the cached watermarked copy of an image, regenerated if stale.
    Falls back to the original on any compositing error."""
    src = IMAGES_DIR / rel
    dst = WM_CACHE / rel
    try:
        # Read once, before the copy is made, and stamped onto the copy after: what
        # this says is "made from the photograph as it stood at that moment". Taking
        # the clock instead would date a copy later than a photograph that had been
        # replaced while it was being made, and that copy -- of the picture before
        # the crop -- would then look fresh forever.
        stamp = src.stat().st_mtime
        if not dst.exists() or dst.stat().st_mtime < stamp:
            _make_watermark(src, dst)
            with contextlib.suppress(OSError):
                os.utime(dst, (stamp, stamp))
        return dst
    except Exception:
        return src


def _wm_forget(rel: str):
    """Drop an image's cached watermark and its resized copies (on delete, rename or
    edit) so they regenerate.

    A copy is rebuilt anyway once it is older than what it was made from, which is
    what covers an edit. This is for the case that check cannot see: a photograph
    that is gone, whose copies would otherwise sit on the disk forever.
    """
    with contextlib.suppress(OSError):
        (WM_CACHE / rel).unlink(missing_ok=True)
    thumbs.forget(IMAGES_DIR, rel)


def _is_own_photo(rel: str) -> bool:
    # A photograph on a history entry is marked like any other: it is this
    # collection's own photograph of its own machine, taken by whoever did the
    # work, and the mark is there for where a photograph goes rather than for
    # which page of the site it was shown on.
    ext = Path(rel).suffix.lower()
    return (
        WATERMARK
        and ext in IMAGE_EXTS
        and (rel.startswith(("computers/", "parts/", LOG_KIND + "/")))
        and not is_reference(rel)
    )


def _image_cache(versioned: bool) -> dict:
    """How long the browser may keep an image.

    A URL carrying ?v= names which version of the photograph it wants -- img_url
    stamps it from the file's mtime -- so that URL can never go stale and may be
    kept for as long as the browser likes. Editing the photograph changes the stamp
    and therefore the URL, which is the whole point of having one. A URL without a
    stamp could mean anything later, so it gets the hour it always had.
    """
    return {
        "Cache-Control": "public, max-age=31536000, immutable"
        if versioned
        else "public, max-age=3600"
    }


def pick_images(kind, asset_id, listing):
    """An asset's photos from a folder listing: <asset_id>.<ext> first, then -2,
    -3, ..., then any other suffix alphabetically."""
    primary, extras = [], []
    for stem, name in listing:
        if stem == asset_id:
            primary.append(f"{kind}/{name}")
        elif stem.startswith(asset_id + "-"):
            extras.append((stem, name))

    def sort_key(item):
        suffix = item[0][len(asset_id) + 1 :]
        return (0, int(suffix), "") if suffix.isdigit() else (1, 0, suffix.lower())

    return primary + [f"{kind}/{name}" for _stem, name in sorted(extras, key=sort_key)]


def detect_images(kind, asset_id):
    """Ordered photos for one asset."""
    return pick_images(kind, asset_id, folder_images(kind))


def _storage_placeholder(kind):
    """Which drive icon a storage part wears, read from its Kind spec: a floppy, a
    disc and a disk are all "storage" and none of them look alike."""
    kind = (kind or "").lower()
    if "optical" in kind:
        return entry.placeholder_for("optical")
    if "floppy" in kind or "gotek" in kind:
        return entry.placeholder_for("floppy")
    return entry.placeholder_for("storage")


def _photo_target(kind, asset_id, ext):
    """Path for a new photo: <asset_id>.<ext> for the first (the primary), then
    the next free -N suffix so an item can carry several."""
    folder = IMAGES_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    existing = detect_images(kind, asset_id)
    if not any(Path(p).stem == asset_id for p in existing):
        name = f"{asset_id}{ext}"
    else:
        n = 2
        while any(Path(p).stem == f"{asset_id}-{n}" for p in existing):
            n += 1
        name = f"{asset_id}-{n}{ext}"
    return folder / name, f"{kind}/{name}"


def _verify_image(source):
    """Confirm something really is one of the image types we accept, by decoding it
    rather than trusting its name -- an SVG or an HTML page renamed .png would
    otherwise be stored and then served with an image content-type. `source` is a
    path or an open binary file. Raises 400 if it is not a valid, accepted image."""
    from PIL import Image

    try:
        with Image.open(source) as im:
            fmt = im.format
            im.verify()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "not a valid image file") from exc
    if fmt not in IMAGE_FORMATS:
        raise HTTPException(400, f"unsupported image type: {fmt}")


def _save_photo(kind, asset_id, upload: UploadFile):
    ext = Path(upload.filename or "").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise HTTPException(400, f"unsupported image type: {ext}")
    path, rel = _photo_target(kind, asset_id, ext)

    def write(tmp):
        with open(tmp, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        # Refuse anything whose bytes are not really the image its name claims;
        # _write_atomically drops the temporary file if this raises, so nothing
        # half-written is moved into place.
        _verify_image(tmp)

    # A page loading while this one is still arriving reads the folder and finds
    # whatever is in it; until the move, what is in it is not this photograph.
    _write_atomically(path, write)
    return rel


def _chosen_photos(form):
    """The photos picked on a create form, every one of them checked before any is
    written. The item is committed before its photos are stored, so its asset id is
    settled first: a file rejected half way would otherwise leave photos filed
    under an id the item never kept, which the next thing created would inherit."""
    ups = [u for u in form.uploads("photos") if (u.filename or "").strip()]
    for up in ups:
        ext = Path(up.filename or "").suffix.lower() or ".jpg"
        if ext not in IMAGE_EXTS:
            raise HTTPException(400, f"unsupported image type: {ext}")
        # Content-check here too, before the item is committed, so a file that is
        # not really an image leaves nothing created (see the docstring above).
        up.file.seek(0)
        try:
            _verify_image(up.file)
        finally:
            up.file.seek(0)
    return ups


# --- photographs of what happened, as against the portrait of the thing ------
# These reuse everything the gallery photographs use -- the same storage, the same
# watermark, the same resized copies -- and differ in one thing only: the folder
# they go in, and therefore that nothing reading an asset's folder can mistake one
# for a picture of the asset. The log entry's id stands where an asset id stands,
# so _photo_target's <id>.jpg, <id>-2.jpg naming works unchanged, and entry 12's
# photographs cannot be claimed by entry 120 because the second name always has the
# hyphen in it.


def _attach_log_photos(db, row, uploads):
    """Store photographs against a history entry. Returns how many were kept.

    The entry is flushed first: the photographs are filed under its id, and until
    the insert has gone to the database there is no id to file them under. Nothing
    is committed here -- the caller does that, once the entry and its photographs
    are both written.
    """
    if row is None or not uploads:
        return 0
    db.flush()
    for up in uploads:
        db.add(LogPhoto(log_id=row.id, rel=_save_photo(LOG_KIND, str(row.id), up)))
    return len(uploads)


def _drop_log_photos(db, asset_id):
    """Clear the photographs hung on one asset's history, and return their paths for
    the caller to delete once the transaction is safe.

    By hand rather than by the foreign key's cascade, for the reason the log entries
    themselves are: the paths have to be read while the rows are still there, since
    a file is the one thing here that cannot be rolled back.
    """
    ids = [i for (i,) in db.query(LogEntry.id).filter(LogEntry.asset_id == asset_id)]
    if not ids:
        return []
    rels = [
        rel
        for (rel,) in db.query(LogPhoto.rel).filter(LogPhoto.log_id.in_(ids)).order_by(LogPhoto.id)
    ]
    db.query(LogPhoto).filter(LogPhoto.log_id.in_(ids)).delete(synchronize_session=False)
    return rels


def _fetch_reference_photo(kind, asset_id, url):
    """Pull a photo from the item's reference URL (Wikipedia API or og:image),
    store it, and return its relative path (or None if nothing was found)."""
    data = enrich.fetch_jpeg(url)
    if not data:
        return None
    path, rel = _photo_target(kind, asset_id, ".jpg")
    path.write_bytes(data)
    # A fetched photo is from the reference source, not necessarily this unit;
    # record the source so we can show its favicon.
    _mark_reference(rel, True, "Photo from the reference source, may not be this exact unit", url)
    return rel


# A photo can be flagged as a reference / stock image (not a photo of the actual
# unit) with a small ".ref" sidecar file next to it. The sidecar holds JSON with
# an optional note and the source URL it was crawled from; from that source we
# cache the site's favicon and show it in the photo's corner. No schema change,
# and the marker travels with the image.
FAVICON_DIR = IMAGES_DIR / "favicons"
_DEFAULT_REF_NOTE = "Illustrative image, not this exact unit"


def _ref_sidecar(rel):
    p = IMAGES_DIR / rel
    return p.with_name(p.name + ".ref")


def is_reference(rel):
    return bool(rel) and _ref_sidecar(rel).exists()


def _read_ref(rel):
    """{'note':.., 'source':..} for a reference image, or None if not flagged.
    Tolerates the pre-JSON format where the sidecar held a bare note string."""
    try:
        raw = _ref_sidecar(rel).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if raw.startswith("{"):
        try:
            d = json.loads(raw)
            return {"note": d.get("note", ""), "source": d.get("source", "")}
        except ValueError:
            pass
    return {"note": raw, "source": ""}


def _favicon_rel(source):
    """Relative path of the cached favicon for a source URL's host, if present."""
    host = urlparse(source or "").hostname or ""
    if host and (FAVICON_DIR / f"{host}.png").exists():
        return f"favicons/{host}.png"
    return ""


def reference_marks(kind, asset_id):
    """{rel: {'note':.., 'icon':..}} for the item's flagged reference photos."""
    out = {}
    for rel in detect_images(kind, asset_id):
        info = _read_ref(rel)
        if info is not None:
            out[rel] = {
                "note": info["note"] or _DEFAULT_REF_NOTE,
                "icon": _favicon_rel(info["source"]),
            }
    return out


def tuned_photos(kind, asset_id):
    """The item's photos that still have a kept original, so the big view can
    offer to put them back."""
    return {rel for rel in detect_images(kind, asset_id) if has_original(rel)}


def _favicon_for_rel(rel):
    """Cached source favicon path for a single image rel, or '' (for index cards)."""
    info = _read_ref(rel) if rel else None
    return _favicon_rel(info["source"]) if info else ""


def img_url(rel, width=None):
    """/images URL for a photo with a cache-busting ?v= stamp from its mtime, so
    the browser refetches after an edit or watermark change rather than showing a
    stale cached copy. Reflects the reference-marker sidecar too (its toggle
    changes whether the served image is watermarked).

    `width` asks for a copy no wider than that many pixels -- see thumbs.py. Leave
    it out for the original, which is what the lightbox wants and what everything
    wanted before there were copies to ask for.

    Milliseconds, not seconds. The stamp is what makes a year-long, `immutable`
    cache safe -- the URL of a photograph that has changed is a different URL -- and
    in whole seconds two edits inside one second were the same URL for two different
    pictures. Turning a photograph twice takes rather less than a second, so the
    second turn was shown the first one's copy and kept it; a refresh was the only
    thing that put it right, which made a stale cache look like a corrupt file.
    """
    if not rel:
        return ""
    ts = 0
    for p in (IMAGES_DIR / rel, _ref_sidecar(rel)):
        with contextlib.suppress(OSError):
            ts = max(ts, p.stat().st_mtime_ns // 1_000_000)
    query = f"?v={ts}" if ts else ""
    if width:
        query += ("&" if query else "?") + f"w={int(width)}"
    return f"/images/{rel}{query}"


def img_srcset(rel, widths):
    """A srcset for one photo at several widths, so the browser takes the one that
    suits its screen: a card is 400 wide on an ordinary display and 800 on a retina
    one, and only it knows which it is."""
    return ", ".join(f"{img_url(rel, w)} {w}w" for w in widths) if rel else ""


def _cache_favicon(source):
    """Fetch and cache the source site's favicon; return its rel path or ''."""
    host = urlparse(source or "").hostname or ""
    if not host:
        return ""
    dest = FAVICON_DIR / f"{host}.png"
    if dest.exists():
        return f"favicons/{host}.png"
    data = enrich.fetch_favicon(source)
    if not data:
        return ""
    FAVICON_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"favicons/{host}.png"


def _mark_reference(rel, on, note="", source=""):
    sc = _ref_sidecar(rel)
    if on:
        sc.write_text(
            json.dumps({"note": note or _DEFAULT_REF_NOTE, "source": source}), encoding="utf-8"
        )
        if source:
            _cache_favicon(source)
    elif sc.exists():
        sc.unlink()
    _wm_forget(rel)  # reference state changed: rebuild (or drop) the watermark


def _move_with_sidecar(src: Path, dst: Path):
    """Rename an image, carrying its reference-marker sidecar along with it, and
    dropping stale watermark caches for both names."""
    src.rename(dst)
    sc = src.with_name(src.name + ".ref")
    if sc.exists():
        sc.rename(dst.with_name(dst.name + ".ref"))
    for p in (src, dst):
        with contextlib.suppress(ValueError):
            rel = str(p.relative_to(IMAGES_DIR))
            _drop_original(rel)
            _wm_forget(rel)


def _set_primary_photo(kind, asset_id, rel):
    """Promote one of an item's photos to the primary (the <asset_id>.<ext>
    file shown in the gallery and as the main photo). The current primary is
    demoted to the next free extra slot. Returns the new primary's path."""
    if rel not in detect_images(kind, asset_id):
        raise HTTPException(404, "no such photo for this item")
    folder = IMAGES_DIR / kind
    chosen = folder / Path(rel).name
    if chosen.stem == asset_id:
        return rel
    for f in list(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS and f.stem == asset_id:
            n = 2
            while (folder / f"{asset_id}-{n}{f.suffix}").exists():
                n += 1
            _move_with_sidecar(f, folder / f"{asset_id}-{n}{f.suffix}")
            break
    new_primary = folder / f"{asset_id}{chosen.suffix}"
    _move_with_sidecar(chosen, new_primary)
    return f"{kind}/{new_primary.name}"


def _delete_image(kind, asset_id, rel):
    """Delete a photo (and its reference sidecar). If it was the primary, the
    next remaining photo is promoted. Returns (was_primary, new_primary_rel)."""
    if rel not in detect_images(kind, asset_id):
        raise HTTPException(404, "no such photo for this item")
    p = IMAGES_DIR / rel
    was_primary = p.stem == asset_id
    sc = _ref_sidecar(rel)
    if sc.exists():
        sc.unlink()
    p.unlink()
    _drop_original(rel)
    _wm_forget(rel)
    new_primary = ""
    if was_primary:
        remaining = detect_images(kind, asset_id)
        if remaining:
            new_primary = _set_primary_photo(kind, asset_id, remaining[0])
    return was_primary, new_primary


def _purge_photos(rels):
    """Delete photo files, each with its reference sidecar and cached watermark.
    Called after the rows are safely gone -- a file cannot be rolled back."""
    for rel in rels:
        with contextlib.suppress(OSError):
            _ref_sidecar(rel).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            (IMAGES_DIR / rel).unlink(missing_ok=True)
        _drop_original(rel)
        _wm_forget(rel)


# Where a photograph's pre-tuneup self is kept. Under a dotted name, like the
# watermark and resize caches, which is what keeps it off the wire: serve_image
# refuses any path with a dotted segment, so an untouched -- and unwatermarked --
# copy of every tuned photograph cannot be fetched by asking for it.
ORIG_CACHE = IMAGES_DIR / ".orig"


def _original_of(rel: str) -> Path:
    return ORIG_CACHE / rel


def has_original(rel: str) -> bool:
    """Whether this photo can still be put back the way it was."""
    return _original_of(rel).is_file()


def _keep_original(rel: str):
    """Copy a photograph aside before it is tuned, if it is not already there.

    One slot, and the first copy wins: tuning an already-tuned photograph must
    still revert to what came off the camera rather than to the previous tuning.
    """
    dst = _original_of(rel)
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Copied, not moved: the photograph carries on being served throughout.
    shutil.copy2(IMAGES_DIR / rel, dst)


def _drop_original(rel: str):
    """Forget the kept copy. Called when it has stopped being the truth about this
    photograph -- the file has been cropped, rotated, renamed or deleted since.
    Reverting then would quietly undo that other edit as well, which is not what
    the button says it does, so the offer is withdrawn instead."""
    with contextlib.suppress(OSError):
        _original_of(rel).unlink(missing_ok=True)


def _restore_original(rel: str):
    """Put the kept copy back and take the slot away with it."""
    src = _original_of(rel)
    if not src.is_file():
        raise HTTPException(404, "nothing kept for this photo")
    # Through the same atomic swap every other write here uses: this photograph is
    # being served while it is replaced. See _write_atomically.
    _write_atomically(IMAGES_DIR / rel, lambda tmp: shutil.copyfile(src, tmp))
    with contextlib.suppress(OSError):
        src.unlink(missing_ok=True)


def _edit_image(kind, asset_id, rel, fn, revertible=False):
    """Apply fn(PIL.Image)->PIL.Image to a photo in place, baking in EXIF
    orientation, then invalidate its watermark cache.

    `revertible` keeps a copy of the photograph as it was first, for the one edit
    that offers to be undone. Every other edit is destructive as it always was,
    and says so by dropping any copy an earlier tuneup left: see _drop_original.
    """
    if rel not in detect_images(kind, asset_id):
        raise HTTPException(404, "no such photo for this item")
    if revertible:
        _keep_original(rel)
    else:
        _drop_original(rel)
    from PIL import Image, ImageOps

    src = IMAGES_DIR / rel
    with Image.open(src) as im:
        out = fn(ImageOps.exif_transpose(im))
        fmt = _image_format(src, im)
        kwargs = {}
        if src.suffix.lower() in (".jpg", ".jpeg"):
            out = out.convert("RGB")
            kwargs = {"quality": 90}
        # Never onto `src` itself: it is being served to other browsers while this
        # runs, and a truncated photograph is what they would be handed and then
        # keep. See _write_atomically.
        _write_atomically(src, lambda tmp: out.save(tmp, fmt, **kwargs))
    # Deliberately not _wm_forget: the copies are dated by the photograph they were
    # made from, so replacing it has already made them stale and they rebuild on
    # the next request. Unlinking them here raced with anyone reading -- a request
    # that had chosen a copy to serve found it deleted out from under it between
    # choosing and opening, and answered a broken image. _wm_forget is for the case
    # the freshness check cannot see, which is a photograph that is gone.


def _rotate_op(direction):
    from PIL import Image

    turn = Image.Transpose.ROTATE_270 if direction == "cw" else Image.Transpose.ROTATE_90
    return lambda im: im.transpose(turn)


def _crop_op(x, y, w, h):
    """Crop to a box given as fractions (0..1) of the image's width/height."""

    def crop(im):
        iw, ih = im.size
        left, top = max(0, round(x * iw)), max(0, round(y * ih))
        right, bottom = min(iw, round((x + w) * iw)), min(ih, round((y + h) * ih))
        # Ignore a too-small or degenerate selection.
        if right - left < 8 or bottom - top < 8:
            return im
        return im.crop((left, top, right, bottom))

    return crop


def _tuneup_op():
    """The one-touch tuneup. See app/enhance.py for what it actually does."""
    from .enhance import tuneup

    return tuneup


def _photo_edit_redirect(kind, aid, image):
    """The photo editor used to be its own page. Rotating and cropping now live in
    the big view on the item page, so there is one crop implementation rather than
    two; this keeps any link or bookmark to the old page working."""
    return RedirectResponse(f"/{kind}/{aid}?photo={quote(image or '')}", status_code=303)


def _asset_log_photos(db, asset_id):
    """The photographs hung on one asset's history, read without touching them --
    what _drop_log_photos will return when the record is actually deleted."""
    return [
        rel
        for (rel,) in db.query(LogPhoto.rel)
        .join(LogEntry, LogEntry.id == LogPhoto.log_id)
        .filter(LogEntry.asset_id == asset_id)
        .order_by(LogPhoto.id)
    ]
