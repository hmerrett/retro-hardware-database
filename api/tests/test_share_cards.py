"""What a shared link to a page of photographs previews as (ADR-0017).

An item's link already previews as the item. These are the pages that are *walls*
of photographs and had no single photograph to be "the" photograph: the gallery, a
`/browse` slice, a search on either, and the projects list. They preview as up to
four of the photographs actually on the page, tiled into one 1200x630 picture.

The pixel assertions are the point of several of these. A montage is the one thing
in this codebase whose correctness a reader cannot check by looking at the HTML --
the tag says only that there is a picture -- so the tests open the picture and ask
what is in each quarter of it.
"""
import re

import pytest
from PIL import Image

from app import cards, main
from app.models import Project

# Four flat colours, far enough apart that JPEG cannot confuse one for another and
# none of them near the card's cream.
RED, BLUE, GREEN, YELLOW = (200, 30, 30), (30, 60, 200), (30, 160, 60), (220, 190, 40)
COLOURS = (RED, BLUE, GREEN, YELLOW)


# --- helpers ----------------------------------------------------------------

@pytest.fixture
def photo():
    """Put a flat-colour photograph on an asset and take it away afterwards.

    Written to the image folder rather than posted through the upload form: these
    tests are about what is made *from* photographs, and a test that spends its
    setup on Pillow round-tripping an upload reads as a test of the upload.
    """
    made = []

    def put(kind, asset_id, colour=RED, size=(800, 600), suffix=""):
        folder = main.IMAGES_DIR / kind
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{asset_id}{suffix}.jpg"
        Image.new("RGB", size, colour).save(path, "JPEG", quality=95)
        made.append(path)
        return f"{kind}/{path.name}"

    yield put
    for path in made:
        path.unlink(missing_ok=True)


def og_image(client, url):
    """The og:image a page names, or None."""
    m = re.search(r'<meta property="og:image" content="([^"]+)"', client.get(url).text)
    return m.group(1) if m else None


def card_of(client, url):
    """The montage a page names, opened. Fails if the page's card is the site's own."""
    src = og_image(client, url)
    assert src and "/og/" in src, f"{url} shares {src}, not a montage"
    r = client.get(src.replace("https://example.test", ""))
    assert r.status_code == 200, src
    import io
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def tiled(*rels):
    """The montage of exactly these photographs, in this order, opened.

    Through cards.montage rather than through a page, and deliberately so: where a
    photograph lands is a property of an ordered list, and the order a page hands
    over is the page's own business. The gallery's is recency, and asset ids are
    random, so ties between items saved in the same second break differently on
    every run -- a layout asserted through `/` would be asserting whatever today's
    ids happened to sort to. What the pages owe is a montage *of their own
    photographs*, and that is what TestWhatAGridPageSharesAs checks, end to end.
    """
    got = cards.montage(list(rels))
    assert got is not None, rels
    path, _w, _h = got
    return Image.open(cards.cache_dir() / path.rsplit("/", 1)[1]).convert("RGB")


def near(pixel, colour, tol=30):
    return all(abs(a - b) <= tol for a, b in zip(pixel, colour, strict=True))


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees. A crawler fetching a card
    is anonymous, so this is the reader every card is made for."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def project_with(client, name, *asset_ids, private=False):
    """A project, optionally private, with these things on it.

    `private` goes in at creation rather than being patched on afterwards: there is
    no window in which it exists and is public, which is the same order the form
    takes and one fewer request to get wrong.
    """
    r = client.post("/api/projects", json={"name": name, "private": private})
    assert r.status_code == 200, r.text
    pid = r.json()["asset_id"]
    for aid in asset_ids:
        assert client.post(f"/api/projects/{pid}/items",
                           json={"asset_id": aid}).status_code == 200
    return pid


# --- the pages ---------------------------------------------------------------

