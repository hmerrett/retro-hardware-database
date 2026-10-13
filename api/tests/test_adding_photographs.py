"""Adding photographs to an item from its Photographs panel (MANUAL §10, "Adding
photographs", "On a touchscreen", "From a phone").

The promises the script keeps are held as the rest of the suite holds them: by what
the server renders and answers, by the stylesheet, and by the script's own source.
No test here drives a browser."""

import re
from pathlib import Path

import pytest

from conftest import content, log_out
from test_files import speak
from test_item_page_controls import _png
from test_item_page_names import tree
from test_level_controls import coarse, outside_coarse
from test_stylesheet_lint import COMPONENTS, text

APP = Path(__file__).resolve().parents[1] / "app"
SCRIPT = APP / "static" / "uploads.js"
LIVE = APP / "static" / "live.js"

KINDS = pytest.mark.parametrize("kind", ["computers", "parts", "locations"])


@pytest.fixture
def made(client, computer, part):
    """An item of each kind with a page of photographs, and the photographs this test
    put on disk taken away again: the register is emptied between tests and the image
    folders are not."""
    from app import main

    ids = []

    def make(kind):
        if kind == "computers":
            aid = computer(name="Lounge PC")["asset_id"]
        elif kind == "parts":
            aid = part(model="Widget")["asset_id"]
        else:
            aid = client.post("/api/locations", json={"name": "Workshop", "kind": "room"}).json()[
                "asset_id"
            ]
        ids.append((kind, aid))
        return aid

    yield make
    for kind, aid in ids:
        for path in (main.IMAGES_DIR / kind).glob(f"{aid}*"):
            path.unlink(missing_ok=True)


def send(client, kind, aid, name="p.png", body=None, kind_of="image/png", script=True):
    """One photograph, as the script sends it (asking for JSON) or as a form does."""
    headers = {"Accept": "application/json"} if script else {}
    return client.post(
        f"/{kind}/{aid}/photo",
        files={"photos": (name, _png() if body is None else body, kind_of)},
        headers=headers,
        follow_redirects=False,
    )


def on_disk(kind, aid):
    from app import main

    return sorted(p.name for p in (main.IMAGES_DIR / kind).glob(f"{aid}*"))


def log(client, aid):
    return [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]


def panel(page):
    """The Photographs panel's markup."""
    inside = content(page)
    assert "<h3>Photographs</h3>" in inside, "no Photographs panel"
    rest = inside[inside.index("<h3>Photographs</h3>") :]
    end = rest.find('<section class="panel', 1)
    return rest if end == -1 else rest[:end]


def tile(page):
    m = re.search(r'<label class="addtile"[^>]*>.*?</label>', page, re.S)
    assert m, "no Add photos tile"
    return m[0]


def take(page):
    m = re.search(r'<label class="btn primary takephoto">.*?</label>', page, re.S)
    assert m, "no Take photo button"
    return m[0]


