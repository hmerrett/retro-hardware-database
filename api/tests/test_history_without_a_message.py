"""An item's page opens whatever its history holds.

``log_entry.message`` is nullable. Nothing the app writes leaves it null, but a row from
before the column had a default, or one written by hand, can -- and two of those
side by side are folded into one line, which meant pluralising a message that was
not there: a TypeError, and a page that would not open for that one item.
"""

from sqlalchemy import text

from app.models import LogEntry


def test_two_entries_with_no_message_do_not_stop_the_page_opening(client, db, computer):
    aid = computer()["asset_id"]
    # Through SQL, because the ORM will not do it: handed None, it writes the
    # column's default. A restored dump or a hand-run INSERT is under no such rule.
    for _ in range(2):
        db.execute(
            text(
                "INSERT INTO log_entry (asset_id, created_at, kind, message) "
                "VALUES (:aid, '2026-01-01 12:00:00', 'change', NULL)"
            ),
            {"aid": aid},
        )
    db.commit()
    stored = db.query(LogEntry.message).filter(LogEntry.asset_id == aid).all()
    assert [m for (m,) in stored].count(None) == 2, stored
    assert client.get(f"/computers/{aid}").status_code == 200
