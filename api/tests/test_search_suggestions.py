"""The suggestions under the banner's search, as the manual describes them.

The list itself is drawn by app.js, and the suite runs no script, so what is held
here is what the server hands the script: the name and the tag cut into runs with
what was typed marked, and the words of the row that goes to every result. Both
are the server's rather than the script's to work out -- the marking because only
the server knows how a query splits into terms (a quoted phrase is one), and the
last row because its words follow the Button text setting, which the script
cannot read. The catalogue's models come as a list of their own beside the
collection's, with the words for when the collection has nothing to offer.
"""

import re
from pathlib import Path

from app import machines
from conftest import log_out, served
from test_projects import make as make_project
from test_settings import save

COMPONENTS = Path(__file__).parents[1] / "app" / "static" / "css" / "components.css"
STYLESHEET = Path(__file__).parents[1] / "app" / "static" / "app.css"


def suggest(client, q):
    return client.get("/suggest", params={"q": q}).json()


def only(client, q):
    items = suggest(client, q)["items"]
    assert len(items) == 1, items
    return items[0]


def media(path, query):
    """The bodies of every `@media <query>` block in a stylesheet, comments removed,
    each read to its own closing brace rather than to the next one found."""
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    bodies = []
    for found in re.finditer(r"@media\s*" + re.escape(query) + r"\s*\{", text):
        depth, at = 1, found.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[at], 0)
            at += 1
        bodies.append(text[found.end() : at - 1])
    return " ".join(bodies)


def marked(runs):
    """The marked letters of a run list, in order."""
    return [text for text, mark in runs if mark]


class TestTheMatchIsMarked:
    def test_what_was_typed_is_marked_in_the_name(self, client, computer):
        computer(manufacturer="Tandon", model="TM262")
        assert only(client, "tan")["runs"]["name"] == [["Tan", True], ["don TM262", False]]

    def test_the_runs_put_the_name_back_together(self, client, computer):
        """Marking cuts the name up; it must not change a letter of it."""
        computer(manufacturer="Tandon", model="TM262")
        item = only(client, "m26")
        assert "".join(text for text, _ in item["runs"]["name"]) == item["name"]

    def test_the_mark_keeps_the_names_own_capitals(self, client, computer):
        computer(manufacturer="Tandon", model="TM262")
        assert marked(only(client, "TAN")["runs"]["name"]) == ["Tan"]

    def test_every_word_typed_is_marked(self, client, computer):
        computer(manufacturer="Tandon", model="TM262")
        assert marked(only(client, "tandon 262")["runs"]["name"]) == ["Tandon", "262"]

    def test_every_place_a_word_appears_is_marked(self, client, computer):
        computer(manufacturer="Commodore", model="Amiga Amiga")
        assert marked(only(client, "amiga")["runs"]["name"]) == ["Amiga", "Amiga"]

    def test_a_quoted_phrase_is_marked_whole(self, client, part):
        """Quoted, it is one term and matched as one, so it is marked as one: the
        space inside it is part of what was asked for."""
        part(manufacturer="Creative", model="Sound Blaster 16")
        runs = only(client, '"sound blaster"')["runs"]["name"]
        assert marked(runs) == ["Sound Blaster"]

    def test_words_that_overlap_are_marked_once(self, client, computer):
        computer(manufacturer="Tandon", model="TM262")
        assert marked(only(client, "tand and")["runs"]["name"]) == ["Tand"]

    def test_the_tag_is_marked_when_it_is_what_was_typed(self, client, computer):
        aid = computer()["asset_id"]
        runs = only(client, aid[:5])["runs"]["aid"]
        assert runs == [[aid[:5], True], [aid[5:], False]]

    def test_a_match_somewhere_else_marks_nothing(self, client, computer):
        """Found by its year, which the row does not print in the name: the row is
        offered, and nothing in its name pretends to be what matched."""
        computer(manufacturer="Acme", model="Test", year=1987)
        item = only(client, "1987")
        assert marked(item["runs"]["name"]) == [] and marked(item["runs"]["aid"]) == []

    def test_a_project_is_marked_the_same_way(self, client):
        make_project(client, "Recap the +2A")
        assert marked(only(client, "recap")["runs"]["name"]) == ["Recap"]