class TestWhatAGridPageSharesAs:
    """The four pages that render a grid of photographs, and the three that do not."""

    def test_the_gallery_shares_a_montage_of_the_photographs_on_it(
            self, client, part, photo):
        """It shared as the logo, so the front page of a collection of photographs
        looked like every other link to the site."""
        photo("parts", part()["asset_id"], RED)
        assert re.fullmatch(r"https://example\.test/og/[0-9a-f]{16}\.jpg",
                            og_image(client, "/"))

    def test_a_search_shares_the_photographs_of_its_own_results(
            self, client, part, photo):
        """Not the gallery's: the card describes the answer that was shared, which
        is the whole reason a search is worth previewing."""
        photo("parts", part(model="Gotek")["asset_id"], RED)
        photo("parts", part(model="Kryoflux")["asset_id"], BLUE)
        assert near(card_of(client, "/?q=gotek").getpixel((600, 315)), RED)
        assert near(card_of(client, "/?q=kryoflux").getpixel((600, 315)), BLUE)

    def test_a_browse_slice_shares_the_photographs_on_it(self, client, computer,
                                                          part, photo):
        photo("computers", computer()["asset_id"], RED)
        photo("parts", part()["asset_id"], BLUE)
        assert near(card_of(client, "/browse?f=computers").getpixel((600, 315)), RED)
        assert near(card_of(client, "/browse?f=parts").getpixel((600, 315)), BLUE)

    def test_the_projects_list_shares_its_projects_photographs(self, client, part,
                                                                photo):
        """A project's own page already previews as the machine it is about; the
        list of them previewed as the logo."""
        aid = part()["asset_id"]
        photo("parts", aid, GREEN)
        project_with(client, "recap the PSU", aid)
        assert near(card_of(client, "/projects").getpixel((600, 315)), GREEN)

    def test_a_page_with_nothing_photographed_still_shares_the_site_card(
            self, client, part):
        """The fallback SITE_CARD was added for is untouched: a page with no
        photographs on it has no montage to make."""
        part()
        for path in ("/", "/?q=widget", "/browse?f=parts", "/projects"):
            assert "/static/og-image.png" in og_image(client, path), path

    def test_the_pages_with_no_photographs_on_them_keep_the_site_card(
            self, client, part, photo):
        """Even with a photographed collection behind them. Four unrelated machines
        would describe a page of drivers worse than the logo does."""
        photo("parts", part()["asset_id"], RED)
        for path in ("/files", "/stats", "/machines"):
            assert "/static/og-image.png" in og_image(client, path), path


# --- what the picture is -----------------------------------------------------

class TestWhatGoesOnTheMontage:
    """Up to four, in a 2x2, filling the space rather than leaving a hole."""

    def test_a_card_is_the_1200_by_630_every_preview_slot_wants(self, client, part,
                                                                 photo):
        photo("parts", part()["asset_id"], RED)
        assert card_of(client, "/").size == (1200, 630)
        page = client.get("/").text
        assert '<meta property="og:image:width" content="1200">' in page
        assert '<meta property="og:image:height" content="630">' in page
        assert 'name="twitter:card" content="summary_large_image"' in page

    def test_one_photograph_fills_the_whole_frame(self, part, photo):
        """Three corners and the middle. The fourth corner carries the site's mark,
        which the test below is about."""
        card = tiled(photo("parts", part()["asset_id"], RED))
        for at in ((6, 6), (1193, 6), (6, 623), (600, 315)):
            assert near(card.getpixel(at), RED), at

    def test_two_sit_side_by_side_with_the_card_between_them(self, part, photo):
        card = tiled(photo("parts", part(model="Aaa")["asset_id"], RED),
                     photo("parts", part(model="Bbb")["asset_id"], BLUE))
        assert near(card.getpixel((300, 315)), RED)
        assert near(card.getpixel((900, 315)), BLUE)
        assert near(card.getpixel((600, 315)), cards.CARD_BG), "no gutter between them"

    def test_three_go_as_one_large_and_two_stacked(self, part, photo):
        card = tiled(*[photo("parts", part(model=f"M{i}")["asset_id"], colour)
                       for i, colour in enumerate((RED, BLUE, GREEN))])
        assert near(card.getpixel((300, 315)), RED), "the first fills the left"
        assert near(card.getpixel((900, 150)), BLUE)
        assert near(card.getpixel((900, 480)), GREEN)

    def test_four_go_as_a_grid_read_left_to_right(self, part, photo):
        card = tiled(*[photo("parts", part(model=f"M{i}")["asset_id"], colour)
                       for i, colour in enumerate(COLOURS)])
        for (x, y), colour in zip(((300, 150), (900, 150), (300, 480), (900, 480)),
                                  COLOURS, strict=True):
            assert near(card.getpixel((x, y)), colour), (x, y)

    def test_at_most_four_photographs_go_on_one_card(self, tmp_path, part, photo):
        """A fifth stops being a photograph at the width a chat client renders a
        preview. Asserted on the cache key rather than on pixels: six results and
        the first four of them are one card, which is also what makes the card of a
        long result list cheap."""
        rels = [photo("parts", part(model=f"M{i}")["asset_id"], COLOURS[i % 4])
                for i in range(6)]
        assert cards.montage(rels) == cards.montage(rels[:4])
        assert cards.montage(rels) != cards.montage(rels[:3])

    def test_a_tile_is_filled_rather_than_letterboxed(self, part, photo):
        """A tall photograph in a wide tile is cropped to it, and a wide one in a
        tall tile likewise. Bands of cream inside a montage read as a broken image
        rather than as a photograph of an unusual shape."""
        card = tiled(photo("parts", part(model="Aaa")["asset_id"], RED, size=(400, 1400)),
                     photo("parts", part(model="Bbb")["asset_id"], BLUE, size=(1600, 300)))
        for x in (60, 300, 540):
            assert near(card.getpixel((x, 40)), RED), x
            assert near(card.getpixel((x, 590)), RED), x
        for x in (660, 900, 1140):
            assert near(card.getpixel((x, 40)), BLUE), x

    def test_the_card_carries_the_sites_mark_once_and_not_per_tile(self, part, photo):
        """Four watermarked tiles would put four marks on one picture, each cropped
        to wherever its tile's corner fell. The card is one picture, so it is marked
        once, in its own corner, at its own scale."""
        card = tiled(*[photo("parts", part(model=f"M{i}")["asset_id"], colour)
                       for i, colour in enumerate(COLOURS)])
        assert not near(card.getpixel((1114, 544)), YELLOW), "no mark on the card"
        # The bottom-right of each of the four tiles, which is where a mark carried
        # in from the photographs would land.
        for (x, y), colour in zip(((560, 280), (1166, 280), (560, 592)),
                                  (RED, BLUE, GREEN), strict=True):
            assert near(card.getpixel((x, y)), colour), (x, y)

    def test_a_placeholder_drawing_is_never_tiled_onto_a_card(self):
        """The same rule a project's card already holds to: an outline of a computer
        reads as a broken image, which is worse than the site's own card."""
        assert cards.montage(["/static/placeholders/storage.svg"]) is None
        assert cards.montage(["", None]) is None


