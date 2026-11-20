"""The numbers page opens whatever the counts hold.

A count on a board's slots, sockets and ports, or on a machine's chips, is a
nullable column, and so are a socket's type and a part's. Nothing the app writes
leaves one empty, but a restored dump or a row written by hand can -- and SQL adds
a group whose counts are all NULL up to NULL. The figures read those sums and
names straight off the columns, so a NULL ranked against a number, or a missing
type put into a link, was a TypeError and a numbers page that would not open.
"""

from datetime import date

from sqlalchemy import text

from app import main
from conftest import content


def figures(db):
    return {f["k"]: f for f in main._facts(db, main._collection_stats(db), date.today().year)}


def test_slots_sockets_and_ports_with_no_count_are_left_out_of_the_figures(client, db, part):
    counted = part(
        type="motherboard",
        model="Counted",
        specs="Slots: 6x 16-bit ISA | RAM slots: 4x 30-pin SIMM | Ports: 2x Serial",
    )
    blank = part(
        type="motherboard",
        model="Blank",
        specs="Slots: 2x VLB | RAM slots: 2x 72-pin SIMM | Ports: Parallel",
    )
    # Through SQL, because the ORM will not do it: handed None, it writes the
    # column's default. A restored dump or a hand-run UPDATE is under no such rule.
    for sql in (
        "UPDATE part_slot SET count = NULL WHERE part_id = :p",
        "UPDATE part_ram_slot SET count = NULL WHERE part_id = :p",
        "UPDATE part_port SET count = NULL WHERE part_id = :p",
    ):
        db.execute(text(sql), {"p": blank["asset_id"]})
    db.commit()
    assert client.get("/stats").status_code == 200
    st = main._collection_stats(db)
    assert [bus for bus, _n, _v in st["buses"]] == ["16-bit ISA"]
    assert [port for port, _n, _v in st["ports"]] == ["Serial"]
    pool = figures(db)
    assert pool["Most slots on one board"]["href"] == f"/parts/{counted['asset_id']}"
    assert pool["Most ports on one thing"]["v"] == "2"
    assert pool["The usual memory socket"]["v"] == "30-pin SIMM"
    assert pool["Memory sockets"]["v"] == "4"


def test_a_socket_of_no_type_is_counted_but_never_named(client, db, part):
    part(type="motherboard", model="Old", specs="RAM slots: 4x 30-pin SIMM")
    odd = part(type="motherboard", model="Odd", specs="RAM slots: 8x 72-pin SIMM")
    db.execute(
        text("UPDATE part_ram_slot SET slot_type = NULL WHERE part_id = :p"),
        {"p": odd["asset_id"]},
    )
    db.commit()
    assert client.get("/stats").status_code == 200
    pool = figures(db)
    assert pool["Memory sockets"]["v"] == "12"
    # The commonest socket is the one nobody named, and a name is what that figure
    # gives; the one about 30-pin sockets still has its own to give.
    assert "The usual memory socket" not in pool
    assert pool["30-pin SIMM sockets"]["v"] == "4"


def test_a_machine_whose_chips_have_no_count_has_no_figure_for_them(client, db, computer):
    aid = computer(model="PC")["asset_id"]
    client.post(f"/computers/{aid}/edit", data={"ramchip:41256": "18"}, follow_redirects=False)
    db.execute(text("UPDATE computer_ram_chip SET count = NULL WHERE computer_id = :c"), {"c": aid})
    db.commit()
    assert db.execute(text("SELECT COUNT(*) FROM computer_ram_chip")).scalar() == 1
    assert client.get("/stats").status_code == 200
    assert "Most memory chips" not in figures(db)


def test_a_spare_of_no_type_is_looked_for_among_the_others(client, db, part):
    for model in ("Typeless One", "Typeless Two", "Typeless Three"):
        part(type="sound", model=model)
    part(type="cpu", model="Typed")
    db.execute(text("UPDATE parts SET type = NULL WHERE type = 'sound'"))
    db.commit()
    assert client.get("/stats").status_code == 200
    spare = figures(db)["The commonest thing to have spare"]
    # Labelled Other, as a part of no type is everywhere, and so linked to the shelf
    # the gallery files it on.
    assert (spare["v"], spare["href"]) == ("Other", "/browse?f=sparetype&v=other")
    shelf = content(client.get(spare["href"]).text)
    assert "Typeless One" in shelf and "Typed" not in shelf
