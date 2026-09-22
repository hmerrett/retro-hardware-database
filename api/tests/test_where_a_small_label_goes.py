"""The print button's destination: a PDF, a printer on the queue, or Bluetooth.

A label is only useful where there is a printer, and which printer is within reach
is a fact about the thing you are holding rather than about the collection -- so
the site sets a default and a device may overrule it (ADR-0023, ADR-0026).

The overruling itself is in the browser and is not tested here; what is tested is
everything the browser is given to do it with, because a menu offering a printer
that does not exist, or a page that never mentions which item its button is for,
is a fault the browser cannot make up for.
"""

import json

import pytest

from app import settings

AGENTS = "workshop-pi:key-one:dymo-11355:pdf,bench:key-two:niimbot-50x30:png"


@pytest.fixture
def agents(monkeypatch):
    monkeypatch.setenv("RHDB_PRINT_AGENTS", AGENTS)


def island(page):
    """The data the label script is handed."""
    body = page.split('<script type="application/json" id="label-data">', 1)[1]
    return json.loads(body.split("</script>", 1)[0])


def save(client, **fields):
    posted = {d.key: settings.value(d.key) for d in settings.DEFINITIONS if d.kind != "switch"}
    r = client.post("/settings", data=posted | fields)
    assert r.status_code in (200, 303), r.text[:300]
    settings.forget()


# --- what is on offer --------------------------------------------------------


def test_the_destinations_are_a_pdf_bluetooth_and_every_printer_configured(client, agents):
    """The list is worked out rather than written down: the printers come from the
    environment, so a list in the template could only ever be out of date."""
    said = dict(settings.choices_for(settings.BY_KEY["label_destination"]))
    assert "pdf" in said
    assert "bluetooth" in said
    assert "agent:workshop-pi" in said
    assert "agent:bench" in said


def test_a_printer_that_is_not_configured_is_not_offered(client):
    said = dict(settings.choices_for(settings.BY_KEY["label_destination"]))
    assert [k for k in said if k.startswith("agent:")] == []


def test_a_printer_says_what_stock_is_in_it(client, agents):
    """So a menu of printers is a menu of what will actually come out, rather than
    a list of names somebody has to remember the tape sizes for.

    In as few words as will do: a list of printers is read to find one, and the
    sentence that describes a stock belongs where a stock is being described rather
    than in every line of a menu."""
    said = dict(settings.choices_for(settings.BY_KEY["label_destination"]))
    assert said["agent:workshop-pi"] == "workshop-pi 51×19 mm"
    assert said["agent:bench"] == "bench 50×30 mm"


def test_the_bluetooth_stock_is_offered_from_the_stocks_that_exist(client):
    """And only the Niimbot ones: a Bluetooth printer is not going to be handed a
    6x4 inch sheet."""
    said = dict(settings.choices_for(settings.BY_KEY["label_bluetooth_media"]))
    assert set(said) == {"niimbot-50x30", "niimbot-40x30"}


# --- saving it ---------------------------------------------------------------


def test_the_default_can_be_set_to_a_configured_printer(client, agents):
    save(client, label_destination="agent:workshop-pi")
    assert settings.value("label_destination") == "agent:workshop-pi"


def test_a_destination_that_is_not_on_offer_is_refused(client, agents):
    """The same reading `clean` takes of every other menu: an answer that was not
    offered did not come from this page."""
    save(client, label_destination="agent:nonesuch")
    assert settings.value("label_destination") == "pdf"


def test_a_fresh_install_hands_out_a_pdf(client):
    """Which is what the button did before there was anywhere else for it to go, so
    an installation that upgrades and changes nothing notices nothing."""
    assert settings.value("label_destination") == "pdf"


# --- what a page is given ----------------------------------------------------


@pytest.mark.parametrize("kind", ["computers", "parts", "projects"])
def test_every_item_page_says_what_its_button_is_for(client, computer, part, kind, agents):
    """The button is a link to a PDF in the markup. To send it anywhere else the
    script has to know which item it is looking at, and saying so in the markup is
    the only way it can -- there is nothing in a URL ending label.pdf that names the
    kind of thing it belongs to."""
    if kind == "computers":
        aid = computer()["asset_id"]
    elif kind == "parts":
        aid = part()["asset_id"]
    else:
        aid = client.post("/api/projects", json={"name": "Recap"}).json()["asset_id"]
    page = client.get(f"/{kind}/{aid}").text
    assert f'data-asset="{aid}"' in page
    assert f'data-kind="{kind[:-1]}"' in page
    assert "/static/labelsend.js" in page


def test_the_page_is_told_where_labels_go(client, part, agents):
    page = client.get(f"/parts/{part()['asset_id']}").text
    data = island(page)
    assert data["default"] == "pdf"
    assert ["agent:workshop-pi", "workshop-pi 51×19 mm"] in data["destinations"]
    assert data["bluetoothMedia"] == "niimbot-50x30"


def test_the_settings_page_and_an_item_page_are_told_the_same_thing(client, part, agents):
    """One answer, read twice. The menu that chooses a destination and the button
    that acts on the choice cannot disagree about what exists."""
    item = island(client.get(f"/parts/{part()['asset_id']}").text)
    page = island(client.get("/settings").text)
    assert item == page


def test_the_button_still_links_to_a_pdf(client, part, agents):
    """With no script, or on a device that has chosen nothing, pressing it gets the
    file it has always got. The destination is something the script does instead,
    not something the markup promises."""
    aid = part()["asset_id"]
    page = client.get(f"/parts/{aid}").text
    assert f'href="/parts/{aid}/label.pdf?small=1"' in page


def test_the_device_menu_is_hidden_until_the_script_fills_it(client):
    """A menu that is nothing but script says nothing useful before the script has
    run, and a menu that forgets what you tell it is worse than no menu."""
    page = client.get("/settings").text
    assert 'id="device-box" hidden>' in page
    # And it is styled as the boxes above it are. The settings rules were once
    # scoped to `form.edit`, and this box is a fieldset rather than a form -- so its
    # control took none of them and sat in the middle of the page looking like a
    # different website.
    assert 'class="fieldset narrow" id="device-box"' in page


def test_nothing_about_the_destination_is_written_inline(client, part, agents):
    """The content policy is `self` throughout and the suite holds the markup to it
    (ADR-0021). A data island is how a page hands a value to a script."""
    page = client.get(f"/parts/{part()['asset_id']}").text
    assert 'type="application/json" id="label-data"' in page
    assert "onclick=" not in page
