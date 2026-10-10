"""A label prints what its list says, and a crowded one makes room before it leaves
anything off (MANUAL §13, "What's on it").

Every kind follows the list, a location as much as a machine. Where the details
ticked need more lines than there is room for, the type a larger label grows into
is given back, as far as the 51x19 mm tape's own size; past that the last ones go,
and the label says which -- the settings page puts it under the picture.

What is drawn is read off a surface that notes what it was asked to draw and passes
it on (test_two_labels_each_set_up_for_its_job), because the layout measures before
it decides anything.
"""

import pytest

from app import labels, surfaces
from test_two_labels_each_set_up_for_its_job import Recording, largest, words

# A drive with a name of its own, three lines of specification on a small label, a
# serial number and somewhere it is kept; a box on a shelf; a project.
DRIVE = {
    "asset_id": "RH-K7Q2",
    "name": "Boot disk",
    "manufacturer": "Seagate",
    "model": "ST-225",
    "type": "storage",
    "specs": 'Capacity: 20MB | CHS: 615/4/17 | Form factor: 5.25"',
    "serial": "3B4471",
    "kept": "Workshop / Drawer 4",
    "variant": "",
}
PLACE = {
    "asset_id": "RH-9J2X",
    "name": "Box 14",
    "kept": "Workshop / Rack 3 / Shelf 2",
    "kind": "Box",
    "notes": "Floppy drives",
}
RECAP = {"asset_id": "RH-J0Y7", "name": "Recap the PC1512", "status": "active"}
EVERY = ("tag", "name", "make", "specs", "serial", "kept")
LARGE = "dymo-99012"


def setup(listed, codes=labels.QR, word=True, stock=labels.SMALL):
    return labels.Setup(
        "small", "Small label", codes, stock, tuple(listed), word, labels.LABEL_FACE
    )


def drawn(row, kind, stock, label):
    """What a label set up as `label` draws for `row` on a stock, and what it says it
    had no room for."""
    media = labels.MEDIA[stock]
    surface = Recording(
        surfaces.RasterSurface(surfaces.blank(*labels.size_dots(media)), media["dpi"])
    )
    fit = labels._draw(surface, media, row, [], kind, True, label=label)
    return surface, fit


def lines_of(row, kind, detail, small=True):
    """The lines one detail puts on a label with every detail ticked, as the label
    reads them: on a full label the first is the head and the rest are listed."""
    label = setup(EVERY)
    if small:
        return [line for d, line in labels._small_entries(row, kind, label) if d == detail]
    entries = labels._full_entries(row, kind, label)
    return [
        head if i == 0 else listed for i, (d, _, head, listed) in enumerate(entries) if d == detail
    ]


# --- making room ---------------------------------------------------------------


def test_a_crowded_label_brings_its_type_down_until_every_detail_fits():
    """Code 128 on the 89x36 mm label: at the size it grows its type to, the bars
    leave room for three lines; with four details ticked -- six lines under the tag --
    the type comes down and all of them are printed."""
    surface, fit = drawn(DRIVE, labels.PART, LARGE, setup(EVERY[:4], labels.BARCODE, False, LARGE))
    said = words(surface)
    for line in ("RH-K7Q2", "Boot disk", "Seagate ST-225", "20MB", "CHS 615/4/17", '5.25"'):
        assert line in said, line
    assert fit == labels.Fit((), ())
    roomy, _ = drawn(DRIVE, labels.PART, LARGE, setup(EVERY[:3], labels.BARCODE, False, LARGE))
    assert max(size for _, size in surface.said) < max(size for _, size in roomy.said)


def test_a_label_with_room_to_spare_keeps_the_type_it_grows_to():
    surface, _ = drawn(DRIVE, labels.PART, LARGE, setup(("tag", "name"), stock=LARGE))
    assert dict(surface.said)["RH-K7Q2"] > labels.TAG_PT * 1.5


