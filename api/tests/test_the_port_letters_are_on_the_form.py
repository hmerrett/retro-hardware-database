"""The letters the Ports box takes are printed under it (MANUAL.md section 9,
"Quick entry").

They were a hint under the box until the pages were made quieter, when every hint
went into a tooltip -- and a tooltip is not shown on a touchscreen, is not reached
by the Tab key, and is the wrong place for anything needed to answer the question
at all (interface-text). Nobody remembers that O is a PS/2 mouse.
"""

import re

import pytest

from app import entry


def legend(page):
    """The key printed under the Ports box, as words rather than as markup."""
    found = re.search(r'<p class="hint portkey" id="spec_ports-legend">(.*?)</p>', page, re.S)
    assert found, "the Ports box has no key printed under it"
    return " ".join(re.sub(r"<[^>]+>", "", found.group(1)).split())


@pytest.mark.parametrize("kind", ["io", "sound"])
def test_every_letter_the_box_reads_is_printed_under_it(client, kind):
    key = legend(client.get(f"/parts/new?type={kind}").text)
    for letter, name in entry.PORT_CODES:
        assert f"{letter} {name}" in key, f"{letter} for {name} is missing"


@pytest.mark.parametrize("kind", ["io", "sound"])
def test_the_box_is_described_by_them(client, kind):
    """For a screen reader too: the key is the box's description, not a paragraph
    that happens to sit near it."""
    page = client.get(f"/parts/new?type={kind}").text
    assert re.search(
        r'<input id="spec_ports" name="spec_ports"[^>]*aria-describedby="spec_ports-legend"', page
    )


def test_they_are_there_when_a_card_is_edited_as_well(client, part):
    aid = part(type="io", manufacturer="Generic", model="IDE/FDD/SIO")["asset_id"]
    assert legend(client.get(f"/parts/{aid}/edit").text)