class TestThePanel:
    @KINDS
    def test_add_photos_is_a_tile_after_the_last_thumbnail(self, client, made, kind):
        aid = made(kind)
        for i in range(3):
            send(client, kind, aid, f"p{i}.png")
        page = client.get(f"/{kind}/{aid}").text
        thumbs = page[page.index('<div class="thumbs">') :]
        # The tile is the grid's last cell: nothing but the grid's end after it.
        assert re.match(r"\s*</div>", thumbs[thumbs.index(tile(page)) + len(tile(page)) :])
        assert thumbs.count('class="thumb-item"') == 2
        assert "Add photos" in tile(page)

    def test_the_picker_is_inside_the_tile_hidden_but_focusable(self, client, made):
        aid = made("computers")
        t = tile(client.get(f"/computers/{aid}").text)
        inp = re.search(r"<input[^>]*>", t)[0]
        assert 'class="sr-only"' in inp and 'type="file"' in inp and 'name="photos"' in inp
        assert 'accept="image/*"' in inp and " multiple" in inp
        assert 'form="photo-upload"' in inp, "the tile sits in the grid, outside the form"
        assert "disabled" not in inp and "tabindex" not in inp

    def test_with_no_photograph_the_tile_sits_under_the_drawing(self, client, made):
        aid = made("computers")
        page = panel(client.get(f"/computers/{aid}").text)
        assert page.index('class="nophoto"') < page.index('class="addtile"')

    def test_with_one_photograph_the_tile_is_the_first_thumbnail(self, client, made):
        aid = made("computers")
        send(client, "computers", aid)
        page = panel(client.get(f"/computers/{aid}").text)
        grid = page[page.index('<div class="thumbs">') :]
        assert grid.index('class="addtile"') < grid.index("</div>")
        assert 'class="thumb-item"' not in page

    def test_the_tile_is_where_photographs_are_dropped(self, client, made):
        assert "data-drop" in tile(client.get(f"/computers/{made('computers')}").text)
        js = SCRIPT.read_text()
        for event in ("dragover", "dragleave", "drop"):
            assert f"'{event}'" in js, event
        assert "dataTransfer.files" in js

    def test_take_photo_opens_the_camera(self, client, made):
        t = take(client.get(f"/computers/{made('computers')}").text)
        inp = re.search(r"<input[^>]*>", t)[0]
        assert 'capture="environment"' in inp and 'class="sr-only"' in inp
        assert " multiple" not in inp
        assert "Take photo" in t

    def test_choose_photos_takes_several_at_once(self, client, made):
        t = tile(client.get(f"/computers/{made('computers')}").text)
        assert re.search(r'<span class="on-coarse">Choose photos</span>', t)
        assert " multiple" in re.search(r"<input[^>]*>", t)[0]

    def test_a_touchscreen_gets_take_photo_and_choose_photos_and_a_desktop_add_photos(self):
        css = text(COMPONENTS)
        fine = re.search(r"@media not all and \(pointer: coarse\)\s*\{([^}]*\})", css)
        assert fine, "nothing hidden away from a touchscreen"
        assert ".takephoto" in fine[1] and ".on-coarse" in fine[1]
        assert "display: none" in fine[1]
        assert re.search(r"\.on-fine[^{]*\{[^}]*display: none", coarse())

    def test_no_picker_is_required(self, client, made):
        page = panel(client.get(f"/computers/{made('computers')}").text)
        assert 'type="file"' in page
        assert not re.search(r'<input[^>]*type="file"[^>]*\brequired\b', page)

    def test_a_browser_without_script_still_has_upload(self, client, made):
        page = client.get(f"/computers/{made('computers')}").text
        form = page[page.index('id="photo-upload"') :]
        form = form[: form.index("</form>")]
        assert re.search(r'<button class="btn sm" type="submit" data-send-go>Upload</button>', form)
        assert 'enctype="multipart/form-data"' in page[: page.index('id="photo-upload"') + 200]

    def test_the_rows_are_read_out_as_they_change(self, client, made):
        page = client.get(f"/computers/{made('computers')}").text
        assert '<ul class="uploads" aria-live="polite"></ul>' in page

    def test_only_the_state_is_read_out_not_every_percent(self, client, made):
        """A polite region reads every change inside it, and a percentage changes a
        hundred times: the figure is for the eye."""
        page = client.get(f"/computers/{made('computers')}").text
        row = page[page.index('<template id="uprow">') :]
        row = row[: row.index("</template>")]
        assert re.search(r'<span class="pc" aria-hidden="true"></span>', row)

    @pytest.mark.parametrize("case", ["cap", "lower"])
    def test_try_again_follows_the_button_text_setting(self, client, made, case):
        speak(client, case)
        page = client.get(f"/computers/{made('computers')}").text
        row = page[page.index('<template id="uprow">') :]
        row = row[: row.index("</template>")]
        words = "Try again" if case == "cap" else "try again"
        assert re.search(rf'<button class="btn sm" type="button" hidden>{words}</button>', row)
        assert ("Add photos" if case == "cap" else "add photos") in tile(page)
        assert ("Take photo" if case == "cap" else "take photo") in take(page)

    @KINDS
    def test_a_visitor_gets_no_picker(self, client, made, kind):
        aid = made(kind)
        log_out(client)
        page = client.get(f"/{kind}/{aid}").text
        for mark in ('class="addtile"', "takephoto", 'id="photo-upload"', "uprow", "uploads.js"):
            assert mark not in page, mark

    def test_every_picker_is_named_by_what_you_press(self, client, made):
        """The input is hidden and the label is what is seen, so the label is its
        name. Of the tile's two words, the pointer's stylesheet shows one and takes
        the other out of the name with it (`display: none`)."""
        t = tree(client.get(f"/computers/{made('computers')}").text)
        names = [t.name(n) for n in t.root.walk() if n.tag == "input" and n.get("type") == "file"]
        assert any("Add photos" in n and "Choose photos" in n for n in names)
        assert "Take photo" in names


