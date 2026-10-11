"""Two labels, each set up for the printer and the job it is used for (MANUAL §13,
"Two labels, each set up for its job"; ADR-0037).

Each label is a set of settings: a name, a code, where it goes, the stock its PDF
is drawn on, what is on it and the face it is set in. The stock decides the shape:
a label on a 6x4 sheet is laid out as a full one, and on anything smaller as a
small one, whichever of the two it is.

What is drawn is read off a surface that notes what it was asked to draw and passes
it on, because the layout measures before it decides anything and a stand-in that
could not measure would be answering a different question.
"""

import html
import io
import json
import re

import pytest
from PIL import Image

from app import labels, printing, settings, surfaces
from conftest import log_out

AGENTS = "workshop-pi:key-one:dymo-11355:pdf,bench:key-two:niimbot-50x30:png"


@pytest.fixture
def agents(monkeypatch):
    monkeypatch.setenv("RHDB_PRINT_AGENTS", AGENTS)


def details(key, *ticked, word=True, order=None):
    """A label's details as the page posts them: every detail in its order, the
    ticked ones ticked, and the word up the end."""
    every = [k for k, _ in labels.DETAILS]
    order = list(order or ticked) + [k for k in every if k not in (order or ticked)]
    out: dict[str, object] = {
        f"label_{key}_details": order,
        f"label_{key}_details_on": list(ticked),
    }
    # Unticked, the box posts nothing; None here is taken out before the post.
    out[f"label_{key}_details_word"] = "1" if word else None
    return out


