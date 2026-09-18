"""The one-touch tuneup: the automatic levels-and-colour fix, and the single
step back it offers.

Two things are being pinned down here. That the fix actually improves a flat
photograph without flattening a well-exposed one -- an automatic correction that
"corrects" a good frame is worse than none. And that "revert" means exactly what
it says: it is on offer only while the kept original is still the truth about the
photograph, and withdrawn the moment another edit has made it a lie.
"""

import io

import pytest
from PIL import Image, ImageStat

from app import enhance, main
from app.enhance import _KEY_HI, _KEY_LO, tuneup


def _contrast(im):
    return ImageStat.Stat(im.convert("L")).stddev[0]


def _brightness(im):
    return ImageStat.Stat(im.convert("L")).mean[0]


def flat_photograph(size=(60, 40)):
    """A dull frame: a narrow band of greys, nothing near black or white. What an
    underlit shot of a beige case on a beige bench actually looks like."""
    im = Image.new("RGB", size)
    im.putdata(
        [
            (90 + (x * 3) % 40, 88 + (x * 3) % 40, 84 + (x * 3) % 40)
            for x in range(size[0] * size[1])
        ]
    )
    return im


def upload(client, kind, aid, name="shot.png", im=None):
    buf = io.BytesIO()
    (im or flat_photograph()).save(buf, "PNG")
    buf.seek(0)
    r = client.post(
        f"/{kind}/{aid}/photo", files={"photos": (name, buf, "image/png")}, follow_redirects=False
    )
    assert r.status_code in (200, 303), r.text
    return main.detect_images(kind, aid)[0]


# --- the fix itself --------------------------------------------------------


def test_a_flat_photograph_gains_contrast():
    before = flat_photograph()
    after = tuneup(before)
    assert _contrast(after) > _contrast(before) * 1.3


def test_a_dark_photograph_is_lifted():
    dark = Image.new("RGB", (40, 40))
    dark.putdata([(12 + (i % 20), 11 + (i % 20), 10 + (i % 20)) for i in range(1600)])
    assert _brightness(tuneup(dark)) > _brightness(dark)


def test_a_well_exposed_photograph_keeps_its_brightness():
    """The fix is for the contrast, not the exposure. A frame already in the
    comfortable band comes out at the brightness the photographer got."""
    im = flat_photograph()  # averages ~108, inside the band
    assert _KEY_LO < _brightness(im) < _KEY_HI
    assert abs(_brightness(tuneup(im)) - _brightness(im)) < 8


def test_a_bright_photograph_is_not_dragged_down_to_a_middle_grey():
    """A pale machine on a pale bench: nothing in the frame is dark, and reading
    that as a fault to be stretched away is what took such a photograph from an
    average of 192 to 127 and made a clean shot look underexposed. It is brought
    to the top of the band and no further."""
    im = Image.new("RGB", (60, 40))
    im.putdata([(150 + (i * 7) % 90, 148 + (i * 7) % 90, 145 + (i * 7) % 90) for i in range(2400)])
    assert _brightness(im) > _KEY_HI
    after = _brightness(tuneup(im))
    assert after >= _KEY_HI - 5
    assert _contrast(tuneup(im)) > _contrast(im)


def test_the_size_and_mode_survive():
    out = tuneup(flat_photograph((23, 17)))
    assert out.size == (23, 17)
    assert out.mode == "RGB"


@pytest.mark.parametrize("mode", ["L", "RGBA", "P"])
def test_it_copes_with_the_other_modes_a_stored_image_can_be_in(mode):
    """Not every photograph in the collection is a plain RGB JPEG: there are
    greyscale scans and PNGs with an alpha channel."""
    assert tuneup(flat_photograph().convert(mode)).mode == "RGB"


def test_a_stronger_stretch_setting_gives_more_contrast_not_less(monkeypatch):
    """A guard on the direction of the knob, which was once backwards.

    The levels curve used to be damped by moving the ends part of the way towards
    0 and 255. That is inverted: pushing the top end towards 255 widens the range
    being mapped onto the full scale, so it stretches *less*. Raising the constant
    to make the fix bolder made it weaker instead, and nothing said so, because
    every other test only asked that contrast went up at all.
    """
    im = flat_photograph()
    got = []
    for strength in (0.2, 0.5, 0.9):
        monkeypatch.setattr(enhance, "_STRETCH", strength)
        got.append(_contrast(enhance._levels(im)))
    assert got == sorted(got), f"contrast did not rise with the setting: {got}"
    assert got[-1] > got[0] * 1.5


def test_an_already_colourful_photograph_gets_less_of_the_colour_boost():
    """Pushed hard, a strong single colour clips to a flat block and loses its
    detail -- which shows up as the measured saturation going *down*. So the
    boost is full on a flat frame and eases off on a vivid one."""
    drab = Image.new("RGB", (40, 40))
    drab.putdata([(120 + (i % 12), 118 + (i % 12), 116 + (i % 12)) for i in range(1600)])
    vivid = Image.new("RGB", (40, 40))
    vivid.putdata([(200 + (i % 40), 20 + (i % 30), 15 + (i % 30)) for i in range(1600)])

    assert enhance._colour_boost(drab) > enhance._colour_boost(vivid)
    assert enhance._colour_boost(drab) <= enhance._COLOUR_MAX
    assert enhance._colour_boost(vivid) >= enhance._COLOUR_MIN