# --- the cache ---------------------------------------------------------------

class TestTheCardIsMadeOnceAndKept:
    """Content-addressed: the key is the photographs, never the query."""

    def test_two_searches_landing_on_the_same_items_share_one_card(
            self, client, part, photo):
        aid = part(manufacturer="Commodore", model="C64")["asset_id"]
        photo("parts", aid, RED)
        assert og_image(client, "/?q=commodore") == og_image(client, "/?q=c64")

    def test_changing_a_photograph_makes_the_card_again(self, client, part, photo):
        """The key carries each photograph's modification time, so a crop is a new
        URL rather than something needing to be invalidated -- the bargain img_url's
        ?v= stamp already makes, and what lets the card be cached for a year."""
        aid = part()["asset_id"]
        rel = photo("parts", aid, RED)
        before = og_image(client, "/")
        Image.new("RGB", (800, 600), BLUE).save(main.IMAGES_DIR / rel, "JPEG")
        assert og_image(client, "/") != before

    def test_a_card_is_served_as_immutable_for_a_year(self, client, part, photo):
        photo("parts", part()["asset_id"], RED)
        src = og_image(client, "/").replace("https://example.test", "")
        r = client.get(src)
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert r.headers["content-type"] == "image/jpeg"

    def test_the_card_route_opens_a_file_by_hash_and_reads_nothing_else(self, client):
        """It never searches and never writes, so there is nothing a stranger can
        ask it to do. Anything that is not one of this app's own hashes is a 404."""
        for name in ("../../etc/passwd", "..%2f..%2fetc%2fpasswd", "nothalfahash.jpg",
                     "0123456789abcdef.png", "0123456789ABCDEF.jpg",
                     "0123456789abcdef.jpg"):
            assert client.get(f"/og/{name}").status_code == 404, name

    def test_a_card_is_fetchable_without_logging_in(self, client, part, photo,
                                                     monkeypatch):
        """The one that makes the feature exist at all, and it was wrong first time.

        A preview is fetched anonymously: the chat service reads the page as a
        stranger, then fetches the og:image that page names. So on an installation
        with a login, a card behind that login answers with a redirect to it and no
        preview ever renders -- while every test on a suite that runs open passes,
        because there is no login there to be behind."""
        photo("parts", part()["asset_id"], RED)
        src = og_image(client, "/").replace("https://example.test", "")
        visitor(monkeypatch)
        r = client.get(src, follow_redirects=False)
        assert r.status_code == 200, f"{src} answered {r.status_code} to a visitor"
        assert r.headers["content-type"] == "image/jpeg"

    def test_a_query_on_the_card_route_changes_nothing(self, client, part, photo):
        photo("parts", part()["asset_id"], RED)
        src = og_image(client, "/").replace("https://example.test", "")
        assert client.get(src).content == client.get(f"{src}?q=anything").content

    def test_the_cache_is_capped(self, part, photo, monkeypatch):
        """A query string is an unbounded key space even when the photographs behind
        it are not, and this route is anonymous."""
        monkeypatch.setattr(cards, "CAP", 2)
        for i in range(4):
            cards.montage([photo("parts", part(model=f"M{i}")["asset_id"],
                                 COLOURS[i])])
        assert len(list(cards.cache_dir().glob("*.jpg"))) <= 2

    def test_cards_from_an_older_build_are_missed_rather_than_served(self):
        """The lesson the watermark cache learned twice: name the directory after
        what went into it, so a change to how these are made misses the old ones."""
        stale = cards.cache_dir().parent / "b0"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "old.jpg").write_bytes(b"not a card")
        cards.sweep()
        assert not stale.exists()
        assert cards.cache_dir().exists()