def save(client, **fields):
    """Post the Labels tab as the page does: every menu with its current answer,
    both lists as they stand, and these fields changed."""
    posted: dict[str, object] = {
        d.key: settings.value(d.key)
        for d in settings.DEFINITIONS
        if d.section == settings.LABELS and d.kind not in (settings.ORDER,)
    }
    for key in labels.LABELS:
        now = labels.setup(key)
        posted |= details(key, *now.details, word=now.word, order=labels.order_of(key))
    form = {k: v for k, v in (posted | fields).items() if v is not None}
    r = client.post("/settings/labels", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    settings.forget()


class Recording:
    """A surface that notes what it is asked to draw, and draws it."""

    def __init__(self, inner):
        self.inner = inner
        self.said: list[tuple[str, float]] = []
        self.fonts: dict[str, str] = {}
        self.xs: dict[str, float] = {}
        self.calls: list[str] = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def text(self, x, y, text, font, size):
        self.said.append((text, size))
        self.fonts.setdefault(text, font)
        self.xs.setdefault(text, x)
        self.inner.text(x, y, text, font, size)

    def text_centred(self, x, y, text, font, size):
        self.said.append((text, size))
        self.inner.text_centred(x, y, text, font, size)

    def vertical(self, x0, x1, y, text, font, size):
        self.calls.append("vertical")
        self.said.append((text, size))
        self.inner.vertical(x0, x1, y, text, font, size)

    def qr(self, *args):
        self.calls.append("qr")
        self.inner.qr(*args)

    def barcode(self, *args):
        self.calls.append("barcode")
        self.inner.barcode(*args)

    def frame(self, *args):
        self.calls.append("frame")
        self.inner.frame(*args)


def drawn(row, kind, stock, small=True, parts=()):
    """What the first label (or the second, `small=False`) draws on a stock."""
    media = labels.MEDIA[stock]
    surface = Recording(
        surfaces.RasterSurface(surfaces.blank(*labels.size_dots(media)), media["dpi"])
    )
    labels._draw(surface, media, row, list(parts), kind, small)
    return surface


def read(db, kind, aid, stock="niimbot-50x30", small=True):
    """What an item's label says, read from the register the way the label routes
    and the print queue read it."""
    source = printing.label_source(db, kind, aid)
    assert source is not None
    media = labels.MEDIA[stock]
    surface = Recording(
        surfaces.RasterSurface(surfaces.blank(*labels.size_dots(media)), media["dpi"])
    )
    labels._draw(
        surface, media, source.row, source.parts, kind, small, source.form_factor, source.spec_pairs
    )
    return words(surface)


def words(surface) -> str:
    return " ".join(text for text, _ in surface.said)


def largest(surface) -> str:
    return max(surface.said, key=lambda pair: pair[1])[0]


DRIVE = {
    "asset_id": "RH-0117",
    "name": "",
    "manufacturer": "Seagate",
    "model": "ST-225",
    "type": "storage",
    "specs": "Capacity: 20MB",
    "serial": "",
    "variant": "",
}


def page_size(pdf: bytes) -> tuple[int, int]:
    box = re.search(rb"/MediaBox \[\s*([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)\s*\]", pdf)
    assert box, "no page size"
    return round(float(box[3])), round(float(box[4]))


def mm_box(stock):
    w, h = labels.rotated_page(labels.MEDIA[stock])
    return round(w), round(h)


# --- the Labels tab ---------------------------------------------------------------


def test_the_labels_tab_has_a_group_for_each_label(client):
    page = client.get("/settings/labels").text
    legends = re.findall(r"<legend>([^<]+)</legend>", page)
    assert legends[:2] == ["Small label", "Full label"]
    for key in labels.LABELS:
        for field in ("name", "codes", "destination", "stock", "details", "type"):
            assert f'name="label_{key}_{field}"' in page, f"{key} {field}"


def test_an_installation_that_changes_nothing_has_the_labels_it_always_had(client):
    """QR codes, the tag, the name and the specifications with the word up the end,
    the label face, a PDF -- on the tape for the first and a 6x4 sheet for the
    second."""
    small, full = labels.setup("small"), labels.setup("full")
    assert (small.name, full.name) == ("Small label", "Full label")
    assert small.codes == full.codes == labels.QR
    assert small.details == full.details == ("tag", "name", "specs")
    assert small.word and full.word
    assert small.face == full.face == labels.LABEL_FACE
    assert (small.stock, full.stock) == (labels.SMALL, labels.FULL)
    assert settings.value("label_small_destination") == "pdf"
    assert settings.value("label_full_destination") == "pdf"


# --- name --------------------------------------------------------------------------


def test_a_labels_print_button_says_its_name(client, part):
    aid = part()["asset_id"]
    save(client, label_small_name="Drawer sticker", label_full_name="Shelf card")
    page = client.get(f"/parts/{aid}").text
    assert "Drawer sticker" in page and "Shelf card" in page
    legends = re.findall(r"<legend>([^<]+)</legend>", client.get("/settings/labels").text)
    assert legends[:2] == ["Drawer sticker", "Shelf card"]


def test_a_name_left_empty_is_the_name_it_started_with(client):
    save(client, label_small_name="Drawer sticker")
    save(client, label_small_name="  ")
    assert labels.setup("small").name == "Small label"


# --- code --------------------------------------------------------------------------


def test_each_label_carries_its_own_code(client):
    save(client, label_small_codes="code128", label_full_codes="qr")
    assert "barcode" in drawn(DRIVE, labels.PART, labels.SMALL).calls
    full = drawn(DRIVE, labels.PART, labels.FULL, small=False)
    assert "qr" in full.calls and "barcode" not in full.calls


@pytest.mark.parametrize("stock", sorted(labels.MEDIA))
def test_none_is_a_label_of_words_alone(client, stock):
    save(client, label_small_codes="none", label_full_codes="none")
    for small in (True, False):
        surface = drawn(DRIVE, labels.PART, stock, small)
        assert "qr" not in surface.calls and "barcode" not in surface.calls
        assert "RH-0117" in words(surface)


def test_none_gives_the_words_the_room_the_code_had(client):
    """With no code at the end of the label, the words start where the code was."""
    coded = drawn(DRIVE, labels.PART, labels.SMALL)
    save(client, label_small_codes="none")
    bare = drawn(DRIVE, labels.PART, labels.SMALL)
    assert bare.xs["RH-0117"] < coded.xs["RH-0117"] / 2


def test_none_is_offered_last(client):
    page = client.get("/settings/labels").text
    box = page.split('name="label_small_codes"', 1)[1].split("</select>", 1)[0]
    assert re.findall(r'<option value="([a-z0-9]+)"', box) == ["qr", "code128", "both", "none"]


# --- type --------------------------------------------------------------------------


def test_each_label_is_set_in_its_own_face(client, part):
    aid = part()["asset_id"]
    save(client, label_small_type="look", label_full_type="label")
    small = client.get(f"/parts/{aid}/label.pdf?small=1").content
    full = client.get(f"/parts/{aid}/label.pdf?small=0").content
    assert b"IBMPlexSans" in small and b"Audiowide" not in small
    assert b"Audiowide" in full and b"IBMPlex" not in full


# --- stock ---------------------------------------------------------------------------


@pytest.mark.parametrize("stock", sorted(labels.MEDIA))
def test_a_labels_stock_is_what_its_pdf_is_drawn_on(client, part, stock):
    aid = part()["asset_id"]
    save(client, label_full_stock=stock)
    assert page_size(client.get(f"/parts/{aid}/label.pdf?small=0").content) == mm_box(stock)


def test_the_stock_menu_offers_every_stock_there_is(client):
    page = client.get("/settings/labels").text
    box = page.split('name="label_small_stock"', 1)[1].split("</select>", 1)[0]
    assert set(re.findall(r'<option value="([a-z0-9-]+)"', box)) == set(labels.MEDIA)


@pytest.mark.parametrize("path", ["computers", "parts", "projects", "locations"])
def test_over_bluetooth_either_label_is_drawn_on_the_roll_the_printer_has(
    client, computer, part, path
):
    """Not on the label's own stock: the size Bluetooth label size gives, which is
    the picture the script fetches and sends, for either label."""
    if path == "computers":
        aid = computer()["asset_id"]
    elif path == "parts":
        aid = part()["asset_id"]
    else:
        aid = client.post(f"/api/{path}", json={"name": "Box 14", "kind": "box"}).json()["asset_id"]
    save(client, label_full_stock="full-6x4", label_bluetooth_media="niimbot-40x30")
    for small in (1, 0):
        r = client.get(f"/{path}/{aid}/label.png?media=niimbot-40x30&small={small}")
        assert r.status_code == 200, r.text
        assert Image.open(io.BytesIO(r.content)).size == labels.size_dots(
            labels.MEDIA["niimbot-40x30"]
        )


def test_sent_to_an_agent_a_label_is_drawn_on_the_agents_stock(client, part, agents):
    """The full label's own stock is the 6x4 sheet; the bench printer has a 50x30
    roll in it, and that is what comes out."""
    aid = part(manufacturer="Seagate", model="ST-225", type="storage")["asset_id"]
    save(client, label_full_stock="full-6x4")
    job = client.post(
        "/api/print/jobs", json={"agent": "bench", "kind": "part", "asset_id": aid, "label": "full"}
    ).json()
    assert (
        client.post(
            "/api/print/agent/claim", headers={"Authorization": "Bearer key-two"}
        ).status_code
        == 200
    )
    got = client.get(
        f"/api/print/agent/jobs/{job['id']}/label.png", headers={"Authorization": "Bearer key-two"}
    )
    assert got.status_code == 200, got.text
    assert Image.open(io.BytesIO(got.content)).size == labels.size_dots(
        labels.MEDIA["niimbot-50x30"]
    )


# --- the stock decides the shape --------------------------------------------------------


@pytest.mark.parametrize("stock", sorted(labels.MEDIA))
@pytest.mark.parametrize("small", [True, False])
def test_the_stock_decides_the_shape(client, stock, small):
    """A 6x4 sheet has room for the full layout, framed with the details listed
    down it; anything smaller is laid out as a small label, whichever label it is."""
    surface = drawn(DRIVE, labels.PART, stock, small)
    assert ("frame" in surface.calls) == (stock == labels.FULL)


def test_the_full_label_sent_to_a_niimbot_carries_the_full_labels_settings(client):
    save(
        client, label_small_codes="qr", label_full_codes="code128", **details("full", "name", "tag")
    )
    surface = drawn(DRIVE, labels.PART, "niimbot-50x30", small=False)
    assert "barcode" in surface.calls and "qr" not in surface.calls
    assert largest(surface) == "Seagate ST-225"


# --- what's on it ------------------------------------------------------------------------


@pytest.mark.parametrize("stock", [labels.SMALL, labels.FULL])
def test_the_first_detail_is_printed_largest(client, stock):
    """A name put first that will not fit on one line at more than the size of the
    words under it takes two, and stays the largest thing on the label."""
    small = stock != labels.FULL
    key = "small" if small else "full"
    assert largest(drawn(DRIVE, labels.PART, stock, small)) == "RH-0117"
    save(client, **details(key, "name", "tag", "specs"))
    surface = drawn(DRIVE, labels.PART, stock, small)
    head = max(size for _, size in surface.said)
    assert {t for t, size in surface.said if size == head} <= {
        "Seagate",
        "ST-225",
        "Seagate ST-225",
    }
    assert all(size < head for t, size in surface.said if "RH-0117" in t)


def test_the_details_follow_in_the_order_given(client):
    row = DRIVE | {"serial": "SN-4471"}
    save(client, **details("small", "tag", "serial", "name"))
    said = words(drawn(row, labels.PART, "niimbot-50x30"))
    assert said.index("RH-0117") < said.index("SN-4471") < said.index("Seagate")


def test_a_detail_not_ticked_is_not_printed(client):
    save(client, **details("small", "tag", "name"))
    assert "20MB" not in words(drawn(DRIVE, labels.PART, labels.SMALL))
    save(client, **details("small", "tag", "name", "specs"))
    assert "20MB" in words(drawn(DRIVE, labels.PART, labels.SMALL))


def test_the_serial_number_is_printed_when_it_is_ticked(client):
    row = DRIVE | {"serial": "SN-4471"}
    assert "SN-4471" not in words(drawn(row, labels.PART, labels.SMALL))
    save(client, **details("small", "tag", "name", "serial"))
    assert "SN-4471" in words(drawn(row, labels.PART, labels.SMALL))


def test_make_and_model_is_for_a_thing_with_a_name_of_its_own(client):
    save(client, **details("small", "tag", "name", "make"))
    named = words(drawn(DRIVE | {"name": "The bad-sector drive"}, labels.PART, "niimbot-50x30"))
    assert "bad-sector" in named and "Seagate ST-225" in named
    plain = words(drawn(DRIVE, labels.PART, "niimbot-50x30"))
    assert plain.count("Seagate") == 1, "said once, not twice"


def test_where_its_kept_is_the_path_it_is_in_on_the_day(client, db, part, computer):
    room = client.post("/api/locations", json={"name": "Workshop", "kind": "room"}).json()
    shelf = client.post(
        "/api/locations", json={"name": "Shelf 2", "kind": "shelf", "parent": room["asset_id"]}
    ).json()
    loose = part(location=shelf["asset_id"])["asset_id"]
    machine = computer(location=shelf["asset_id"])["asset_id"]
    fitted = part(computer_id=machine)["asset_id"]
    save(client, **details("small", "tag", "kept"))
    assert "WORKSHOP / SHELF 2" in read(db, labels.PART, loose)
    assert "WORKSHOP / SHELF 2" in read(db, labels.PART, fitted), "kept where its machine is"
    assert "WORKSHOP / SHELF 2" in read(db, labels.COMPUTER, machine)


def test_where_its_kept_is_printed_whatever_the_visible_tick_says(client, db, part):
    """The tick is about who reads the item's page; a label is read by whoever is
    holding the thing, and the owner chose to print it."""
    box = client.post("/api/locations", json={"name": "Box 14", "kind": "box"}).json()
    aid = part(location=box["asset_id"], location_public=False)["asset_id"]
    save(client, **details("small", "tag", "kept"))
    assert "BOX 14" in read(db, labels.PART, aid)


def test_a_thing_kept_nowhere_has_no_line_for_it(client, db, part):
    aid = part()["asset_id"]
    save(client, **details("small", "tag", "kept", "name"))
    assert "/" not in read(db, labels.PART, aid)


def test_a_detail_a_thing_does_not_have_is_not_there(client):
    """A project has no serial number and is kept nowhere: no blank lines for them."""
    project = {"asset_id": "RH-P001", "name": "Recap the PC1512", "status": "active"}
    save(client, **details("small", "tag", "serial", "kept", "name"))
    said = drawn(project, labels.PROJECT, labels.SMALL).said
    assert [t for t, _ in said if not t.strip()] == []
    assert "Recap the PC1512" in " ".join(t for t, _ in said)


def test_the_word_up_the_end_has_a_tick_of_its_own(client):
    assert "vertical" in drawn(DRIVE, labels.PART, labels.SMALL).calls
    save(client, **details("small", "tag", "name", "specs", word=False))
    assert "vertical" not in drawn(DRIVE, labels.PART, labels.SMALL).calls


def test_where_there_is_no_room_the_last_details_go(client):
    row = DRIVE | {
        "name": "Amstrad drive from the loft",
        "serial": "SN-4471-99812-AA",
        "specs": 'Capacity: 20MB | CHS: 615/4/17 | Form factor: 5.25" | Media: MFM | Speed: 3600 rpm',
    }
    save(client, **details("small", "tag", "name", "specs", "serial"))
    said = words(drawn(row, labels.PART, labels.SMALL))
    assert "RH-0117" in said and "Amstrad" in said
    assert "SN-4471" not in said, "the last detail is the one a crowded label loses"


def test_on_a_full_label_a_name_is_set_in_bold_and_the_rest_listed(client):
    row = DRIVE | {"serial": "SN-4471"}
    save(client, **details("full", "tag", "serial", "name", "specs"))
    surface = drawn(row, labels.PART, labels.FULL, small=False)
    texts = [t for t, _ in surface.said]
    assert surface.fonts["Seagate ST-225"] == surfaces.HEAD
    serial = next(t for t in texts if "SN-4471" in t)
    assert serial.startswith("• ") and surface.fonts[serial] == surfaces.BODY
    assert texts.index(serial) < texts.index("Seagate ST-225"), "in the order given"


def test_a_locations_label_follows_the_list(client):
    """Its tag, its name and where it is kept are details like any other's: what is
    ticked is printed, the first largest, and the word up the end only if it is
    ticked. A location has no serial number, so a list of that alone prints nothing."""
    place = {
        "asset_id": "RH-9J2X",
        "name": "Box 14",
        "kept": "Workshop / Shelf 2",
        "kind": "Box",
        "notes": "",
    }
    save(client, **details("small", "serial", word=False), label_small_codes="none")
    nothing = drawn(place, labels.LOCATION, labels.SMALL)
    assert words(nothing) == ""
    assert "qr" not in nothing.calls, "its code is the label's"
    save(client, **details("small", "name", "kept", "tag"), label_small_codes="none")
    surface = drawn(place, labels.LOCATION, labels.SMALL)
    said = words(surface)
    assert largest(surface) == "Box 14"
    assert "WORKSHOP / SHELF 2" in said and "RH-9J2X" in said and "LOCATION" in said


# --- saving the list -----------------------------------------------------------------------


def test_the_list_is_kept_in_the_order_it_was_posted(client):
    save(client, **details("small", "serial", "tag", order=["serial", "make", "tag", "name"]))
    assert labels.setup("small").details == ("serial", "tag")
    assert labels.order_of("small")[:4] == ["serial", "make", "tag", "name"]


def move(client, how):
    r = client.post("/settings/labels/move", data={"move": how}, follow_redirects=False)
    settings.forget()
    return r


def test_up_moves_a_detail_up_one_and_down_moves_it_down(client):
    """Without a script each press is a post of its own, kept as it is made; with
    one, the row moves in the page and Save keeps it, as any other change is kept."""
    move(client, "label_small_details:specs:up")
    assert labels.order_of("small")[:3] == ["tag", "specs", "name"]
    move(client, "label_small_details:tag:down")
    assert labels.order_of("small")[:3] == ["specs", "tag", "name"]
    assert labels.setup("small").details == ("specs", "tag", "name"), "the ticks go with them"


def test_moving_comes_back_to_the_list_it_moved_in(client):
    r = move(client, "label_full_details:name:down")
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/labels?saved=1#label_full_details"


def test_a_move_off_either_end_or_of_nothing_changes_nothing(client):
    before = labels.order_of("small")
    for how in (
        "label_small_details:tag:up",
        "label_small_details:nonesuch:up",
        "site_name:x:up",
        "junk",
    ):
        move(client, how)
    assert labels.order_of("small") == before


def test_the_moves_are_not_buttons_of_the_settings_form(client):
    """Enter in a box presses the form's first button. Were the first up a button
    of the form, Enter in Name would move a detail -- or, since the top row's up is
    disabled, do nothing at all."""
    page = client.get("/settings/labels").text
    form = page.split('id="settings-form"', 1)[1].split("</form>", 1)[0]
    for button in re.findall(r"<button [^>]*name=\"move\"[^>]*>", form):
        assert 'form="label-moves"' in button


def test_a_detail_that_was_not_offered_is_dropped(client):
    save(client, **details("small", "tag", "password", "name"))
    assert labels.setup("small").details == ("tag", "name")


def test_a_form_without_the_list_leaves_it_alone(client):
    """A tab posted without the list -- a script, a form from an older page -- has
    said nothing about it, and silence is not unticking everything."""
    save(client, **details("small", "serial"))
    client.post("/settings/labels", data={"label_small_codes": "both"})
    settings.forget()
    assert labels.setup("small").details == ("serial",)


def test_every_control_in_the_list_is_named(client):
    page = client.get("/settings/labels").text
    block = html.unescape(page.split('id="label_small_details"', 1)[1].split("</ol>", 1)[0])
    for _, words_ in labels.DETAILS:
        assert f'aria-label="move {words_} up"' in block
        assert f'aria-label="move {words_} down"' in block
        assert re.search(
            rf'<label class="check"><input type="checkbox" id="label_small_details-[a-z]+"[^>]*> {re.escape(words_)}</label>',
            block,
        ), words_


# --- labels for everything inside -------------------------------------------------------------


def test_labels_for_everything_inside_are_the_first_labels(client):
    box = client.post("/api/locations", json={"name": "Box 14", "kind": "box"}).json()["asset_id"]
    save(client, label_small_stock="niimbot-50x30")
    pdf = client.get(f"/locations/{box}/labels.pdf").content
    assert page_size(pdf) == mm_box("niimbot-50x30")


# --- where a label goes ------------------------------------------------------------------------


def test_each_print_button_says_which_label_it_is(client, part):
    aid = part()["asset_id"]
    page = client.get(f"/parts/{aid}").text
    for key, small in (("small", 1), ("full", 0)):
        button = re.search(rf'<a [^>]*data-label="{key}"[^>]*>', page)
        assert button, key
        assert f'href="/parts/{aid}/label.pdf?small={small}"' in button.group(0)
        assert f'data-asset="{aid}"' in button.group(0)


def test_each_label_has_its_own_destination(client, part, agents):
    save(client, label_small_destination="bluetooth", label_full_destination="agent:workshop-pi")
    page = client.get(f"/parts/{part()['asset_id']}").text
    data = json.loads(page.split('id="label-data">', 1)[1].split("</script>", 1)[0])
    assert data["defaults"] == {"small": "bluetooth", "full": "agent:workshop-pi"}


def test_this_browser_has_a_menu_for_each_label(client):
    page = client.get("/settings/labels").text
    box = page.split('id="device-box"', 1)[1].split("</fieldset>", 1)[0]
    assert 'id="device_destination_small"' in box and 'id="device_destination_full"' in box
    assert "Small label goes to" in box and "Full label goes to" in box


# --- the print queue ----------------------------------------------------------------------------


def test_a_print_job_says_which_label_it_is(client, part, agents):
    aid = part()["asset_id"]
    full = client.post(
        "/api/print/jobs", json={"agent": "bench", "kind": "part", "asset_id": aid, "label": "full"}
    ).json()
    first = client.post(
        "/api/print/jobs", json={"agent": "bench", "kind": "part", "asset_id": aid}
    ).json()
    assert (full["label"], first["label"]) == ("full", "small")


def test_a_label_that_is_not_one_of_the_two_is_refused(client, part, agents):
    aid = part()["asset_id"]
    r = client.post(
        "/api/print/jobs", json={"agent": "bench", "kind": "part", "asset_id": aid, "label": "huge"}
    )
    assert r.status_code == 422


def test_the_agent_is_handed_the_label_the_job_is_for(client, part, agents):
    aid = part(manufacturer="Seagate", model="ST-225", type="storage")["asset_id"]
    save(client, label_full_codes="code128")
    job = client.post(
        "/api/print/jobs", json={"agent": "bench", "kind": "part", "asset_id": aid, "label": "full"}
    ).json()
    claimed = client.post("/api/print/agent/claim", headers={"Authorization": "Bearer key-two"})
    assert claimed.status_code == 200
    got = client.get(
        f"/api/print/agent/jobs/{job['id']}/label.png", headers={"Authorization": "Bearer key-two"}
    )
    assert got.status_code == 200
    first = client.get(f"/parts/{aid}/label.png?media=niimbot-50x30&small=1").content
    second = client.get(f"/parts/{aid}/label.png?media=niimbot-50x30&small=0").content
    assert got.content == second != first


# --- the panel's picture --------------------------------------------------------------------------


def test_the_panels_picture_is_the_first_labels_pdf_on_its_own_stock(client, part):
    aid = part()["asset_id"]
    save(client, label_small_stock="niimbot-40x30")
    page = client.get(f"/parts/{aid}").text
    assert f'src="/parts/{aid}/label.png?media=niimbot-40x30"' in page


def test_a_visitor_sees_none_of_it(client, part):
    aid = part()["asset_id"]
    log_out(client)
    page = client.get(f"/parts/{aid}").text
    assert "data-label=" not in page and "label.pdf" not in page
