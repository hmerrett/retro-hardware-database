"""The numbers page on the v0.2 components, as MANUAL.md section 16 describes it: a
headline, the portrait coverage, eight tiles drawn from the pool, and the ranked
charts -- and almost every number a link to what it counted.

The figures themselves are held in test_api.py; this is the page they are set in.
"""

import re

from app.routers import stats as stats_routes


def main_of(page: str) -> str:
    return page.split("<main", 1)[1].split("</main>", 1)[0]


class TestTheNumbersPage:
    def test_it_is_on_the_v2_layout_with_a_heading_of_its_own(self, client):
        page = client.get("/stats").text
        assert '<main id="main" tabindex="-1" class="v2">' in page
        # The figure is the page's headline, but a figure is not a heading: the page
        # is still named for a reader who moves by headings.
        assert re.search(r"<h1[^>]*>The collection by numbers</h1>", page)

    def test_the_headline_figure_leads_to_everything_it_counted(self, client, computer):
        page = client.get("/stats").text
        assert re.search(r'<div class="figure"><a href="/browse\?f=all">\d+</a></div>', page)

    def test_the_tiles_are_stat_tiles_and_one_with_a_page_is_its_link(self, client, monkeypatch):
        monkeypatch.setattr(
            stats_routes,
            "_facts",
            lambda *_a: [
                {"k": "Linked", "v": "7", "s": "seven of them", "href": "/browse?f=all"},
                {"k": "Unlinked", "v": "12", "s": "no page to show", "href": None},
            ],
        )
        body = main_of(client.get("/stats").text)
        grid = body.split('<div class="statgrid">', 1)[1]
        assert '<a class="stattile" href="/browse?f=all"><div class="k">Linked</div>' in grid
        assert '<div class="stattile"><div class="k">Unlinked</div>' in grid

    def test_each_ranked_chart_is_headed_and_its_names_lead_to_what_they_count(self, client, part):
        part(type="video", manufacturer="Tseng", model="ET4000")
        body = main_of(client.get("/stats").text)
        charts = body.split('<div class="twocol', 1)[1]
        assert '<h2 class="heading">Makers, by parts held</h2>' in charts
        assert '<div class="bars">' in charts
        assert '<a href="/browse?f=maker&v=Tseng">Tseng</a>' in charts

    def test_no_0_1_markup_is_left(self, client, computer):
        body = main_of(client.get("/stats").text)
        for gone in ('class="hero"', 'class="tiles"', 'class="tile"', 'class="rank"', "<table"):
            assert gone not in body, gone
