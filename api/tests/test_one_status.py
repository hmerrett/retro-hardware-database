"""One Status control on an item page, as MANUAL.md section 16 ("Status") promises
it: In the collection, Might sell or Disposed -- three answers to one question,
sent by one Save -- in place of the Might sell tick under the summary and the
disposal box at the foot of the side column.

The bookkeeping behind Disposed is disposal.py's, and its own tests (test_api,
test_tree) go on holding it; what is here is the control, what each answer does to
the record, and who is shown any of it (ADR-0018: Might sell is the owner's alone).
"""

import re
from datetime import date

import pytest

from app.models import Computer, LogEntry, Part
from conftest import as_viewer, content, log_out

KINDS = pytest.mark.parametrize("kind,model", [("computers", Computer), ("parts", Part)])


def make(kind, computer, part, **kw):
    return (computer(**kw) if kind == "computers" else part(**kw))["asset_id"]


def status(client, kind, aid, to, **extra):
    """Choose an answer and press Save, the way the panel does."""
    r = client.post(f"/{kind}/{aid}/status", data={"status": to, **extra}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def panel(page: str) -> str:
    """The Status form, or the empty string where there is none."""
    found = re.search(r"<form[^>]*\bdata-status\b.*?</form>", content(page), re.S)
    return found.group(0) if found else ""


def radios(form: str) -> dict[str, str]:
    """Each answer's value, mapped to the words beside it."""
    return {
        v: " ".join(w.split())
        for v, w in re.findall(
            r'<label[^>]*>\s*<input[^>]*type="radio"[^>]*value="([^"]+)"[^>]*>([^<]*)</label>',
            form,
        )
    }


def chosen(form: str) -> str:
    hit = re.findall(r'<input[^>]*type="radio"[^>]*value="([^"]+)"[^>]*\bchecked\b', form)
    assert len(hit) == 1, hit
    return hit[0]


def lines(db, aid: str) -> list[str]:
    db.expire_all()
    return [e.message for e in db.query(LogEntry).filter(LogEntry.asset_id == aid)]


class TestThePanel:
    @KINDS
    def test_the_owner_has_one_status_with_three_answers(self, client, computer, part, kind, model):
        aid = make(kind, computer, part)
        form = panel(client.get(f"/{kind}/{aid}").text)
        assert radios(form) == {
            "held": "In the collection",
            "might-sell": "Might sell",
            "disposed": "Disposed",
        }
        assert f'action="/{kind}/{aid}/status"' in form

    def test_the_answers_are_one_named_group(self, client, part):
        """Three radio buttons with no name for the question they answer are three
        loose words to a screen reader."""
        form = panel(client.get(f"/parts/{part()['asset_id']}").text)
        assert re.search(r"<fieldset[^>]*>\s*<legend[^>]*>Status</legend>", form)

    def test_it_is_sent_by_save_and_nothing_else(self, client, part):
        """Nothing changes until Save is pressed (Jonathan, 2026-10-13): unlike the
        tick it replaces, it is not a data-ticksend form."""
        form = panel(client.get(f"/parts/{part()['asset_id']}").text)
        assert "data-ticksend" not in form
        assert re.search(r'<button[^>]*type="submit"[^>]*>\s*Save\s*</button>', form)

    def test_it_is_in_the_side_column_under_the_label(self, client, part):
        page = content(client.get(f"/parts/{part()['asset_id']}").text)
        side = page.split('<div class="itemside">', 1)[1]
        assert "data-status" in side
        assert side.index(">Label<") < side.index("data-status")

    def test_a_new_item_is_in_the_collection(self, client, part):
        assert chosen(panel(client.get(f"/parts/{part()['asset_id']}").text)) == "held"

    @KINDS
    def test_a_flagged_item_opens_on_might_sell(self, client, computer, part, kind, model):
        aid = make(kind, computer, part)
        status(client, kind, aid, "might-sell")
        assert chosen(panel(client.get(f"/{kind}/{aid}").text)) == "might-sell"

    @KINDS
    def test_a_disposed_item_opens_on_disposed_with_what_was_written(
        self, client, computer, part, kind, model
    ):
        aid = make(kind, computer, part)
        status(client, kind, aid, "disposed", note="sold at the rally", date="2026-07-20")
        form = panel(client.get(f"/{kind}/{aid}").text)
        assert chosen(form) == "disposed"
        assert 'value="sold at the rally"' in form
        assert 'value="2026-07-20"' in form

    def test_why_and_when_are_labelled_and_shown_without_script(self, client, part):
        """With JavaScript switched off they are always there: the markup never
        hides them, the script does."""
        form = panel(client.get(f"/parts/{part()['asset_id']}").text)
        when = re.search(r"<div[^>]*\bdata-status-when\b[^>]*>", form)
        assert when and "hidden" not in when.group(0)
        for box, words in (("status-note", "Why"), ("status-date", "When")):
            assert f'<label for="{box}">{words}</label>' in form
            assert f'id="{box}"' in form

    def test_the_script_opens_why_and_when_only_with_disposed(self, client, part):
        """What no rendered page can show: read off the script the page links."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        script = re.search(r'src="(/static/app\.js)', page)
        js = client.get(script.group(1)).text
        block = js.split("form[data-status]", 1)[1].split("})();", 1)[0]
        assert "[data-status-when]" in block
        assert "'disposed'" in block
        assert ".hidden" in block

    def test_what_disposing_a_machine_does_to_its_parts_is_in_the_tooltip(self, client, computer):
        form = panel(client.get(f"/computers/{computer()['asset_id']}").text)
        assert "The parts in it go with it" in form

    @KINDS
    def test_the_tick_and_the_disposal_box_are_gone(self, client, computer, part, kind, model):
        aid = make(kind, computer, part)
        page = content(client.get(f"/{kind}/{aid}").text)
        assert f"/{aid}/for-sale" not in page
        assert f"/{aid}/dispose" not in page
        assert ">Disposal<" not in page

    @KINDS
    def test_the_banner_keeps_delete_and_loses_restore(self, client, computer, part, kind, model):
        """Putting it back is choosing In the collection; the banner is left with
        the one thing nothing else on the page does."""
        aid = make(kind, computer, part)
        status(client, kind, aid, "disposed", note="binned")
        page = content(client.get(f"/{kind}/{aid}").text)
        banner = re.search(r'<div class="banner[^"]*".*?</div>', page, re.S).group(0)
        assert f"/{kind}/{aid}/delete" in banner
        assert "Restore" not in banner and "/restore" not in page


class TestNobodyElseSeesIt:
    def test_a_visitor_is_shown_no_panel_and_no_might_sell(self, client, part):
        aid = part()["asset_id"]
        status(client, "parts", aid, "might-sell")
        log_out(client)
        page = client.get(f"/parts/{aid}").text
        assert panel(page) == ""
        assert "might sell" not in content(page).lower()

    def test_a_visitor_is_shown_the_disposed_banner(self, client, part):
        aid = part()["asset_id"]
        status(client, "parts", aid, "disposed", note="sold", date="2026-01-02")
        log_out(client)
        page = client.get(f"/parts/{aid}").text
        assert "Disposed" in content(page) and "2026-01-02" in content(page)
        assert panel(page) == ""

    def test_a_viewer_account_is_shown_no_panel(self, client, part):
        """A viewer reads the shortlist and changes nothing on it (ADR-0018)."""
        aid = part()["asset_id"]
        as_viewer(client)
        assert panel(client.get(f"/parts/{aid}").text) == ""

    def test_a_visitor_cannot_set_one(self, client, db, part):
        aid = part()["asset_id"]
        log_out(client)
        r = client.post(f"/parts/{aid}/status", data={"status": "disposed"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login?next=")
        db.expire_all()
        assert db.get(Part, aid).disposed is False


class TestChoosing:
    @KINDS
    def test_might_sell_puts_it_on_the_shortlist_and_in_the_collection_takes_it_off(
        self, client, db, computer, part, kind, model
    ):
        aid = make(kind, computer, part)
        status(client, kind, aid, "might-sell")
        db.expire_all()
        assert db.get(model, aid).for_sale is True
        status(client, kind, aid, "held")
        db.expire_all()
        assert db.get(model, aid).for_sale is False

    @KINDS
    def test_disposed_records_why_and_when(self, client, db, computer, part, kind, model):
        aid = make(kind, computer, part)
        status(client, kind, aid, "disposed", note="sold at the rally", date="2026-07-20")
        db.expire_all()
        row = db.get(model, aid)
        assert row.disposed is True
        assert row.disposed_at == date(2026, 7, 20)
        assert row.disposed_note == "sold at the rally"

    def test_disposed_with_no_date_went_today(self, client, db, part):
        aid = part()["asset_id"]
        status(client, "parts", aid, "disposed", note="", date="")
        db.expire_all()
        assert db.get(Part, aid).disposed_at == date.today()

    def test_why_and_when_are_ignored_by_any_other_answer(self, client, db, part):
        """Without script they are on the page whatever is chosen, and sent with it."""
        aid = part()["asset_id"]
        status(client, "parts", aid, "might-sell", note="typed anyway", date="2026-01-01")
        db.expire_all()
        row = db.get(Part, aid)
        assert row.disposed is False and row.disposed_note == ""

    @KINDS
    def test_disposing_takes_it_off_the_shortlist(self, client, db, computer, part, kind, model):
        """One status or the other: something gone is not something you might sell."""
        aid = make(kind, computer, part)
        status(client, kind, aid, "might-sell")
        status(client, kind, aid, "disposed", note="sold")
        db.expire_all()
        row = db.get(model, aid)
        assert row.disposed is True and row.for_sale is False

    def test_in_the_collection_restores_a_machine_and_the_parts_that_went_with_it(
        self, client, db, computer, part
    ):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        status(client, "computers", cid, "disposed", note="sold as a lot", date="2026-07-20")
        db.expire_all()
        assert db.get(Part, pid).disposed is True
        status(client, "computers", cid, "held")
        db.expire_all()
        machine = db.get(Computer, cid)
        assert machine.disposed is False
        assert machine.disposed_at is None and machine.disposed_note == ""
        assert db.get(Part, pid).disposed is False

    def test_might_sell_on_something_disposed_restores_it_and_flags_it(self, client, db, part):
        aid = part()["asset_id"]
        status(client, "parts", aid, "disposed", note="binned")
        status(client, "parts", aid, "might-sell")
        db.expire_all()
        row = db.get(Part, aid)
        assert row.disposed is False and row.for_sale is True
        assert any(m.startswith("restored") for m in lines(db, aid))

    def test_saving_disposed_again_corrects_it_and_the_parts_that_went_with_it(
        self, client, db, computer, part
    ):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        status(client, "computers", cid, "disposed", note="sold", date="2026-07-20")
        status(client, "computers", cid, "disposed", note="sold at the rally", date="2026-07-21")
        db.expire_all()
        for row in (db.get(Computer, cid), db.get(Part, pid)):
            assert row.disposed is True
            assert row.disposed_at == date(2026, 7, 21)
            assert row.disposed_note == "sold at the rally"
        assert "disposal corrected (2026-07-21): sold at the rally\n1 part in it corrected too" in (
            lines(db, cid)
        )
        assert f"disposal corrected with {cid} (2026-07-21): sold at the rally" in lines(db, pid)

    def test_a_corrected_disposal_still_brings_its_parts_back(self, client, db, computer, part):
        """The reason the correction reaches the parts: a restore finds what went
        with a machine by its date and why."""
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        status(client, "computers", cid, "disposed", note="sold", date="2026-07-20")
        status(client, "computers", cid, "disposed", note="given away", date="2026-07-22")
        status(client, "computers", cid, "held")
        db.expire_all()
        assert db.get(Part, pid).disposed is False

    def test_a_part_disposed_of_separately_is_left_out_of_the_correction(
        self, client, db, computer, part
    ):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        status(client, "parts", pid, "disposed", note="died on the bench", date="2026-01-05")
        status(client, "computers", cid, "disposed", note="sold", date="2026-07-20")
        status(client, "computers", cid, "disposed", note="sold at the rally", date="2026-07-20")
        db.expire_all()
        assert db.get(Part, pid).disposed_note == "died on the bench"

    def test_saving_the_same_answer_again_writes_nothing(self, client, db, part):
        aid = part()["asset_id"]
        status(client, "parts", aid, "disposed", note="sold", date="2026-07-20")
        before = lines(db, aid)
        status(client, "parts", aid, "disposed", note="sold", date="2026-07-20")
        assert lines(db, aid) == before

    def test_an_answer_it_does_not_offer_is_refused(self, client, db, part):
        aid = part()["asset_id"]
        r = client.post(f"/parts/{aid}/status", data={"status": "sold"}, follow_redirects=False)
        assert r.status_code == 400
        r = client.post(f"/parts/{aid}/status", data={}, follow_redirects=False)
        assert r.status_code == 400
        db.expire_all()
        assert db.get(Part, aid).disposed is False

    def test_something_that_is_not_there_is_a_404(self, client):
        r = client.post("/parts/RH-9999/status", data={"status": "held"}, follow_redirects=False)
        assert r.status_code == 404

    @KINDS
    def test_it_comes_back_to_the_page_and_the_tab_it_was_sent_from(
        self, client, computer, part, kind, model
    ):
        aid = make(kind, computer, part)
        r = client.post(
            f"/{kind}/{aid}/status?tab=files",
            data={"status": "might-sell"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == f"/{kind}/{aid}?tab=files"
