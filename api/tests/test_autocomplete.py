"""Offering back what has already been typed.

Several boxes on these forms are answered the same way over and over -- where a
thing came from, what case it is in, what it runs. Left as bare text they drift:
the register holds "Pete Farm" sixteen times and "Farm Pete" eight, which is one
person and one provenance recorded as two, and no search finds both.

So every such box carries a datalist of the answers already given, commonest
first. It is a datalist and not a menu on purpose -- the next machine may well come
from somewhere new, and nothing here refuses a new answer. What it does is make the
answer already given the easier one to give again.
"""
from app import main
from app.models import Computer, Part, StoredFile


def sources(db):
    return main._answers_given(db, Computer.source, Part.source)


def options(html, list_id):
    """The values a page offers in one datalist."""
    import re
    m = re.search(rf'<datalist id="{list_id}">(.*?)</datalist>', html, re.S)
    return re.findall(r'<option value="([^"]*)"', m.group(1)) if m else None


class TestWhatIsOffered:
    def test_an_answer_already_given_is_offered(self, client, db, computer):
        computer(source="Stephen Usher")
        assert sources(db) == ["Stephen Usher"]

    def test_the_commonest_comes_first(self, client, db, computer):
        """A datalist is offered in the order it is written, and the answer given
        twenty times is the likelier one."""
        for _ in range(3):
            computer(source="Pete Farm")
        computer(source="eBay")
        assert sources(db) == ["Pete Farm", "eBay"]

    def test_the_same_answer_typed_two_ways_is_one_answer(self, client, db,
                                                          computer):
        """Case and stray spaces are how one answer becomes two. They fold together
        for the counting, and the spelling offered back is the one used most -- so
        "eBay" wins by having been typed, not by a rule about capitals."""
        for _ in range(2):
            computer(source="eBay")
        computer(source="ebay")
        computer(source="  eBay  ")
        assert sources(db) == ["eBay"]

    def test_the_minority_spelling_does_not_win_by_being_stored_first(
            self, client, db, computer):
        """The one the database would have picked. MariaDB's collation folds case
        and ignores trailing spaces, so GROUP BY had already merged these three
        before we saw them and handed back whichever row it read first as the
        label -- which made "the spelling used most" a fact about the storage
        engine. Written first here, and outnumbered, so it must lose."""
        computer(source="EBAY")
        for _ in range(3):
            computer(source="eBay")
        assert sources(db) == ["eBay"]

    def test_nothing_is_offered_for_a_field_left_blank(self, client, db, computer):
        computer(source="")
        assert sources(db) == []

    def test_machines_and_parts_share_one_list(self, client, db, computer, part):
        """A job lot arrives as a machine and a box of cards together, and that is
        one provenance however many records it becomes."""
        computer(source="Job lot of Amstrad stuff")
        part(source="RC Table Sale")
        assert set(sources(db)) == {"Job lot of Amstrad stuff", "RC Table Sale"}


class TestTheFormsOfferThem:
    def test_the_machine_form_offers_a_source(self, client, computer):
        computer(source="Stephen Usher")
        assert options(client.get("/computers/new").text,
                       "dl_source") == ["Stephen Usher"]

    def test_the_part_form_offers_the_same_sources(self, client, computer):
        computer(source="Stephen Usher")
        assert options(client.get("/parts/new").text,
                       "dl_sources") == ["Stephen Usher"]

    def test_a_machine_is_offered_the_makes_it_knows(self, client, computer, part):
        """Parts had this and machines did not, though a Compaq is a Compaq whether
        it is the box or the board out of it."""
        computer(manufacturer="Compaq")
        part(manufacturer="Adaptec")
        assert set(options(client.get("/computers/new").text,
                           "dl_makes")) == {"Compaq", "Adaptec"}

    def test_a_part_is_offered_a_make_only_a_machine_has_used(self, client,
                                                              computer):
        computer(manufacturer="Amstrad")
        assert "Amstrad" in options(client.get("/parts/new").text, "dl_makes")

    def test_a_machines_model_list_is_machines_only(self, client, computer, part):
        """A list of every card and drive model as well would bury "PC1512" among a
        thousand answers to a different question."""
        computer(model="PC1512")
        part(model="AHA-1542CF")
        assert options(client.get("/computers/new").text,
                       "dl_models") == ["PC1512"]

    def test_the_three_a_machine_is_asked_and_a_part_is_not(self, client,
                                                            computer):
        computer(chassis="desktop", os="MS-DOS 6.22", cpu="Intel 486DX2-66")
        page = client.get("/computers/new").text
        assert options(page, "dl_chassis") == ["desktop"]
        assert options(page, "dl_os") == ["MS-DOS 6.22"]
        assert options(page, "dl_cpu") == ["Intel 486DX2-66"]

    def test_an_edit_form_offers_them_as_well(self, client, computer):
        """The same boxes, and the same drift: an edit is where a spelling gets
        changed into a second one."""
        aid = computer(source="Stephen Usher")["asset_id"]
        assert options(client.get(f"/computers/{aid}/edit").text,
                       "dl_source") == ["Stephen Usher"]


class TestElsewhere:
    def test_a_project_offers_who_things_were_bought_from(self, client, db):
        p = client.post("/api/projects", json={"name": "A500"}).json()["asset_id"]
        client.post(f"/api/projects/{p}/orders",
                    json={"description": "belt", "supplier": "Retro Bits"})
        assert options(client.get(f"/projects/{p}").text,
                       "dl_suppliers") == ["Retro Bits"]

    def test_the_files_panel_offers_what_files_have_been_called(self, client, db,
                                                               computer):
        db.add(StoredFile(stored="x.bin", filename="x.bin", note="ROM dump"))
        db.commit()
        aid = computer()["asset_id"]
        assert options(client.get(f"/computers/{aid}").text,
                       "dl_filenotes") == ["ROM dump"]

    def test_a_visitor_is_offered_nothing(self, client, computer, monkeypatch):
        """The pick lists are on the forms, and the forms are behind the login --
        so a public page cannot leak the list of everybody the collection has ever
        bought from."""
        computer(source="Stephen Usher")
        aid = computer()["asset_id"]
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert "Stephen Usher" not in client.get(f"/computers/{aid}").text