# --- who may be on one -------------------------------------------------------

class TestOnlyPublicPhotographsGoOnACard:
    """A card is fetched by an anonymous crawler, so it is made of what an anonymous
    reader is shown. Every photograph under /images already is -- the projects list
    is the one page where the question has an edge."""

    def test_a_private_project_puts_no_photograph_on_the_list_card(
            self, client, db, part, photo, monkeypatch):
        aid = part()["asset_id"]
        photo("parts", aid, RED)
        pid = project_with(client, "hush", aid, private=True)
        assert db.get(Project, pid).private is True
        visitor(monkeypatch)
        assert "/static/og-image.png" in og_image(client, "/projects")

    @staticmethod
    def two_projects(client, part, photo):
        """A private project and a public one, each with a photographed thing on it.
        Named so the private one sorts first, which is what would put its photograph
        on the card if the rows were not already filtered."""
        hidden = part(model="Hidden")["asset_id"]
        shown = part(model="Shown")["asset_id"]
        photo("parts", hidden, BLUE)
        photo("parts", shown, GREEN)
        project_with(client, "aaa hush", hidden, private=True)
        project_with(client, "bbb open", shown)

    def test_a_visitors_card_is_made_of_a_visitors_rows(self, client, part, photo,
                                                         monkeypatch):
        """The whole rule, and the one that matters. A preview is fetched
        anonymously -- a chat service reads the page as a stranger and takes the
        og:image it names -- so this is the card a recipient sees whoever pasted the
        link. One photograph survives for a visitor, so it fills the frame."""
        self.two_projects(client, part, photo)
        visitor(monkeypatch)
        assert near(card_of(client, "/projects").getpixel((600, 315)), GREEN)

    def test_the_owners_own_card_may_show_more_and_that_is_not_a_leak(
            self, client, part, photo, monkeypatch):
        """The owner's page names a card built from the owner's rows, so it can carry
        a photograph of something on a private project. That photograph is public
        already -- /images serves it to anybody -- and the card is never what a
        shared link previews as, because a preview is fetched anonymously and gets
        the card above instead.

        Asserted rather than left implicit so that making the two identical is a
        decision somebody takes on purpose, not a tidy-up. Deterministic: two
        photographs for the owner and one for a visitor are different layouts, so
        different cards."""
        self.two_projects(client, part, photo)
        owner = og_image(client, "/projects")
        visitor(monkeypatch)
        assert og_image(client, "/projects") != owner

    def test_the_photographs_on_a_card_are_ones_the_site_already_serves(
            self, client, part, photo, monkeypatch):
        """Stated as a test because it is the reason the montage needs no gate of
        its own: it is made of pictures anybody may already fetch one at a time."""
        rel = photo("parts", part()["asset_id"], RED)
        visitor(monkeypatch)
        assert client.get(f"/images/{rel}").status_code == 200
        assert cards.montage([rel]) is not None


class TestTheMapAndTheManualSaySo:
    def test_the_decision_is_written_down(self):
        from pathlib import Path
        root = Path(__file__).parents[2]
        adr = root / "adr" / "0017-a-page-of-photographs-shares-a-montage-of-them.md"
        assert adr.exists()
        assert "0017" in (root / "adr" / "README.md").read_text(encoding="utf-8")
        assert "ADR-0017" in (root / "docs" / "architecture.md").read_text(
            encoding="utf-8")