class TestTheCodeForAPhone:
    @KINDS
    def test_the_code_is_in_the_photographs_panel_under_the_rows(self, client, made, kind):
        aid = made(kind)
        page = panel(client.get(f"/{kind}/{aid}").text)
        assert page.index('class="uploads"') < page.index('class="qrlabel"')
        assert "From your phone" not in client.get(f"/{kind}/{aid}").text

    def test_the_code_on_the_page_says_take_photo(self, client, made):
        aid = made("computers")
        page = client.get(f"/computers/{aid}").text
        assert re.search(
            r'class="qrlabel".*?<p class="t"><b>On your phone</b>'
            r"Scan to open this page there, then Take photo\.</p>",
            page,
            re.S,
        )

    def test_it_still_points_at_the_upload(self, client, made):
        from app import labels

        aid = made("computers")
        page = client.get(f"/computers/{aid}").text
        assert labels.qr_svg(f"https://example.test/computers/{aid}#photo-upload") in page
        assert 'id="photo-upload"' in page

    def test_it_stays_hidden_on_a_phone(self):
        assert re.search(
            r"@media \(max-width: 860px\) \{ \.qrlabel \{ display: none; \} \}", text(COMPONENTS)
        )


class TestTheRoute:
    @KINDS
    def test_one_photograph_sent_by_the_script_is_answered_in_json(self, client, made, kind):
        aid = made(kind)
        r = send(client, kind, aid)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert r.json() == {"added": [f"{kind}/{aid}.png"]}
        assert on_disk(kind, aid) == [f"{aid}.png"]

    @KINDS
    def test_a_form_post_still_goes_back_to_the_page(self, client, made, kind):
        aid = made(kind)
        r = send(client, kind, aid, script=False)
        assert r.status_code == 303
        assert r.headers["location"] == f"/{kind}/{aid}"

    def test_a_form_post_from_a_tab_goes_back_to_that_tab(self, client, made):
        aid = made("computers")
        r = client.post(
            f"/computers/{aid}/photo?tab=history",
            files={"photos": ("p.png", _png(), "image/png")},
            follow_redirects=False,
        )
        assert r.headers["location"] == f"/computers/{aid}?tab=history"

    @pytest.mark.parametrize(
        "name, body, kind_of",
        [
            ("notes.txt", b"not a picture at all", "text/plain"),
            ("disguised.png", b"not a picture either", "image/png"),
        ],
    )
    def test_a_file_that_is_not_a_photograph_is_refused_in_the_rows_words(
        self, client, made, name, body, kind_of
    ):
        aid = made("computers")
        r = send(client, "computers", aid, name, body, kind_of)
        assert r.status_code == 400
        assert r.json() == {"reason": "not a photograph"}
        assert on_disk("computers", aid) == []
        assert not any("photo" in m for m in log(client, aid))

    @pytest.mark.parametrize(
        "name, kind_of, body",
        [
            ("IMG_0001.heic", "image/heic", b"\x00\x00\x00\x18ftypheic"),
            ("scan.bmp", "image/bmp", None),
        ],
    )
    def test_a_kind_of_image_not_kept_says_which_are(self, client, made, name, kind_of, body):
        if body is None:
            from io import BytesIO

            from PIL import Image

            buf = BytesIO()
            Image.new("RGB", (8, 6), "white").save(buf, "BMP")
            body = buf.getvalue()
        aid = made("computers")
        r = send(client, "computers", aid, name, body, kind_of)
        assert r.status_code == 400
        assert r.json() == {"reason": "only JPEG, PNG, WebP and GIF are kept"}
        assert on_disk("computers", aid) == []

    def test_a_bmp_wearing_a_png_name_is_refused_as_a_kind_not_kept(self, client, made):
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 6), "white").save(buf, "BMP")
        aid = made("computers")
        r = send(client, "computers", aid, "scan.png", buf.getvalue())
        assert r.json() == {"reason": "only JPEG, PNG, WebP and GIF are kept"}

    @KINDS
    def test_three_added_one_at_a_time_read_as_one_line(self, client, made, kind):
        aid = made(kind)
        for i in range(3):
            assert send(client, kind, aid, f"p{i}.png").status_code == 200
        assert log(client, aid).count("added a photo") == 3
        page = client.get(f"/{kind}/{aid}").text
        assert "added 3 photos" in page and "photo(s)" not in page

    def test_several_in_one_form_post_are_one_line(self, client, made):
        aid = made("computers")
        client.post(
            f"/computers/{aid}/photo",
            files=[("photos", (f"p{i}.png", _png(), "image/png")) for i in range(2)],
            follow_redirects=False,
        )
        assert "added 2 photos" in log(client, aid)

    def test_a_photograph_on_a_new_item_is_worded_the_same(self, client):
        r = client.post(
            "/computers/new",
            data={"manufacturer": "Acme", "model": "Solo"},
            files={"photos": ("p.png", _png(), "image/png")},
            follow_redirects=False,
        )
        aid = r.headers["location"].split("/")[2].split("?")[0]
        try:
            assert "added a photo" in log(client, aid)
        finally:
            from app import main

            for path in (main.IMAGES_DIR / "computers").glob(f"{aid}*"):
                path.unlink(missing_ok=True)

    def test_a_signed_out_upload_is_not_answered_as_added(self, client, made):
        aid = made("computers")
        log_out(client)
        r = send(client, "computers", aid)
        assert r.status_code != 200 or "added" not in r.text
        assert not r.headers.get("content-type", "").startswith("application/json")
        assert on_disk("computers", aid) == []

    def test_with_no_script_a_refused_photograph_is_named_on_the_page(self, client, made):
        aid = made("computers")
        r = client.post(
            f"/computers/{aid}/photo",
            files=[
                ("photos", ("good.png", _png(), "image/png")),
                ("photos", ("notes.txt", b"words", "text/plain")),
            ],
            follow_redirects=False,
        )
        assert r.status_code == 303
        page = client.get(r.headers["location"]).text
        box = panel(page)
        assert "Not added: notes.txt." in box
        assert "JPEG, PNG, WebP and GIF" in box
        # The one that could be kept was.
        assert on_disk("computers", aid) == [f"{aid}.png"]
        assert "added a photo" in log(client, aid)

    def test_the_names_are_said_to_the_owner_and_nobody_else(self, client, made):
        """The names ride in the address, and an address can be sent to anybody: a
        visitor's page does not print words a stranger put in a link."""
        aid = made("computers")
        log_out(client)
        page = client.get(f"/computers/{aid}?notadded=Your+account+is+closed").text
        assert "Your account is closed" not in page


