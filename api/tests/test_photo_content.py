"""Photo uploads were checked by filename extension only. A file named .png but
carrying something else -- an SVG or an HTML page -- was stored and then served
with an image content-type. Uploads must be validated by content.
"""

import io

from app import main


def test_a_png_that_is_not_really_an_image_is_refused_and_stores_nothing(client):
    folder = main.IMAGES_DIR / "computers"
    folder.mkdir(parents=True, exist_ok=True)
    before = sorted(p.name for p in folder.iterdir())

    r = client.post(
        "/computers/new",
        data={"model": "Sneaky"},
        files={
            "photos": (
                "evil.png",
                io.BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"),
                "image/png",
            )
        },
        follow_redirects=False,
    )

    assert r.status_code == 400
    # Checked before the machine is written, so nothing is created either.
    assert client.get("/api/computers").json() == []
    assert sorted(p.name for p in folder.iterdir()) == before


def test_a_real_png_is_accepted(client):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    buf.seek(0)
    r = client.post(
        "/computers/new",
        data={"model": "Genuine"},
        files={"photos": ("shot.png", buf, "image/png")},
        follow_redirects=False,
    )
    assert r.status_code in (200, 303)
    assert client.get("/api/computers").json()[0]["model"] == "Genuine"


def phone_photo():
    """The bytes a phone camera actually produces: a JPEG carrying a second image
    after the first (MPO -- Multi-Picture Object). iPhones and most Android
    cameras write one for a portrait-mode or HDR shot, name it .jpg, and every
    viewer shows the first frame -- but Pillow reports the format as MPO, and the
    content check refused it as an unsupported type."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (12, 8), "red").save(
        buf, "MPO", save_all=True, append_images=[Image.new("RGB", (12, 8), "blue")]
    )
    buf.seek(0)
    return buf


def test_a_photograph_from_a_phone_is_accepted(client):
    r = client.post(
        "/computers/new",
        data={"model": "Phoneshot"},
        files={"photos": ("IMG_4021.JPG", phone_photo(), "image/jpeg")},
        follow_redirects=False,
    )
    assert r.status_code in (200, 303), r.text
    assert client.get("/api/computers").json()[0]["model"] == "Phoneshot"


def test_a_phone_photograph_uploaded_to_an_item_is_accepted(client, computer):
    """The other door: the photo column on an item that already exists, which is
    where most photographs are actually added."""
    aid = computer()["asset_id"]
    r = client.post(
        f"/computers/{aid}/photo",
        files={"photos": ("IMG_4022.JPG", phone_photo(), "image/jpeg")},
        follow_redirects=False,
    )
    assert r.status_code in (200, 303), r.text
    assert main.detect_images("computers", aid)


def test_a_phone_photograph_can_still_be_rotated(client, computer):
    """The write path, which re-encodes in the format the file was opened as. A
    rotated photograph is one image and nothing else, so what it is written back as
    is an ordinary JPEG -- and it must still be readable afterwards."""
    from PIL import Image

    aid = computer()["asset_id"]
    client.post(
        f"/computers/{aid}/photo",
        files={"photos": ("IMG_4023.JPG", phone_photo(), "image/jpeg")},
        follow_redirects=False,
    )
    rel = main.detect_images("computers", aid)[0]
    r = client.post(
        f"/computers/{aid}/photo-rotate", data={"image": rel, "dir": "cw"}, follow_redirects=False
    )
    assert r.status_code in (200, 303), r.text
    with Image.open(main.IMAGES_DIR / rel) as im:
        assert im.size == (8, 12)
