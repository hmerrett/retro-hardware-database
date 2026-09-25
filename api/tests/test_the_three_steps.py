"""The first screen of a new installation: an empty register, and three steps.

Until the first thing is in it the gallery has nothing to be, so the front page is
the three steps to a labelled machine instead. It is the one screen in the register
that nobody sees twice, which is exactly why it needs a test: the only way to look
at it by hand is to empty the database.
"""

from app import settings
from conftest import content, log_out


def owner(client):
    return content(client.get("/").text)


def visitor(client):
    log_out(client)
    return content(client.get("/").text)


class TestAnEmptyRegister:
    def test_the_owner_is_given_the_three_steps(self, client, db):
        """Numbered, because they are an order and not a menu: name the collection,
        add the first machine, print its label."""
        page = owner(client)
        assert '<ol class="steps">' in page
        assert "Name the collection" in page
        assert "Add the first machine" in page
        assert "Print its label" in page
        assert page.count("<li") == 3, "three steps, and the numbering is the list's"

    def test_naming_the_collection_ticks_its_own_step(self, client, db):
        """The one step the screen can see the answer to. Ticked and struck through
        rather than only struck through -- a line through a word is a colour and a
        shape, and the mark is what a screen reader has to go on."""
        before = owner(client)
        assert '<li class="done">' not in before

        settings.save(db, {"site_name": "The Retro Loft"})
        settings.forget()
        after = owner(client)
        assert '<li class="done">' in after
        done = after.split('<li class="done">', 1)[1].split("</li>", 1)[0]
        assert "Name the collection" in done

    def test_there_is_nothing_to_print_yet(self, client, db):
        """The third step waits on the second. A button that offered to print a
        label for nothing would be a button that cannot be pressed and does not
        say so."""
        page = owner(client)
        step = page.split("Print its label", 1)[1]
        assert "disabled" in step.split("</li>", 1)[0]

    def test_the_way_to_the_first_machine_is_on_the_screen(self, client, db):
        """A step somebody has to go and find the control for is an instruction
        rather than a step."""
        page = owner(client)
        assert 'href="/settings"' in page
        assert 'href="/computers/new"' in page

    def test_a_visitor_is_told_it_is_empty_and_no_more(self, client, db):
        """The steps are things only the owner can do, and a list of them is a list
        of what has not been done yet -- which is nobody else's business."""
        page = visitor(client)
        assert "Nothing here yet" in page
        assert '<ol class="steps">' not in page
        assert "Add the first machine" not in page


class TestOnceThereIsSomethingInIt:
    def test_the_gallery_comes_back_the_moment_there_is_an_item(self, client, db, computer):
        """It goes as soon as there is one item and does not come back: not a tour,
        and nothing to dismiss."""
        computer()
        page = owner(client)
        assert '<ol class="steps">' not in page
        assert '<div class="grid' in page or 'class="card' in page

    def test_a_search_that_finds_nothing_is_not_an_empty_register(self, client, db, computer):
        """Two different states that both draw no cards. A search with no matches
        says so; the steps belong to a register with nothing in it at all."""
        computer()
        page = content(client.get("/?q=nothing-matches-this").text)
        assert '<ol class="steps">' not in page
        assert "No matching items." in page


def test_the_steps_are_the_front_page_and_not_every_empty_grid(client, db):
    """/for-sale draws the same grid from a narrowed list, and an empty one of
    those is a filter that matched nothing rather than a new installation. So the
    question is asked on the way into the gallery and not inside the grid the
    three of them share."""
    assert '<ol class="steps">' not in content(client.get("/for-sale").text)
