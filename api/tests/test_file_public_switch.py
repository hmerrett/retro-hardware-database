"""A file's Public switch on every list of files (ADR-0042), as MANUAL.md section 11
("Who can see a file") promises it: on each row of an item's or a project's Files
panel and of /files, a Public button for an account that can change files, pressed
while the file is published, that publishes it or takes it back without the list
moving. A viewer keeps the Private mark; a visitor sees neither. ADR-0009's rules are
the file page's tick's, and hold whichever control changed the column.
"""

import re

import pytest

from app.models import StoredFile
from conftest import as_viewer, log_out
from test_files import card, newest, project, publish, speak, upload

PLACES = pytest.mark.parametrize("where", ["files", "item", "project"])


def a_file_in(client, part, where, name="receipt.pdf"):
    """A file, and the page whose list shows it."""
    if where == "project":
        aid = project(client)
        page = f"/projects/{aid}"
    else:
        aid = card(part)
        page = "/files" if where == "files" else f"/parts/{aid}"
    upload(client, name, aid=aid)
    return newest(client), page


def rows(html: str) -> str:
    found = re.search(r'<ul class="filerows">.*?</ul>', html, re.S)
    assert found, "the page has no list of files"
    return found.group(0)


def row(html: str, fid: int) -> str:
    found = re.search(rf'<li class="filerow" id="file-{fid}">.*?</li>', rows(html), re.S)
    assert found, f"no row for file {fid}"
    return found.group(0)


def switch(html: str, fid: int) -> dict[str, str]:
    """The row's Public form: where it posts, what it sends, and its button."""
    r = row(html, fid)
    form = re.search(r"<form[^>]*\bdata-pubswitch\b[^>]*>.*?</form>", r, re.S)
    assert form, "the row has no Public switch"
    f = form.group(0)
    button = re.search(r"<button\b[^>]*>(.*?)</button>", f, re.S)
    return {
        "action": re.search(r'action="([^"]+)"', f).group(1),
        "fields": dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', f)),
        "button": button.group(0),
        "words": " ".join(button.group(1).split()),
        "pressed": re.search(r'aria-pressed="(true|false)"', button.group(0)).group(1),
        "name": re.search(r'aria-label="([^"]+)"', button.group(0)).group(1),
    }


def press_it(client, page, fid, **headers):
    s = switch(client.get(page).text, fid)
    return client.post(s["action"], data=s["fields"], headers=headers, follow_redirects=False)


def is_public(db, fid) -> bool:
    db.expire_all()
    return db.get(StoredFile, fid).public


class TestOnEveryList:
    @PLACES
    def test_each_row_carries_public(self, client, part, where):
        fid, page = a_file_in(client, part, where)
        s = switch(client.get(page).text, fid)
        assert s["words"] == "Public"
        assert s["action"] == f"/files/{fid}/public"

    @PLACES
    def test_pressed_while_the_file_is_published_and_not_otherwise(self, client, part, where):
        fid, page = a_file_in(client, part, where)
        assert switch(client.get(page).text, fid)["pressed"] == "false"
        publish(client, fid)
        s = switch(client.get(page).text, fid)
        assert s["pressed"] == "true"
        assert re.search(r'class="[^"]*\bon\b', s["button"]), "drawn pressed, not only said"

    def test_its_name_starts_with_its_word_and_says_which_file(self, client, part):
        """A list of them is a list of buttons all called the same thing otherwise; and
        the words on show begin the name, so speaking them finds it."""
        fid, page = a_file_in(client, part, "files", name="tvga.zip")
        assert switch(client.get(page).text, fid)["name"] == "Public, tvga.zip"

    def test_it_follows_button_text(self, client, part):
        fid, page = a_file_in(client, part, "files")
        speak(client, "lower")
        s = switch(client.get(page).text, fid)
        assert s["words"] == "public" and s["name"].startswith("public, ")

    def test_the_owner_is_given_the_switch_in_place_of_the_private_mark(self, client, part):
        fid, page = a_file_in(client, part, "files")
        assert not re.search(
            r'<span class="chip quiet"[^>]*>Private</span>', row(client.get(page).text, fid)
        )

    def test_it_is_the_only_form_on_a_row(self, client, part):
        """Everything else done to a file is still done on its own page (ADR-0028)."""
        for where in ("files", "item"):
            fid, page = a_file_in(client, part, where, name=f"{where}.zip")
            assert len(re.findall(r"<form\b", row(client.get(page).text, fid))) == 1


