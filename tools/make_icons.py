"""Regenerate the favicon / app-icon set from the master artwork.

Run it inside the api image (which has Pillow) with the static dir mounted:

    docker run --rm -v "$PWD/api/app/static:/static" \
        retro-hardware-db-2-api python /static/../../../tools/make_icons.py

or, more simply, from the repo root:

    docker run --rm -v "$PWD/api/app/static:/static" \
        -v "$PWD/tools:/tools" retro-hardware-db-2-api python /tools/make_icons.py

Set RHDB_STATIC to run it outside the container against a checkout:

    RHDB_STATIC=api/app/static python3 tools/make_icons.py

It crops the master to its solid content (ignoring any soft drop-shadow in the
transparent padding), squares it, and writes every size the pages reference.
Every output keeps its alpha channel except apple-touch-icon.png, which is
deliberately flattened on white because iOS composites transparency on black.
Rebuild the api image afterwards so the files are copied in.
"""
import os

from PIL import Image

STATIC = os.getenv("RHDB_STATIC", "/static")
MASTER = f"{STATIC}/app-icon.png"
# Alpha below this is treated as empty padding (excludes soft shadows), so the
# icon is cropped to its solid artwork rather than the shadow's faint halo.
ALPHA_THRESHOLD = 32


def load_tight():
    """The master cropped to its artwork, aspect intact."""
    base = Image.open(MASTER).convert("RGBA")
    mask = base.getchannel("A").point(lambda v: 255 if v > ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox()
    return base.crop(bbox) if bbox else base


def squared(icon):
    """Centred in a transparent square, because every icon slot is square and a
    logo wider than it is tall must not be stretched into one."""
    w, h = icon.size
    s = max(w, h)
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.paste(icon, ((s - w) // 2, (s - h) // 2), icon)
    return sq


def main():
    tight = load_tight()
    sq = squared(tight)
    print(f"cropped master to {tight.size}, squared to {sq.size}")

    def out(size, name, white=False):
        im = sq.resize((size, size), Image.LANCZOS)
        if white:  # iOS composites transparency on black, so flatten on white
            bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im).convert("RGB")
        im.save(f"{STATIC}/{name}", optimize=True)

    out(16, "favicon-16x16.png")
    out(32, "favicon-32x32.png")
    out(180, "apple-touch-icon.png", white=True)
    out(192, "icon-192.png")
    out(512, "icon-512.png")
    sq.save(f"{STATIC}/favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])

    # The photo watermark, from the tight crop rather than the squared icon: it is
    # composited into a corner at a fraction of the photo's short edge, so a square
    # with the logo letterboxed inside it would put a smaller mark on the photo than
    # the numbers ask for -- and the padding is invisible against the picture.
    mark = tight.copy()
    mark.thumbnail((512, 512), Image.LANCZOS)
    mark.save(f"{STATIC}/watermark.png", optimize=True)
    print(f"regenerated favicon.ico + png icons, and watermark.png at {mark.size}")


if __name__ == "__main__":
    main()