class TestTheStylesheet:
    def test_the_button_shows_where_the_keyboard_is(self):
        css = text(COMPONENTS)
        ring = re.search(
            r":is\(\.addtile, \.takephoto\):has\(input:focus-visible\)\s*\{([^}]*)\}", css
        )
        assert ring, "no ring drawn for the hidden pickers"
        assert "outline: var(--focus-w) solid var(--focus)" in ring[1]

    def test_the_tile_is_outlined_in_accent_while_something_is_dragged_over_it(self):
        """And everything on it turns `text`, as on any hovered row: the accent ink
        on the hover ground is not a pair the design uses."""
        css = text(COMPONENTS)
        over = re.search(r"\.addtile:hover, \.addtile\.is-over\s*\{([^}]*)\}", css)
        assert over
        assert "border-color: var(--accent)" in over[1]
        assert "color: var(--text)" in over[1]
        assert "background: var(--surface-hover)" in over[1]

    def test_the_tile_is_the_cards_shape_in_accent_ink_on_a_dashed_edge(self):
        body = re.search(r"(?<![\w.-])\.addtile\s*\{([^}]*)\}", text(COMPONENTS))[1]
        assert "aspect-ratio: var(--thumb-ratio)" in body
        assert "color: var(--accent)" in body
        assert "dashed var(--line-strong)" in body

    def test_on_a_touchscreen_take_photo_runs_the_width_of_the_panel(self):
        assert re.search(r"\.takephoto\s*\{[^}]*flex-basis: 100%", coarse())

    def test_the_old_panel_is_gone(self):
        css = outside_coarse()
        for gone in (".photo-actions.across", ".photo-qr", ".qr-code", ".dropzone"):
            assert gone not in css, gone