def test_it_comes_no_further_down_than_the_tape_and_then_the_last_ones_go():
    surface, fit = drawn(DRIVE, labels.PART, LARGE, setup(EVERY, labels.BARCODE, False, LARGE))
    body = [size for text, size in surface.said if text != "RH-K7Q2"]
    assert min(body) >= labels.BODY_PT
    assert "kept" in fit.left
    assert "WORKSHOP" not in words(surface)


def test_on_the_tape_nothing_comes_down_that_was_not_already_there():
    """The tape's type is the size every other label's grows from, so it has nothing
    to give back: a crowded tape is set as it always was."""
    surface, fit = drawn(DRIVE, labels.PART, labels.SMALL, setup(EVERY, labels.BARCODE, False))
    body = [size for text, size in surface.said if text != "RH-K7Q2"]
    assert max(body) <= labels.BODY_PT
    assert fit.left


# --- saying what is left off ---------------------------------------------------


@pytest.mark.parametrize("stock", [labels.SMALL, LARGE, "niimbot-40x30", labels.FULL])
@pytest.mark.parametrize("codes", [labels.QR, labels.BARCODE])
def test_it_says_exactly_which_details_it_had_no_room_for(stock, codes):
    """Left off is nothing of it on the label; part is some of its lines and not
    others; anything else ticked is there whole."""
    small = not labels.full_layout(labels.MEDIA[stock])
    surface, fit = drawn(DRIVE, labels.PART, stock, setup(EVERY, codes, False, stock))
    said = words(surface)
    for detail in EVERY:
        lines = lines_of(DRIVE, labels.PART, detail, small)
        whole = [line for line in lines if line in said]
        begun = [line for line in lines if line.split()[0] in said]
        if detail in fit.left:
            assert not begun, detail
        elif detail in fit.part:
            # Some of its lines and not others, or a line wrapped over two with room
            # for the first.
            assert begun and len(whole) < len(lines), detail
        else:
            assert len(whole) == len(lines), detail
    assert not set(fit.left) & set(fit.part)


def test_a_detail_a_thing_does_not_have_is_not_said_to_be_left_off():
    _, fit = drawn(RECAP, labels.PROJECT, LARGE, setup(EVERY, stock=LARGE))
    assert not {"make", "serial", "kept"} & set(fit.left + fit.part)


# --- nothing ticked, and a location ---------------------------------------------


@pytest.mark.parametrize(
    ("kind", "row"),
    [(labels.PART, DRIVE), (labels.LOCATION, PLACE), (labels.PROJECT, RECAP)],
)
@pytest.mark.parametrize("stock", [labels.SMALL, LARGE, labels.FULL])
def test_nothing_ticked_is_the_code_alone(kind, row, stock):
    surface, fit = drawn(row, kind, stock, setup((), word=False, stock=stock))
    assert [text for text, _ in surface.said if text != "scan for details"] == []
    assert "qr" in surface.calls
    assert fit == labels.Fit((), ())
    worded, _ = drawn(row, kind, stock, setup((), word=True, stock=stock))
    assert [t for t, _ in worded.said if t != "scan for details"] == [labels.KIND_WORDS[kind]]


def test_a_location_follows_the_list_like_anything_else():
    surface, _ = drawn(PLACE, labels.LOCATION, labels.SMALL, setup(("name", "kept", "tag")))
    said = words(surface)
    assert largest(surface) == "Box 14"
    assert "SHELF 2" in said and "RH-9J2X" in said and "LOCATION" in said
    turned, _ = drawn(PLACE, labels.LOCATION, labels.SMALL, setup(("tag", "name")))
    assert largest(turned) == "RH-9J2X"
    assert "SHELF 2" not in words(turned)


def test_a_location_has_no_make_or_serial_and_its_specifications_are_on_a_full_label():
    small, _ = drawn(
        PLACE, labels.LOCATION, labels.SMALL, setup(("make", "serial", "specs"), word=False)
    )
    assert [t for t, _ in small.said] == []
    full, _ = drawn(
        PLACE, labels.LOCATION, labels.FULL, setup(("name", "specs"), stock=labels.FULL)
    )
    said = words(full)
    assert "Box 14" in said and "Box" in said.replace("Box 14", "") and "Floppy drives" in said