class TestPressingIt:
    @PLACES
    def test_it_publishes_a_private_file_and_takes_a_public_one_back(self, client, db, part, where):
        fid, page = a_file_in(client, part, where)
        press_it(client, page, fid)
        assert is_public(db, fid) is True
        press_it(client, page, fid)
        assert is_public(db, fid) is False

    @PLACES
    def test_without_script_it_comes_back_to_the_same_row(self, client, part, where):
        fid, page = a_file_in(client, part, where)
        r = press_it(client, page, fid)
        assert r.status_code == 303
        assert r.headers["location"] == f"{page}#file-{fid}"

    def test_the_list_it_comes_back_to_keeps_its_filter(self, client, part):
        fid, _ = a_file_in(client, part, "files")
        r = press_it(client, "/files?show=private", fid)
        assert r.headers["location"] == f"/files?show=private#file-{fid}"

    def test_on_a_tabbed_item_page_it_comes_back_to_the_files_tab(self, client, part):
        fid, page = a_file_in(client, part, "item")
        client.cookies.set("rhdb_itemlayout", "tabs")
        r = press_it(client, f"{page}?tab=files", fid)
        assert r.headers["location"] == f"{page}?tab=files#file-{fid}"

    def test_an_items_list_comes_back_without_a_one_off_message(self, client, part):
        """An item page's address can carry an answer to the last thing sent; the
        switch comes back to the page and its tab, as every form on it does, and not
        to that answer again."""
        fid, page = a_file_in(client, part, "item")
        r = press_it(client, f"{page}?notadded=scan.heic", fid)
        assert r.headers["location"] == f"{page}#file-{fid}"

    def test_with_script_it_answers_in_place(self, client, db, part):
        """The list does not move: the script asks for the answer rather than a page."""
        fid, page = a_file_in(client, part, "files")
        r = press_it(client, page, fid, accept="application/json")
        assert r.status_code == 200
        assert r.json() == {"public": True}
        assert is_public(db, fid) is True

    def test_the_script_sends_it_and_turns_the_button(self, client, part):
        """What no rendered page can show, read off the script the page links."""
        page = client.get("/files").text
        js = client.get(re.search(r'src="(/static/app\.js)', page).group(1)).text
        block = js.split("form[data-pubswitch]", 1)[1].split("})();", 1)[0]
        assert "fetch(" in block and "application/json" in block
        assert "aria-pressed" in block

    def test_taking_it_back_hides_it_from_a_visitor_at_once(self, client, part):
        """ADR-0009 unchanged: an unpublished file is not found at its address."""
        fid, page = a_file_in(client, part, "files")
        publish(client, fid)
        press_it(client, page, fid)
        log_out(client)
        r = client.get(f"/files/{fid}/receipt.pdf")
        assert r.status_code == 404


class TestNobodyElseHasIt:
    def test_a_viewer_sees_private_and_no_switch(self, client, part):
        fid, page = a_file_in(client, part, "files")
        as_viewer(client)
        r = row(client.get(page).text, fid)
        assert "data-pubswitch" not in r
        assert re.search(r'<span class="chip quiet"[^>]*>Private</span>', r)

    def test_a_visitor_sees_neither(self, client, part):
        fid, page = a_file_in(client, part, "item")
        publish(client, fid)
        log_out(client)
        r = row(client.get(page).text, fid)
        assert "data-pubswitch" not in r and "Private" not in r

    def test_a_visitor_cannot_press_one(self, client, db, part):
        fid, _ = a_file_in(client, part, "files")
        log_out(client)
        r = client.post(f"/files/{fid}/public", data={"public": "1"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")
        assert is_public(db, fid) is False

    def test_the_decision_is_written_down(self):
        from pathlib import Path

        root = Path(__file__).parents[2]
        assert (root / "adr" / "0042-a-file-row-carries-its-public-switch.md").exists()
        assert "0042" in (root / "adr" / "README.md").read_text(encoding="utf-8")
