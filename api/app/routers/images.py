"""The route that serves a photograph.

Every picture the register shows goes through here rather than off the filesystem
directly: it is where the watermark is put on, where a request for a narrower copy
is answered, and where a path that tries to leave the photograph folder is refused.
The upload side of the same store is in photos.py; this is only the reading of it.
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import thumbs
from ..common import IMAGES_DIR, IMAGE_EXTS
from ..photos import _image_cache, _is_own_photo, _watermarked_file

router = APIRouter()


@router.get("/images/{path:path}", include_in_schema=False)
def serve_image(path: str, v: str = "", w: int = 0):
    # Reject traversal, dotfiles/dotdirs (e.g. the .wm and .sized caches) and
    # non-images.
    if any(seg.startswith(".") for seg in path.split("/")):
        raise HTTPException(404)
    full = (IMAGES_DIR / path).resolve()
    if not str(full).startswith(str(IMAGES_DIR.resolve()) + os.sep) or not full.is_file():
        raise HTTPException(404)
    if full.suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(404)
    served = _watermarked_file(path) if _is_own_photo(path) else full
    # ?w= asks for a copy no wider than that, made and kept on first request. Only
    # the widths the templates use are made; anything else is served whole rather
    # than refused, because a photograph is never the wrong answer to a request for
    # a photograph.
    if w:
        served = thumbs.served_path(IMAGES_DIR, path, w, served)
    # A copy can still go between being chosen and being opened -- deleting a
    # photograph takes its copies with it. The original is the same picture and is
    # still here; a slower answer beats a broken one.
    if not served.exists():
        served = full
    return FileResponse(served, headers=_image_cache(bool(v)))
