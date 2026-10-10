"""Each label pictured beside its settings, and drawn again as they change (MANUAL
§13, "Seeing it as you set it up").

The picture is drawn by the server from what is on the page -- read the way Save
reads it, and kept nowhere -- for an example rather than for anything in the
collection, on the stock the label goes to. Which settings are on the page is the
script's to send, and asking again as they change is the script's to do; what is
tested here is everything the page hands the script and everything the server does
with what it is sent. That the picture follows the page and not the browser's own
choice of printer is a fact about the script, and was checked in a browser.
"""

import html
import io
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from PIL import Image

from app import ids, labelpreview, labels, settings
from app.db import SessionLocal
from app.models import Setting, Thing
from conftest import as_viewer, log_out
from test_page_width import rules_by_media
from test_site_chrome import COMPONENTS
from test_two_labels_each_set_up_for_its_job import details, save

AGENTS = "workshop-pi:key-one:dymo-11355:pdf,bench:key-two:niimbot-50x30:png"
PREVIEW = "/settings/labels/preview.png"
KINDS = [kind for kind, _ in labelpreview.KINDS]


@pytest.fixture
def agents(monkeypatch):
    monkeypatch.setenv("RHDB_PRINT_AGENTS", AGENTS)


class Tags(HTMLParser):
    """Every element on a page that has an id, by id -- its tag and its attributes --
    and the ids in the order the page has them."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.by_id: dict[str, dict[str, str]] = {}
        self.order: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        found = {k: v or "" for k, v in attrs}
        if "id" in found:
            self.by_id[found["id"]] = {"tag": tag} | found
            self.order.append(found["id"])


def page(client):
    r = client.get("/settings/labels")
    assert r.status_code == 200
    return r.text


def inside(text, tag, ident):
    """What is inside the element with this id."""
    m = re.search(rf'<{tag}\b[^>]*\bid="{ident}"[^>]*>(.*?)</{tag}>', text, re.S)
    assert m, f"no <{tag} id={ident}>"
    return m.group(1)


def sent(key, **changed):
    """One label's settings as the page has them, with these changed: what the script
    sends for its picture."""
    now = labels.setup(key)
    out: dict[str, object] = {
        name: settings.value(name)
        for name in (
            f"label_{key}_codes",
            f"label_{key}_destination",
            f"label_{key}_stock",
            f"label_{key}_type",
            "label_bluetooth_media",
        )
    }
    out |= details(key, *now.details, word=now.word, order=labels.order_of(key))
    out |= changed
    return {k: v for k, v in out.items() if v is not None}


def picture(client, key, kind=None, **fields):
    """The picture the page asks for: one label, for one sort of example, drawn from
    the settings sent with it."""
    query = {"label": key, "kind": kind or labelpreview.STARTS[key], **fields}
    r = client.get(PREVIEW, params=query)
    assert r.status_code == 200, r.text[:200]
    assert r.headers["content-type"] == "image/png"
    return r.content


def size(png):
    return Image.open(io.BytesIO(png)).size


# --- beside each label's settings --------------------------------------------


def test_each_label_has_a_picture_of_it_among_its_settings(client):
    tags = Tags(page(client))
    for key in labels.LABELS:
        img = tags.by_id[f"preview_{key}"]
        assert img["tag"] == "img"
        assert img["src"] == f"{PREVIEW}?label={key}&kind={labelpreview.STARTS[key]}"
    # In the label's own group, between its legend and the next label's.
    at = tags.order.index
    assert at("preview_small") < at("label_small_name") < at("label_small_type")
    assert at("label_small_type") < at("preview_full") < at("label_full_name")


def test_the_picture_says_what_it_is_a_picture_of(client):
    tags = Tags(page(client))
    assert tags.by_id["preview_small"]["alt"] == "Small label for an example part"
    assert tags.by_id["preview_full"]["alt"] == "Full label for an example machine"


@pytest.mark.parametrize("key", labels.LABELS)
@pytest.mark.parametrize("kind", KINDS)
def test_it_is_the_label_itself_drawn_for_an_example_with_nothing_in_the_collection(
    client, key, kind
):
    """Drawn by the code that draws the label, so it is the label and not a likeness
    of it; for an example, so a register with nothing in it yet has a picture."""
    with SessionLocal() as db:
        assert db.query(Thing).count() == 0
    example = labelpreview.EXAMPLES[kind]
    expected = labels.render_png(
        example.row,
        example.parts,
        kind,
        labels.MEDIA[labels.setup(key).stock],
        small=key == labels.LABELS[0],
        form_factor=example.form_factor,
        spec_pairs=example.spec_pairs,
    )
    assert picture(client, key, kind) == expected


# --- drawn again as the settings change, before anything is saved -------------


def test_it_is_drawn_from_the_settings_on_the_page_and_drawing_it_keeps_nothing(client):
    saved = picture(client, "small")
    with SessionLocal() as db:
        before = {s.name: s.value for s in db.query(Setting).all()}
    unsaved = picture(client, "small", **sent("small", label_small_codes="none"))
    assert unsaved != saved
    settings.forget()
    with SessionLocal() as db:
        assert {s.name: s.value for s in db.query(Setting).all()} == before
    assert settings.value("label_small_codes") == "qr"
    assert picture(client, "small") == saved


# Each of the changes the manual names: a tick, a move, another code, another stock,
# another face -- and the word up the end, which has a tick of its own.
CHANGES = {
    "a detail ticked": lambda k: details(k, "serial", "tag", "name", "specs"),
    "a detail moved": lambda k: details(k, "name", "tag", "specs"),
    "the word unticked": lambda k: details(k, "tag", "name", "specs", word=False),
    "no code": lambda k: {f"label_{k}_codes": "none"},
    "both codes": lambda k: {f"label_{k}_codes": "both"},
    "another stock": lambda k: {f"label_{k}_stock": "niimbot-40x30"},
    "another face": lambda k: {f"label_{k}_type": "look"},
}


@pytest.mark.parametrize("key", labels.LABELS)
@pytest.mark.parametrize("change", list(CHANGES))
def test_before_it_is_saved_the_picture_is_the_label_save_keeps(client, key, change):
    changed = CHANGES[change](key)
    unsaved = picture(client, key, **sent(key, **changed))
    assert unsaved != picture(client, key)
    save(client, **changed)
    assert picture(client, key) == unsaved


# --- an example with every detail its sort of thing can have -----------------


def test_the_example_s_tag_is_one_the_register_never_issues(client):
    tag = labelpreview.TAG
    assert tag == "RH-DEMO"
    # The shape of a tag, so it is laid out as one...
    assert ids.exact_tag(tag) == tag
    # ...but never issued: a new tag is four of an alphabet with no O in it, and an
    # old one is four digits.
    tail = tag.removeprefix(ids.PREFIX)
    assert set(tail) - set(ids.ALPHABET)
    assert not tail.isdigit()
    assert {example.row["asset_id"] for example in labelpreview.EXAMPLES.values()} == {tag}
    # What its code holds opens nothing.
    scanned = urlsplit(labels.item_url(tag)).path
    assert client.get(scanned, follow_redirects=True).status_code == 404


# What each sort of example has nothing to print for, on each label: a machine's
# specifications are its build, which a small label has no room for; a project has
# no make and model, no serial number and nowhere it is kept; and a location has no
# make and model or serial number, and its specifications only on a full label
# (MANUAL §13).
LACKS = {
    (labels.LOCATION, "small"): {"make", "serial", "specs"},
    (labels.LOCATION, "full"): {"make", "serial"},
    (labels.COMPUTER, "small"): {"specs"},
    (labels.COMPUTER, "full"): set(),
    (labels.PART, "small"): set(),
    (labels.PART, "full"): set(),
    (labels.PROJECT, "small"): {"make", "serial", "kept"},
    (labels.PROJECT, "full"): {"make", "serial", "kept"},
}


@pytest.mark.parametrize(("kind", "key"), list(LACKS))
def test_the_example_has_every_detail_its_sort_of_thing_can_have(client, kind, key):
    """Each detail alone, against none at all: a detail the example carries puts
    something on the label, whatever room the others would have left it."""
    bare = picture(client, key, kind, **sent(key, **details(key)))
    for detail, _ in labels.DETAILS:
        alone = picture(client, key, kind, **sent(key, **details(key, detail)))
        assert (alone != bare) == (detail not in LACKS[kind, key]), detail


@pytest.mark.parametrize("key", labels.LABELS)
def test_a_location_s_label_follows_the_list_and_its_word_tick(client, key):
    shown = picture(client, key, labels.LOCATION)
    unworded = details(key, *labels.setup(key).details, word=False)
    assert picture(client, key, labels.LOCATION, **sent(key, **unworded)) != shown
    moved = details(key, "name", "kept", "tag")
    assert picture(client, key, labels.LOCATION, **sent(key, **moved)) != shown


@pytest.mark.parametrize("key", labels.LABELS)
def test_each_sort_of_example_is_drawn_as_that_sort_of_thing(client, key):
    drawn = {kind: picture(client, key, kind) for kind in KINDS}
    assert len(set(drawn.values())) == len(KINDS)


def test_a_menu_under_the_picture_says_what_sort_of_thing_the_example_is(client):
    text = page(client)
    tags = Tags(text)
    for key in labels.LABELS:
        menu = tags.by_id[f"preview_{key}_kind"]
        assert menu["tag"] == "select"
        # Not one of the settings: it has no name, so it posts nothing for Save to keep.
        assert "name" not in menu
        assert f'<label for="preview_{key}_kind">Example</label>' in text
        offered = inside(text, "select", f"preview_{key}_kind")
        assert re.findall(r'<option value="(\w+)"', offered) == KINDS
        assert re.findall(r">([^<]+)</option>", offered) == [
            "Machine",
            "Part",
            "Project",
            "Location",
        ]
        assert f'<option value="{labelpreview.STARTS[key]}" selected>' in offered
        assert tags.order.index(f"preview_{key}") < tags.order.index(f"preview_{key}_kind")


def test_the_first_label_starts_on_a_part_and_the_second_on_a_machine(client):
    assert labelpreview.STARTS == {"small": labels.PART, "full": labels.COMPUTER}
    tags = Tags(page(client))
    assert tags.by_id["preview_small"]["src"].endswith("&kind=part")
    assert tags.by_id["preview_full"]["src"].endswith("&kind=computer")


# --- on the stock the label goes to -------------------------------------------

# Where a label goes, and the stock that puts it on with these settings: its own
# Stock a 6x4 sheet, the Bluetooth printer loaded with 40x30, and the agents' own.
GOES = [
    ("pdf", "full-6x4"),
    ("bluetooth", "niimbot-40x30"),
    ("agent:workshop-pi", "dymo-11355"),
    ("agent:bench", "niimbot-50x30"),
]


def going(key, goes):
    return {
        f"label_{key}_destination": goes,
        f"label_{key}_stock": "full-6x4",
        "label_bluetooth_media": "niimbot-40x30",
    }


@pytest.mark.parametrize("key", labels.LABELS)
@pytest.mark.parametrize(("goes", "stock"), GOES)
def test_it_is_drawn_on_the_stock_the_label_goes_to(client, agents, key, goes, stock):
    dots = labels.size_dots(labels.MEDIA[stock])
    # Sent from the page, before it is saved...
    assert size(picture(client, key, **sent(key, **going(key, goes)))) == dots
    # ...and as saved, where the markup says how big it is before it arrives.
    save(client, **going(key, goes))
    assert size(picture(client, key)) == dots
    img = Tags(page(client)).by_id[f"preview_{key}"]
    assert (int(img["width"]), int(img["height"])) == dots


@pytest.mark.parametrize("key", labels.LABELS)
@pytest.mark.parametrize(("goes", "stock"), GOES)
def test_a_line_under_the_picture_names_the_stock(client, agents, key, goes, stock):
    save(client, **going(key, goes))
    text = page(client)
    assert (
        inside(text, "figcaption", f"preview_{key}_stock").strip() == (labels.MEDIA[stock]["what"])
    )
    tags = Tags(text)
    assert tags.order.index(f"preview_{key}") < tags.order.index(f"preview_{key}_stock")


def test_the_page_hands_the_script_every_stock_and_where_each_agent_prints(client, agents):
    """So the line under the picture can name the stock as the settings change, and
    the picture be given its size before it arrives."""
    island = inside(page(client), "script", "label-preview-data")
    data = json.loads(island)
    assert data["media"] == {
        name: {
            "what": media["what"],
            "w": labels.size_dots(media)[0],
            "h": labels.size_dots(media)[1],
        }
        for name, media in labels.MEDIA.items()
    }
    assert data["agents"] == {"agent:workshop-pi": "dymo-11355", "agent:bench": "niimbot-50x30"}
    assert data["kinds"] == {
        "computer": "machine",
        "part": "part",
        "project": "project",
        "location": "location",
    }


# --- where it sits, and with no script ---------------------------------------


def test_on_a_phone_it_is_at_the_top_and_on_a_wide_screen_it_stays_in_view_beside(client):
    """At the top of the group in the page's own order, so a phone has it there with
    nothing moved; beside the settings on a wide screen, and held in view while the
    list under them is worked down."""
    tags = Tags(page(client))
    at = tags.order.index
    for key in labels.LABELS:
        assert at(f"preview_{key}") < at(f"label_{key}_name")
    wide = {
        head: body
        for queries, head, body in rules_by_media(COMPONENTS)
        if any(q.startswith("(min-width:") for q in queries)
    }
    assert "grid-template-columns" in wide[".lblset"]
    assert re.search(r"position:\s*sticky", wide[".lblset > .lblprev"])


def test_with_no_script_it_is_the_label_as_saved_and_save_draws_it_again(client):
    tags = Tags(page(client))
    src = tags.by_id["preview_small"]["src"]
    before = client.get(src)
    # Asked for again every time the page is: the address does not change when the
    # settings do, and a picture kept from before a save would be the old label.
    assert before.headers["cache-control"] == "no-store"
    save(client, label_small_codes="none")
    again = Tags(page(client))
    assert again.by_id["preview_small"]["src"] == src
    after = client.get(src).content
    assert after != before.content
    assert after == picture(client, "small", **sent("small"))
    # The menu needs a script to do anything, and is not offered without one.
    for key in labels.LABELS:
        assert "hidden" in again.by_id[f"preview_{key}_example"]


# --- who may see it, and what it will not draw --------------------------------


def test_the_picture_is_behind_the_login_like_the_page_it_is_on(client):
    log_out(client)
    r = client.get(PREVIEW, params={"label": "small", "kind": "part"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_a_viewer_is_not_shown_it_either(client):
    as_viewer(client)
    r = client.get(PREVIEW, params={"label": "small", "kind": "part"}, follow_redirects=False)
    assert r.status_code != 200
    assert r.headers.get("content-type") != "image/png"


@pytest.mark.parametrize(
    "query",
    [
        {"label": "middle", "kind": "part"},
        {"label": "small", "kind": "drawer"},
        {"kind": "part"},
        {"label": "small"},
    ],
)
def test_a_label_or_an_example_there_is_not_is_not_found(client, query):
    assert client.get(PREVIEW, params=query).status_code == 404


def test_a_setting_the_page_could_not_have_sent_is_drawn_as_saved(client):
    shown = picture(client, "small")
    nonsense = sent(
        "small",
        label_small_codes="hologram",
        label_small_stock="a4-sheet",
        label_small_type="comic-sans",
        label_small_destination="carrier-pigeon",
        label_small_details=["colour"],
    )
    assert picture(client, "small", **nonsense) == shown


# --- saying what there is no room for -------------------------------------------

# The first label on the 51x19 mm tape with every detail ticked and a barcode under
# the words: room for the tag and a line or two, whatever the type is brought to.
CROWDED = {"label_small_codes": "code128"}


def crowded(key="small"):
    return CROWDED | details(key, "tag", "name", "make", "specs", "serial", "kept")


def room_line(text, key):
    return html.unescape(inside(text, "p", f"preview_{key}_room").strip())


def test_a_line_under_the_picture_says_what_the_label_has_no_room_for(client):
    save(client, **crowded())
    text = page(client)
    said = room_line(text, "small")
    assert said.startswith("No room for ")
    named = dict(labels.DETAILS)
    assert named["kept"] in said, "the last details are the ones that go"
    assert "hidden" not in Tags(text).by_id["preview_small_room"]
    at = Tags(text).order.index
    assert at("preview_small") < at("preview_small_room") < at("preview_small_kind")


def test_with_room_for_everything_the_line_says_nothing(client):
    text = page(client)
    for key in labels.LABELS:
        assert room_line(text, key) == ""
        assert "hidden" in Tags(text).by_id[f"preview_{key}_room"]
        assert Tags(text).by_id[f"preview_{key}_room"]["aria-live"] == "polite"


def test_the_line_is_asked_again_with_the_picture_from_the_settings_on_the_page(client):
    """Before anything is saved, as the picture is."""
    r = client.get(
        "/settings/labels/preview.json",
        params={"label": "small", "kind": "part", **sent("small", **crowded())},
    )
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["room"].startswith("No room for ")
    settings.forget()
    assert settings.value("label_small_codes") == "qr", "and nothing is kept"
    plain = client.get("/settings/labels/preview.json", params={"label": "small", "kind": "part"})
    assert plain.json() == {"room": ""}


def test_the_line_is_behind_the_login_and_asks_only_of_a_label_and_an_example_there_are(client):
    for query in ({"label": "middle", "kind": "part"}, {"label": "small", "kind": "drawer"}):
        assert client.get("/settings/labels/preview.json", params=query).status_code == 404
    log_out(client)
    r = client.get(
        "/settings/labels/preview.json",
        params={"label": "small", "kind": "part"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
