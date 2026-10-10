"""The DYMO LabelWriter's larger labels, beside its 51×19 mm tape: 89×36 mm large
address labels (99012) and 70×54 mm multipurpose labels (99015) (MANUAL §13, "Two
labels, each set up for its job" and "Printing to a printer somewhere else").

Each is named by its DYMO number, as the tape is, because a size does not say what
prints it (ADR-0024). What every stock must do -- be drawn whole on both surfaces,
keep its bars to whole dots, take the shape its size gives it -- is held for every
stock by the tests that walk all of them; what is here is what these two are, and
that the manual names every stock there is.
"""

import re
from pathlib import Path

import pytest
from reportlab.lib.units import mm

from app import labels, printing, settings
from test_two_labels_each_set_up_for_its_job import page_size, save

MANUAL = Path(__file__).parents[2] / "MANUAL.md"

# The two as DYMO sells them: along the label and across it, in millimetres.
LARGER = {
    "dymo-99012": (89, 36, "large address"),
    "dymo-99015": (70, 54, "multipurpose"),
}


@pytest.mark.parametrize("stock", LARGER)
def test_each_is_a_stock_the_register_knows_at_its_own_size(stock):
    w, h, what = LARGER[stock]
    media = labels.MEDIA[stock]
    assert (media["w_mm"], media["h_mm"]) == (w, h)
    assert media["what"] == f"{w}×{h} mm {what} label (DYMO LabelWriter)"
    assert media["short"] == f"{w}×{h} mm"
    # A LabelWriter's: 300 dots an inch, and a head that reaches the whole label.
    assert media["dpi"] == 300
    assert media["dots"] == 0


@pytest.mark.parametrize("stock", LARGER)
def test_either_label_can_be_set_up_on_it(client, stock):
    for key in labels.LABELS:
        offered = dict(settings.choices_for(settings.BY_KEY[f"label_{key}_stock"]))
        assert offered[stock] == labels.MEDIA[stock]["what"]
    save(client, label_small_stock=stock, label_full_stock=stock)
    assert labels.setup("small").stock == labels.setup("full").stock == stock


@pytest.mark.parametrize("stock", LARGER)
def test_neither_is_offered_as_the_bluetooth_printer_s_size(stock):
    """Bluetooth is a Niimbot's, and a LabelWriter is not one."""
    offered = dict(settings.choices_for(settings.BY_KEY["label_bluetooth_media"]))
    assert stock not in offered


@pytest.mark.parametrize("stock", LARGER)
def test_a_print_agent_can_be_loaded_with_either(monkeypatch, stock):
    monkeypatch.setenv("RHDB_PRINT_AGENTS", f"office:key-one:{stock}:pdf")
    assert printing.agents()["office"].media == stock


@pytest.mark.parametrize("stock", LARGER)
def test_each_is_laid_out_as_a_small_label(stock):
    """Smaller than a 6x4 sheet, so the small label's shape: the code at one end and
    the words beside it (MANUAL §13, "The stock decides the shape")."""
    assert not labels.full_layout(labels.MEDIA[stock])


@pytest.mark.parametrize(
    ("stock", "dots"), [("dymo-99012", (1051, 425)), ("dymo-99015", (827, 638))]
)
def test_its_picture_is_the_label_in_the_labelwriter_s_dots(stock, dots):
    assert labels.size_dots(labels.MEDIA[stock]) == dots


@pytest.mark.parametrize("stock", LARGER)
def test_its_pdf_is_turned_the_way_the_labelwriter_feeds_it(client, part, stock):
    """Short side first, as the tape's is: the label goes through the printer across
    the head and then along the roll."""
    w, h, _ = LARGER[stock]
    aid = part(type="storage", manufacturer="Seagate", model="ST-225")["asset_id"]
    save(client, label_small_stock=stock)
    pdf = client.get(f"/parts/{aid}/label.pdf?small=1").content
    assert page_size(pdf) == (round(h * mm), round(w * mm))


def test_the_manual_names_every_stock_an_agent_can_be_loaded_with():
    """The list an agent's stock is chosen from, which every new stock has to join."""
    text = MANUAL.read_text(encoding="utf-8")
    start = text.index("Each entry is `name:key:stock:format`.")
    named = text[start : text.index("never reuse one.", start)]
    assert set(re.findall(r"`([a-z0-9]+-[a-z0-9]+)`", named)) == set(labels.MEDIA)
