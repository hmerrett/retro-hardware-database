"""Regenerate the favicon / app-icon set from the master artwork.

Run it inside the api image (which has Pillow) with the static dir mounted:

    docker run --rm -v "$PWD/api/app/static:/static" \
        retro-hardware-database-api python /static/../../../tools/make_icons.py

or, more simply, from the repo root:

    docker run --rm -v "$PWD/api/app/static:/static" \
        -v "$PWD/tools:/tools" retro-hardware-database-api python /tools/make_icons.py

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
    logo that is not must not be stretched into one."""
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

    # The logo at its own proportions, for everywhere that is not a square slot:
    # the header, and the photo watermark. A watermark goes into the corner of a
    # photo at a fraction of its short edge, so a square with the logo letterboxed
    # inside it would put a smaller mark on the photo than the numbers ask for.
    def logo(width, name):
        im = tight.copy()
        im.thumbnail((width, width), Image.LANCZOS)
        im.save(f"{STATIC}/{name}", optimize=True)
        return im

    # Two sizes rather than one master-sized file: 512 is what a watermark needs on
    # the largest photo in the collection, and 256 is a 30px-tall header logo on a
    # 3x screen. Neither is the master, because the master is whatever artwork
    # somebody dropped in -- these are cropped, and known to be.
    big = logo(512, "logo-512.png")
    small = logo(256, "logo-256.png")
    print(f"logo-512.png at {big.size}, logo-256.png at {small.size}")
    make_share_card(tight)


# A social-share card is composited by the sites that show it, several of them onto
# black, so this one is opaque: the logo on a flat ground, at the 1.91:1 the card
# slots want. Cream because the artwork is a beige machine photographed against
# nothing -- white would leave its case looking grubby and charcoal would turn a
# shared link into a picture of a switched-off monitor.
CARD_SIZE = (1200, 630)
CARD_BG = (244, 240, 226)
CARD_FILL = 0.72  # of the card's width, leaving it room to breathe


def make_share_card(tight):
    card = Image.new("RGB", CARD_SIZE, CARD_BG)
    art = tight.copy()
    art.thumbnail((int(CARD_SIZE[0] * CARD_FILL), int(CARD_SIZE[1] * CARD_FILL)), Image.LANCZOS)
    card.paste(art, ((CARD_SIZE[0] - art.width) // 2, (CARD_SIZE[1] - art.height) // 2), art)
    card.save(f"{STATIC}/og-image.png", optimize=True)
    print(f"og-image.png at {card.size}, logo {art.size}")


if __name__ == "__main__":
    main()
