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
        "/computers/new", data={"model": "Sneaky"},
        files={"photos": ("evil.png",
                          io.BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'"
                                     b" onload='alert(1)'/>"),
                          "image/png")},
        follow_redirects=False)

    assert r.status_code == 400
    # Checked before the machine is written, so nothing is created either.
    assert client.get("/api/computers").json() == []
    assert sorted(p.name for p in folder.iterdir()) == before


def test_a_real_png_is_accepted(client):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    buf.seek(0)
    r = client.post("/computers/new", data={"model": "Genuine"},
                    files={"photos": ("shot.png", buf, "image/png")},
                    follow_redirects=False)
    assert r.status_code in (200, 303)
    assert client.get("/api/computers").json()[0]["model"] == "Genuine"
