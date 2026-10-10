"""The Label panel shows the small label as it will print (MANUAL §13, "The label
as a picture").

Two print buttons and no picture meant printing a label to find out what it said,
and finding out that a name had been cut short by peeling it off the backing. The
picture is the label the printer is sent, drawn for wherever the small button is
going to send it.

Which printer a browser has chosen for itself is the browser's to know, so the swap
to that printer's picture happens in labelsend.js and is not tested here; what is
tested is everything the page hands the script to do it with.
"""

import io
import json
import re

import pytest
from PIL import Image

from app import labels, printing, settings
from conftest import log_out

AGENTS = (
    "workshop-pi:key-one:dymo-11355:pdf,"
    "bench:key-two:niimbot-50x30:png,"
    "shipping:key-three:full-6x4:png"
)

# Every page with a Label panel, as the path its label routes hang off and the kind
# a label is drawn for.
PAGES = [
    ("computers", labels.COMPUTER),
    ("parts", labels.PART),
    ("projects", labels.PROJECT),
    ("locations", labels.LOCATION),
]


@pytest.fixture
def agents(monkeypatch):
    monkeypatch.setenv("RHDB_PRINT_AGENTS", AGENTS)


@pytest.fixture
def thing(client, computer, part):
    """One thing of each kind with a Label panel, by the path its page is under."""

    def make(path):
        if path == "computers":
            return computer(manufacturer="Amstrad", model="PC1512")["asset_id"]
        if path == "parts":
            return part(manufacturer="Seagate", model="ST-225", type="storage")["asset_id"]
        if path == "projects":
            return client.post("/api/projects", json={"name": "Recap the PC1512"}).json()[
                "asset_id"
            ]
        return client.post("/api/locations", json={"name": "Box 14", "kind": "box"}).json()[
            "asset_id"
        ]

    return make


TABS = {
    "/settings": settings.APPEARANCE,
    "/settings/labels": settings.LABELS,
    "/settings/server": settings.SERVER,
}


def save(client, **fields):
    """Change settings the way the page does: each tab posting its own rows, with
    every switch already on posted on again, since a tick left out is a tick off."""
    for tab, section in TABS.items():
        mine = {k: v for k, v in fields.items() if settings.BY_KEY[k].section == section}
        if not mine:
            continue
        rows = [d for d in settings.DEFINITIONS if d.section == section]
        posted = {
            d.key: settings.value(d.key)
            for d in rows
            if d.kind != settings.SWITCH or settings.on(d.key)
        }
        r = client.post(tab, data=posted | mine)
        assert r.status_code in (200, 303), r.text[:300]
    settings.forget()


def label_panel(page: str) -> str:
    """The Label panel's markup, from its heading to the next panel."""
    m = re.search(r'<section class="panel[^"]*">\s*<header>\s*<h3>Label</h3>', page)
    if not m:
        return ""
    rest = page[m.end() :]
    stop = re.search(r'<section class="panel', rest)
    return rest[: stop.start()] if stop else rest


def picture(page: str) -> dict[str, str]:
    """The attributes of the picture in the Label panel."""
    tag = re.search(r"<img [^>]*class=\"lblpic\"[^>]*>", label_panel(page), re.S)
    assert tag, "no picture in the Label panel"
    return dict(re.findall(r'([\w-]+)=(?:"([^"]*)"|\'[^\']*\')', tag.group(0))) | {
        "pictures": re.search(r"data-pictures='([^']*)'", tag.group(0)).group(1)
    }


def pictures(page: str) -> dict[str, dict[str, object]]:
    """The map the script is handed: a picture for every place the label can go."""
    return json.loads(picture(page)["pictures"])


def png(client, src: str) -> bytes:
    r = client.get(src)
    assert r.status_code == 200, src
    assert r.headers["content-type"] == "image/png"
    return r.content


# --- the picture is there, over the buttons that print it ---------------------


@pytest.mark.parametrize("path,kind", PAGES)
def test_every_label_panel_shows_the_small_label_above_its_buttons(client, thing, path, kind):
    aid = thing(path)
    panel = label_panel(client.get(f"/{path}/{aid}").text)
    assert 'class="lblpic"' in panel
    assert panel.index('class="lblpic"') < panel.index('data-label="small"')
    assert f'src="/{path}/{aid}/label.png?media={labels.SMALL}"' in panel


@pytest.mark.parametrize("path,kind", PAGES)
def test_the_picture_is_named_for_what_it_shows(client, thing, path, kind):
    """It is content, not decoration: a screen reader is told what it is a picture
    of rather than reading out a filename."""
    aid = thing(path)
    assert picture(client.get(f"/{path}/{aid}").text)["alt"] == f"Small label for {aid}"