class TestTheScript:
    def test_the_page_waits_for_its_own_uploads_before_reloading(self):
        js = LIVE.read_text()
        busy = js[js.index("function busy()") :]
        busy = busy[: busy.index("\n  }\n")]
        assert "'.uploads .up:not(.is-done)'" in busy

    def test_the_page_reloads_once_every_photograph_is_added(self):
        js = SCRIPT.read_text()
        done = js[js.index("function finished()") :]
        done = done[: done.index("\n  }\n")]
        assert "location.reload()" in done
        assert ".up:not(.is-done)" in done

    def test_if_one_is_not_added_the_page_asks_rather_than_reloads(self):
        js, live = SCRIPT.read_text(), LIVE.read_text()
        assert "new Event('rhdb:look')" in js
        assert "addEventListener('rhdb:look', look)" in live

    def test_photographs_go_one_at_a_time(self):
        js = SCRIPT.read_text()
        assert "if (running) return;" in js
        assert "queue.shift()" in js
        # Each request carries one photograph.
        assert js.count("fd.append('photos'") == 1

    def test_progress_comes_from_xmlhttprequest(self):
        """`fetch` reports nothing about an upload's progress."""
        js = SCRIPT.read_text()
        assert "new XMLHttpRequest()" in js and "xhr.upload.onprogress" in js
        assert "fetch(" not in js

    def test_it_asks_the_route_for_json(self):
        assert "setRequestHeader('Accept', 'application/json')" in SCRIPT.read_text()

    def test_try_again_is_offered_where_it_could_help_and_not_for_a_refusal(self):
        js = SCRIPT.read_text()
        assert re.search(r"xhr\.onerror = \(\) => fail\(job, '[^']+', true\)", js)
        assert re.search(r"xhr\.ontimeout = \(\) => fail\(job, '[^']+', true\)", js)
        assert re.search(r"status >= 500\) fail\(job, '[^']+', true\)", js)
        assert re.search(r"status === 400[^\n]*fail\(job, [^\n]*, false\)", js)

    def test_a_signed_out_answer_says_to_log_in(self):
        assert "log in again" in SCRIPT.read_text()

    def test_each_row_draws_its_picture_on_a_canvas(self):
        js = SCRIPT.read_text()
        assert "createImageBitmap(" in js and "getContext('2d')" in js
        assert "drawImage(" in js

    def test_no_preview_is_drawn_from_a_blob_url(self):
        """The policy is `img-src 'self'`, which a blob: URL in an <img> is not."""
        code = re.sub(r"//[^\n]*", "", SCRIPT.read_text())
        assert "createObjectURL" not in code and "blob:" not in code

    def test_the_bar_is_set_through_the_cssom(self):
        js = SCRIPT.read_text()
        assert ".style.width = " in js and "setAttribute('style'" not in js