class TestTheWayToEveryResult:
    def test_the_last_row_counts_every_result(self, client, computer):
        for _ in range(12):
            computer()
        assert suggest(client, "acme")["all"]["text"] == 'All 12 results for "acme"'

    def test_it_is_there_when_every_result_already_fits(self, client, computer):
        computer()
        computer()
        assert suggest(client, "acme")["all"]["text"] == 'All 2 results for "acme"'

    def test_a_single_result_is_not_called_all(self, client, computer):
        computer()
        assert suggest(client, "acme")["all"]["text"] == '1 result for "acme"'

    def test_it_says_the_query_as_it_was_typed(self, client, part):
        """Less the spaces either side, which nobody meant."""
        part(manufacturer="Creative", model="Sound Blaster 16")
        assert suggest(client, "  Sound Blaster ")["all"]["text"] == '1 result for "Sound Blaster"'

    def test_it_goes_where_enter_goes(self, client, computer):
        """Enter with nothing lit submits the banner's form: a GET to / with the box
        as q. The row is a link to the same address."""
        computer(model="Sound Blaster")
        page = client.get("/").text
        form = re.search(r'<form class="searchwrap"[^>]*>', page).group(0)
        assert 'method="get"' in form and 'action="/"' in form
        assert 'id="q" name="q"' in page
        assert suggest(client, "sound blaster")["all"]["url"] == "/?q=sound+blaster"

    def test_it_follows_the_button_text_setting(self, client, computer):
        """It is a control, so it speaks in the installation's voice."""
        computer()
        save(client, button_case="lower")
        assert suggest(client, "acme")["all"]["text"] == '1 result for "acme"'
        computer()
        assert suggest(client, "acme")["all"]["text"] == 'all 2 results for "acme"'

    def test_nothing_in_either_says_so(self, client, computer):
        """A word neither the collection nor the catalogue holds: no rows, no last
        row, and the words the list shows instead."""
        computer()
        answer = suggest(client, "qqzzy")
        assert answer["items"] == [] and answer["models"] == [] and answer["total"] == 0
        assert answer["all"] is None
        assert answer["none"] == 'Nothing matches "qqzzy".'


def file_as(client, aid, key, kind="computers"):
    client.patch(f"/api/{kind}/{aid}", json={"machine": {"model_key": key}})


def names(models):
    return [m["name"] for m in models]


class TestModelsFromTheCatalogue:
    """The second search: over the catalogue rather than the register, matched on
    what a model's own page prints as its name, its family's and its styles, and
    given only the room the collection leaves."""

    def test_a_model_nobody_owns_is_offered_and_opens_its_page(self, client):
        [zx81] = suggest(client, "zx81")["models"]
        assert zx81["name"] == "Sinclair ZX81"
        assert zx81["url"] == "/machines/zx81"
        assert client.get(zx81["url"]).status_code == 200

    def test_its_row_says_none_in_this_collection(self, client):
        [zx81] = suggest(client, "zx81")["models"]
        assert zx81["cat"] == "Model"
        assert zx81["year"] == 1981
        assert zx81["here"] == "none in this collection"

    def test_a_model_you_own_says_how_many_are_here(self, client, computer, part):
        """The count its page lists: machines and bare boards, disposed ones too."""
        kept, gone = computer()["asset_id"], computer()["asset_id"]
        board = part(type="motherboard")["asset_id"]
        for aid in (kept, gone):
            file_as(client, aid, "vic-20")
        file_as(client, board, "vic-20", "parts")
        client.post(f"/computers/{gone}/dispose", data={"note": "", "date": ""})
        [vic] = [m for m in suggest(client, "vic-20")["models"] if m["url"] == "/machines/vic-20"]
        assert vic["here"] == "3 in this collection"
        page = client.get("/machines/vic-20").text
        assert len(re.findall(r'<a class="result"', page)) == 3

    def test_a_model_has_no_asset_tag(self, client):
        [zx81] = suggest(client, "zx81")["models"]
        assert "aid" not in zx81 and "aid" not in zx81["runs"]

    def test_what_was_typed_is_marked_in_a_models_name(self, client):
        [zx81] = suggest(client, "zx81")["models"]
        assert zx81["runs"]["name"] == [["Sinclair ", False], ["ZX81", True]]

    def test_a_model_is_found_by_one_of_its_styles(self, client):
        """The name on the badge of the machine in front of you: the M24 was sold
        in the US as the AT&T 6300."""
        assert names(suggest(client, "at&t 6300")["models"]) == ["Olivetti M24"]

    def test_a_model_is_found_by_the_name_of_its_family(self, client):
        """Printed under its name on its page, and often on the badge as well: the
        CD32 is catalogued as Commodore's, among the Amigas, and every MSX machine
        carries the name of the standard whoever made it built it to."""
        assert names(suggest(client, "amiga cd32")["models"]) == ["Commodore CD32"]
        assert len(suggest(client, "msx")["models"]) == 10

    def test_a_model_is_not_found_by_its_cpu_or_its_paragraph(self, client):
        """Neither is what the model is called, and either would offer the catalogue
        wholesale: dozens of its models were built round a 6502."""
        assert sum("6502" in m["cpu"] for m in machines.models()) > 10
        assert suggest(client, "6502")["models"] == []
        assert suggest(client, '"first computer of any kind"')["models"] == []

    def test_a_name_that_starts_with_what_was_typed_comes_first(self, client):
        """The Osborne 1 is found by a style, the one in a tan case; the Tandons, the
        Tandys and the Tano Dragon are found by their names, and come before it."""
        offered = names(suggest(client, "tan")["models"])
        assert len(offered) == 10
        assert all(n.lower().startswith("tan") for n in offered), offered

    def test_models_come_after_everything_in_the_collection(self, client, computer):
        """Into the room the collection leaves, and drawn below it."""
        for _ in range(3):
            computer(manufacturer="Tandon", model="PCA")
        answer = client.get("/suggest", params={"q": "tandon", "limit": 4}).json()
        assert len(answer["items"]) == 3
        assert names(answer["models"]) == ["Tandon PAC 386SX"]
        script = served(client, client.get("/").text)
        assert "items.concat(models).forEach(" in script

    def test_a_model_never_takes_the_place_of_something_owned(self, client, computer):
        for _ in range(10):
            computer(manufacturer="Tandon", model="PCA")
        answer = suggest(client, "tandon")
        assert len(answer["items"]) == 10 and answer["models"] == []
        answer = client.get("/suggest", params={"q": "tandon", "limit": 4}).json()
        assert len(answer["items"]) == 4 and answer["models"] == []

    def test_the_last_row_counts_the_collection_alone(self, client, computer):
        computer(manufacturer="Tandon", model="PCA")
        computer(manufacturer="Tandon", model="PCX")
        answer = suggest(client, "tandon")
        assert len(answer["models"]) == 4
        assert answer["total"] == 2
        assert answer["all"]["text"] == 'All 2 results for "tandon"'

    def test_only_the_catalogue_matching_says_nothing_in_the_collection_does(
        self, client, computer
    ):
        """And offers no last row: it would read "All 0 results", and open a page
        with nothing on it."""
        computer()
        answer = suggest(client, "zx81")
        assert answer["items"] == [] and answer["total"] == 0
        assert names(answer["models"]) == ["Sinclair ZX81"]
        assert answer["all"] is None
        assert answer["none"] == 'Nothing in the collection matches "zx81".'

    def test_a_visitor_is_offered_models_too(self, client):
        """The catalogue is public, and so is how many of each are here."""
        log_out(client)
        assert names(suggest(client, "zx81")["models"]) == ["Sinclair ZX81"]


