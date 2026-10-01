"""Browse as tiles or as a table (MANUAL §2, "The gallery").

The cards are for looking; a table is for running an eye down a long list. The
choice is two links carrying the whole view, so it works without script and a
table can be bookmarked or sent; it is remembered in a cookie like the sort, and a
link outranks the cookie. The table holds the same items in the same order, a
hundred to a page, each row a small picture, the tag, the name, the kind, the year
and -- for whoever is shown locations -- where it is."""

import json
import re

import pytest

from app import settings
from app.routers import gallery
from conftest import log_out

HTML = {"accept": "text/html"}


def switch(page):
    nav = re.search(r'<nav class="viewswitch"[^>]*>(.*?)</nav>', page, re.S)
    assert nav, "no Tiles / Table switch"
    return re.findall(r'<a href="([^"]*)"( aria-current="page")?>([^<]*)</a>', nav[1])


def table_rows(page):
    table = re.search(r'<table class="table stack gallerytable">(.*?)</table>', page, re.S)
    return re.findall(r"<tr>(.*?)</tr>", table[1], re.S)[1:] if table else []


def order(page):
    blob = re.search(r'<script type="application/json" id="index-data">(.*?)</script>', page, re.S)
    return [href for href, _ in json.loads(blob[1])["order"]]


def test_the_switch_offers_tiles_and_a_table_as_links_carrying_the_view(client, computer):
    computer()
    links = switch(client.get("/?sort=aid&disposed=1", headers=HTML).text)
    assert [(words.strip(), bool(cur)) for _, cur, words in links] == [
        ("Tiles", True),
        ("Table", False),
    ]
    for href, _, _ in links:
        assert "sort=aid" in href and "disposed=1" in href
    assert "layout=table" in links[1][0]


def test_the_table_holds_the_same_items_in_the_same_order(client, computer, part):
    for n in range(3):
        computer(name=f"Machine {n}")
        part(name=f"Card {n}")
    tiles = client.get("/?sort=name&layout=tiles", headers=HTML).text
    table = client.get("/?sort=name&layout=table", headers=HTML).text
    assert order(tiles) == order(table)
    firsts = [
        re.search(r'href="(/(?:computers|parts)/RH-[^"]+)"', row)[1] for row in table_rows(table)
    ]
    assert firsts == order(table)[: len(firsts)] and len(firsts) == 6


def test_a_table_page_holds_a_hundred_rows(client, computer, monkeypatch):
    assert gallery.TABLE_PAGE_SIZE == 100
    monkeypatch.setattr(gallery, "TABLE_PAGE_SIZE", 2)
    for n in range(3):
        computer(name=f"M{n}")
    page = client.get("/?sort=aid&layout=table", headers=HTML).text
    assert len(table_rows(page)) == 2
    assert '<nav class="pager" aria-label="Pages">' in page and "layout=table" in page


def test_a_row_leads_to_the_item_by_its_tag_and_its_name(client, computer):
    aid = computer(name="Lounge PC")["asset_id"]
    (row,) = table_rows(client.get("/?layout=table", headers=HTML).text)
    assert row.count(f'href="/computers/{aid}"') == 2 and "Lounge PC" in row


def test_a_row_s_picture_is_decoration_beside_its_name(client, computer):
    computer()
    (row,) = table_rows(client.get("/?layout=table", headers=HTML).text)
    assert re.search(r'<img class="rowthumb[^"]*" src="[^"]+" alt=""', row)


def test_a_disposed_item_says_so_in_its_row(client, db, computer):
    from app.models import Computer

    aid = computer()["asset_id"]
    db.get(Computer, aid).disposed = True
    db.commit()
    (row,) = table_rows(client.get("/?layout=table&disposed=1&sort=aid", headers=HTML).text)
    assert "Disposed" in row


def test_where_it_is_is_the_owner_s_and_a_fitted_part_says_whose(client, computer, part):
    cid = computer(name="PC", location="Loft")["asset_id"]
    part(name="Card", computer_id=cid)
    page = client.get("/?layout=table&sort=name", headers=HTML).text
    assert '<th scope="col">Where it is</th>' in page
    card = next(r for r in table_rows(page) if "Card" in r)
    assert "Loft" in card and f"where {cid} is" in re.sub(r"<[^>]+>", "", card)


def test_a_visitor_is_shown_where_only_while_show_locations_is_on(client, computer):
    computer(location="Loft")
    log_out(client)
    assert "Where it is" not in client.get("/?layout=table", headers=HTML).text
    settings.forget()


def test_the_choice_is_remembered_and_a_link_outranks_it(client, computer):
    computer()
    r = client.get("/?layout=table", headers=HTML)
    assert r.cookies.get("rhdb_layout") == "table"
    assert table_rows(client.get("/", headers=HTML).text)
    assert not table_rows(client.get("/?layout=tiles", headers=HTML).text)


def test_nothing_is_stored_until_the_choice_is_made(client, computer):
    computer()
    assert "rhdb_layout" not in client.get("/", headers=HTML).headers.get("set-cookie", "")


@pytest.mark.parametrize(
    "path", ["/for-sale?layout=table", "/browse?f=all&layout=table", "/?q=pc&layout=table"]
)
def test_every_page_that_is_browse_offers_the_table(client, computer, path):
    computer(name="PC", for_sale=True)
    page = client.get(path, headers=HTML).text
    assert switch(page) and '<table class="table stack gallerytable">' in page


def test_the_notice_names_every_choice_the_site_keeps(client):
    log_out(client)
    note = re.search(
        r'<div class="banner toast" id="cookienote".*?</div>',
        client.get("/login", headers=HTML).text,
        re.S,
    )
    assert note and "tiles or a table" in note[0] and "side rail" in note[0] and "sort" in note[0]
