"""A machine's label prints whatever is inside it.

The label lists the machine's parts in order of their type. ``parts.type`` is
nullable, and sorting a part that has none against one that has was None compared
with a string: a TypeError, and no label for that machine at all. The app always
writes a type, so it took a row from outside it -- a restored dump, an import --
to have one missing.
"""

from sqlalchemy import text


def test_a_part_with_no_type_does_not_stop_the_label_printing(client, db, computer):
    aid = computer()["asset_id"]
    for model in ("One", "Two"):
        r = client.post(
            "/api/parts",
            json={"type": "cpu", "manufacturer": "Acme", "model": model, "computer_id": aid},
        )
        assert r.status_code == 200, r.text
    # Through SQL, because the ORM writes the column's default in place of a None.
    db.execute(text("UPDATE parts SET type = NULL WHERE model = 'Two'"))
    db.commit()
    r = client.get(f"/computers/{aid}/label.pdf")
    assert r.status_code == 200, r.text[:300]
    assert r.content.startswith(b"%PDF")