class TestHowManyRows:
    """Ten, or four when the script is on a phone and asks for four: the keyboard
    takes half the screen, and the last row has to stay in sight above it."""

    def test_ten_are_offered(self, client, computer):
        for _ in range(12):
            computer()
        answer = suggest(client, "acme")
        assert len(answer["items"]) == 10 and answer["total"] == 12

    def test_a_phone_is_offered_four(self, client, computer):
        for _ in range(12):
            computer()
        answer = client.get("/suggest", params={"q": "acme", "limit": 4}).json()
        assert len(answer["items"]) == 4
        assert answer["all"]["text"] == 'All 12 results for "acme"'

    def test_no_more_than_ten_are_offered_whatever_is_asked(self, client, computer):
        """The whole answer is the results page's to give, not this list's."""
        for _ in range(12):
            computer()
        assert len(client.get("/suggest", params={"q": "acme", "limit": 500}).json()["items"]) == 10

    def test_a_nonsense_count_is_refused(self, client):
        assert client.get("/suggest", params={"q": "acme", "limit": 0}).status_code == 422


class TestOnAPhone:
    def test_the_banners_list_is_dressed_as_a_suggestion_list(self, client):
        """It was the one listbox without the class, so it wore 0.1's rules --
        anchored to the box's right edge at 380px, which on a phone put its left
        half off the screen."""
        page = client.get("/").text
        tag = re.search(r'<div[^>]*id="suggest"[^>]*>', page).group(0)
        assert re.search(r'class="[^"]*\bsuggest\b', tag), tag

    def test_no_rule_is_left_for_the_old_list(self):
        text = re.sub(r"/\*.*?\*/", "", STYLESHEET.read_text(encoding="utf-8"), flags=re.S)
        assert "#suggest" not in text

    def test_the_list_spans_the_width_under_the_banner(self):
        """On a phone the list hangs from the banner rather than from the box, and
        runs from one side of the screen to the other."""
        rule = re.search(
            r"\.site-header \.suggest \{([^}]*)\}", media(COMPONENTS, "(max-width: 620px)")
        )
        assert rule, "the phone block does not place the suggestion list"
        body = rule.group(1)
        assert re.search(r"\bleft:", body) and re.search(r"\bright:", body)
        assert re.search(r"\bwidth:\s*auto", body)

    def test_every_row_is_tall_enough_for_a_thumb(self):
        coarse = media(COMPONENTS, "(pointer: coarse)")
        for row in (".suggest .sg", ".suggest .all"):
            assert re.search(re.escape(row) + r"[^{]*\{[^}]*min-height:\s*var\(--tap\)", coarse), (
                row
            )