def test_the_fix_makes_colours_more_saturated_not_less():
    """The point of the whole last stage. Measured on a frame with real colour in
    it rather than the grey test card, and it must not clip its way backwards."""
    im = Image.new("RGB", (60, 40))
    im.putdata([(90 + (i * 5) % 60, 120 + (i * 3) % 50, 70 + (i * 7) % 40) for i in range(2400)])
    before = ImageStat.Stat(im.convert("HSV").getchannel("S")).mean[0]
    after = ImageStat.Stat(tuneup(im).convert("HSV").getchannel("S")).mean[0]
    assert after > before


# --- the button ------------------------------------------------------------


def test_tuning_a_photo_changes_it_and_keeps_the_original(client, computer):
    aid = computer()["asset_id"]
    rel = upload(client, "computers", aid)
    was = (main.IMAGES_DIR / rel).read_bytes()

    r = client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)

    assert r.status_code in (200, 303), r.text
    assert (main.IMAGES_DIR / rel).read_bytes() != was
    assert main.has_original(rel)
    assert main._original_of(rel).read_bytes() == was


def test_the_history_records_it(client, computer):
    aid = computer()["asset_id"]
    rel = upload(client, "computers", aid)
    client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)
    assert "tuned a photo" in client.get(f"/computers/{aid}").text


def test_reverting_puts_the_photograph_back_exactly(client, computer):
    aid = computer()["asset_id"]
    rel = upload(client, "computers", aid)
    was = (main.IMAGES_DIR / rel).read_bytes()
    client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)

    r = client.post(f"/computers/{aid}/photo-revert", data={"image": rel}, follow_redirects=False)

    assert r.status_code in (200, 303), r.text
    assert (main.IMAGES_DIR / rel).read_bytes() == was
    # And the offer goes with it: there is nothing further to go back to.
    assert not main.has_original(rel)


def test_pressing_tuneup_twice_does_not_tune_it_twice(client, computer):
    """Each edit re-encodes the file, so a second press would cost another
    generation of JPEG for a photograph that has already had the fix."""
    aid = computer()["asset_id"]
    rel = upload(client, "computers", aid)
    client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)
    once = (main.IMAGES_DIR / rel).read_bytes()

    client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)

    assert (main.IMAGES_DIR / rel).read_bytes() == once


def test_a_later_edit_withdraws_the_offer_to_revert(client, computer):
    """Reverting after a crop would quietly undo the crop as well, which is not
    what the button says it does. The kept original goes when it stops being the
    truth about the photograph."""
    aid = computer()["asset_id"]
    rel = upload(client, "computers", aid)
    client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)
    assert main.has_original(rel)

    client.post(
        f"/computers/{aid}/photo-rotate", data={"image": rel, "dir": "cw"}, follow_redirects=False
    )

    assert not main.has_original(rel)
    assert rel not in main.tuned_photos("computers", aid)
    r = client.post(f"/computers/{aid}/photo-revert", data={"image": rel}, follow_redirects=False)
    assert r.status_code == 404


def test_deleting_the_photograph_takes_the_kept_original_with_it(client, computer):
    aid = computer()["asset_id"]
    rel = upload(client, "computers", aid)
    client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)
    kept = main._original_of(rel)
    assert kept.is_file()

    client.post(f"/computers/{aid}/photo-delete", data={"image": rel}, follow_redirects=False)

    assert not kept.exists()


def test_the_kept_original_cannot_be_fetched(client, computer):
    """It lives under a dotted directory precisely so it cannot: it is an
    unwatermarked copy of a photograph the site only ever serves watermarked."""
    aid = computer()["asset_id"]
    rel = upload(client, "computers", aid)
    client.post(f"/computers/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)
    assert client.get(f"/images/.orig/{rel}").status_code == 404


def test_a_photo_belonging_to_another_item_is_refused(client, computer):
    mine, theirs = computer()["asset_id"], computer()["asset_id"]
    rel = upload(client, "computers", theirs)
    r = client.post(f"/computers/{mine}/photo-tuneup", data={"image": rel}, follow_redirects=False)
    assert r.status_code == 404


def test_a_part_can_be_tuned_too(client, part):
    aid = part()["asset_id"]
    rel = upload(client, "parts", aid)
    was = (main.IMAGES_DIR / rel).read_bytes()
    r = client.post(f"/parts/{aid}/photo-tuneup", data={"image": rel}, follow_redirects=False)
    assert r.status_code in (200, 303), r.text
    assert (main.IMAGES_DIR / rel).read_bytes() != was
    assert rel in main.tuned_photos("parts", aid)