@pytest.mark.parametrize("path,kind", PAGES)
def test_a_visitor_is_shown_no_picture(client, thing, path, kind):
    """The panel is the owner's, and so is the picture. A location's page is only
    open to a visitor at all when Show locations is on."""
    aid = thing(path)
    save(client, public_locations="1")
    log_out(client)
    r = client.get(f"/{path}/{aid}")
    assert r.status_code == 200
    assert "label.png" not in r.text
    assert 'class="lblpic"' not in r.text


# --- without a script, it is the PDF's -----------------------------------------


@pytest.mark.parametrize("path,kind", PAGES)
def test_without_a_script_the_picture_is_of_the_pdf(client, thing, path, kind):
    """The markup's button is a link to the PDF, so the markup's picture is the
    PDF's label -- on the 51x19mm tape -- whatever the site sends a label to. It is
    the script that knows better, and only the script that says so (ADR-0026)."""
    aid = thing(path)
    save(client, label_small_destination="bluetooth")
    shown = picture(client.get(f"/{path}/{aid}").text)
    assert shown["src"] == f"/{path}/{aid}/label.png?media={labels.SMALL}"
    assert (int(shown["width"]), int(shown["height"])) == labels.size_dots(
        labels.MEDIA[labels.SMALL]
    )


@pytest.mark.parametrize("path,kind", PAGES)
def test_the_picture_is_the_size_its_markup_says(client, thing, path, kind):
    """So the panel keeps its shape while the picture is on its way, rather than
    jumping when it lands."""
    aid = thing(path)
    shown = picture(client.get(f"/{path}/{aid}").text)
    image = Image.open(io.BytesIO(png(client, shown["src"])))
    assert image.size == (int(shown["width"]), int(shown["height"]))


@pytest.mark.parametrize("path,kind", PAGES)
def test_the_picture_for_a_pdf_is_the_small_label_the_pdf_carries(client, thing, path, kind):
    """The same label drawn as the printer's dots rather than as a page: same stock,
    same layout, the small one."""
    aid = thing(path)
    drawn = pictures(client.get(f"/{path}/{aid}").text)["pdf"]
    assert drawn["src"] == f"/{path}/{aid}/label.png?media={labels.SMALL}"


# --- the script is handed the picture for everywhere the label can go ----------


def test_there_is_a_picture_for_every_place_the_small_button_can_send_it(client, thing, agents):
    """The same list the button and the settings page are given, from the same
    place: a printer with no picture would be a printer the panel cannot show."""
    aid = thing("parts")
    offered = {k for k, _ in settings.choices_for(settings.BY_KEY["label_small_destination"])}
    assert set(pictures(client.get(f"/parts/{aid}").text)) == offered
    assert offered == {"pdf", "bluetooth", "agent:workshop-pi", "agent:bench", "agent:shipping"}


@pytest.mark.parametrize("roll", ["niimbot-50x30", "niimbot-40x30"])
def test_over_bluetooth_the_picture_is_drawn_on_the_roll_the_printer_has(client, thing, roll):
    """The size Settings → Labels says the Bluetooth printer is loaded with, and the
    very file the script fetches to send it: the picture is not a likeness of the
    label but the label."""
    aid = thing("parts")
    save(client, label_bluetooth_media=roll)
    drawn = pictures(client.get(f"/parts/{aid}").text)["bluetooth"]
    assert drawn["src"] == f"/parts/{aid}/label.png?media={roll}"
    assert (drawn["w"], drawn["h"]) == labels.size_dots(labels.MEDIA[roll])


@pytest.mark.parametrize("path,kind", PAGES)
@pytest.mark.parametrize("agent,stock", [("bench", "niimbot-50x30"), ("workshop-pi", "dymo-11355")])
def test_sent_to_a_print_agent_the_picture_is_what_the_agent_prints_dot_for_dot(
    client, db, thing, agents, path, kind, agent, stock
):
    """Compared with the bytes the agent is handed for the same label, so a line the
    printer will cut short is cut short on the screen first."""
    aid = thing(path)
    drawn = pictures(client.get(f"/{path}/{aid}").text)[f"agent:{agent}"]
    assert png(client, drawn["src"]) == printing.label_bytes(db, kind, aid, stock, printing.PNG)


@pytest.mark.parametrize("path,kind", [("computers", labels.COMPUTER), ("parts", labels.PART)])
def test_anything_going_to_a_6x4_printer_is_pictured_as_the_full_layout_it_gets(
    client, db, thing, agents, path, kind
):
    """The stock decides the shape (ADR-0037): a 6x4 sheet has room for the full
    layout, so a label sent to one is laid out as a full label -- a part's as well as
    a machine's, which is the one change the rule makes -- and the picture is that,
    not the small layout stretched over a sheet."""
    aid = thing(path)
    drawn = pictures(client.get(f"/{path}/{aid}").text)["agent:shipping"]
    assert drawn["src"] == f"/{path}/{aid}/label.png?media=full-6x4"
    assert png(client, drawn["src"]) == printing.label_bytes(
        db, kind, aid, "full-6x4", printing.PNG
    )
