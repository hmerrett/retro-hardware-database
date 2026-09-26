"""The v0.2 component macros in `_ui.html`, and the `ui` filter their words pass
through (ADR-0031).

Rendered through the app's own environment, so a test sees the globals and filters
a page would. Nothing calls these macros yet -- the templates move onto them group
by group -- so this is where their markup is held to the design system's cards
until a page is.
"""

import re
from typing import ClassVar

import pytest
from markupsafe import Markup

from app.web import button_text, templates


def render(call: str, **context: object) -> str:
    source = '{% import "_ui.html" as U %}' + call
    return templates.env.from_string(source).render(**context).strip()


class TestTheUiFilter:
    @pytest.mark.parametrize(
        "text,lowered",
        [
            ("Add note", "add note"),
            ("Save", "save"),
            ("+ Computer", "+ computer"),
            ("‹ Prev", "‹ prev"),
        ],
    )
    def test_lower_case_takes_the_capital_off_the_first_word(self, text, lowered):
        assert button_text(text, "lower") == lowered

    @pytest.mark.parametrize("text", ["API docs", "OK", "CPU family", "RAM slots"])
    def test_an_acronym_keeps_its_capitals(self, text):
        assert button_text(text, "lower") == text

    def test_a_first_word_in_mixed_case_is_a_name_and_is_left_alone(self):
        # Only a word written Like This is one the setting capitalised; anything
        # else was spelt that way on purpose.
        assert button_text("MacBook charger", "lower") == "MacBook charger"

    def test_only_the_first_word_changes(self):
        assert button_text("Delete Photo", "lower") == "delete Photo"

    def test_capitalised_leaves_the_words_as_written(self):
        assert button_text("Add note", "cap") == "Add note"

    def test_the_filter_follows_the_installation_default_of_capitalised(self):
        assert render("{{ 'Add note' | ui }}") == "Add note"

    def test_markup_stays_markup(self):
        out = button_text(Markup("Add <b>note</b>"), "lower")
        assert isinstance(out, Markup)
        assert out == Markup("add <b>note</b>")


class TestButton:
    def test_a_button_is_a_button_of_type_button_by_default(self):
        assert render("{{ U.button('Edit') }}") == '<button class="btn" type="button">Edit</button>'

    def test_kind_and_size_become_classes(self):
        html = render("{{ U.button('Save', kind='primary', size='sm', type='submit') }}")
        assert 'class="btn primary sm"' in html
        assert 'type="submit"' in html

    def test_an_href_makes_it_a_link_drawn_the_same(self):
        html = render("{{ U.button('+ Computer', href='/computers/new') }}")
        assert html == '<a class="btn" href="/computers/new">+ Computer</a>'

    def test_an_icon_beside_a_word_is_hidden_from_a_screen_reader(self):
        html = render("{{ U.button('Photos', icon='camera') }}")
        assert re.search(r'<svg [^>]*aria-hidden="true"', html)
        assert html.endswith("Photos</button>")

    def test_an_icon_only_button_names_itself_from_its_label(self):
        html = render(
            "{{ U.button('Delete', kind='danger', size='sm', icon='trash', icon_only=true) }}"
        )
        assert 'class="btn danger sm icon"' in html
        assert 'aria-label="Delete"' in html
        # The label is the name, not a word printed beside the icon as well.
        assert re.sub(r"<svg.*</svg>", "", html).count("Delete") == 1

    def test_a_name_and_value_are_posted_with_the_form(self):
        html = render("{{ U.button('Delete', name='action', value='delete', type='submit') }}")
        assert 'name="action"' in html and 'value="delete"' in html

    def test_disabled_is_said_to_the_browser(self):
        assert " disabled" in render("{{ U.button('Edit', disabled=true) }}")

    def test_a_disabled_link_goes_nowhere_and_says_so(self):
        html = render("{{ U.button('Edit', href='/x', disabled=true) }}")
        assert "href" not in html
        assert 'aria-disabled="true"' in html

    def test_a_pressed_toggle_says_it_is_pressed_and_is_drawn_on(self):
        html = render("{{ U.button('Default photo', icon='star', pressed=true) }}")
        assert 'class="btn on"' in html and 'aria-pressed="true"' in html

    def test_an_unpressed_toggle_says_so_too(self):
        html = render("{{ U.button('Default photo', pressed=false) }}")
        assert 'aria-pressed="false"' in html and " on" not in html

    def test_the_label_is_escaped(self):
        assert "&lt;b&gt;" in render("{{ U.button('<b>') }}")


class TestField:
    def test_a_text_field_labels_its_control(self):
        html = render("{{ U.field('manufacturer', 'Manufacturer', value='Commodore') }}")
        assert html.startswith('<div class="field">')
        assert '<label for="manufacturer">Manufacturer</label>' in html
        assert (
            '<input class="input" id="manufacturer" name="manufacturer" value="Commodore">' in html
        )

    def test_a_note_goes_in_a_title_on_the_row(self):
        html = render("{{ U.field('serial', 'Serial number', note='As on the badge.') }}")
        assert html.startswith('<div class="field" title="As on the badge.">')

    def test_an_area_is_a_textarea_holding_its_value(self):
        html = render("{{ U.field('summary', 'Summary', kind='area', value='Dead fan.') }}")
        assert '<textarea class="input" id="summary" name="summary">Dead fan.</textarea>' in html

    def test_a_choice_marks_the_current_value_selected(self):
        html = render(
            "{{ U.field('condition', 'Condition', kind='choice', value='Working',"
            " choices=['Restored', 'Working']) }}"
        )
        assert '<select class="select" id="condition" name="condition">' in html
        assert '<option value="Working" selected>Working</option>' in html
        assert '<option value="Restored">Restored</option>' in html

    def test_a_choice_can_show_words_other_than_the_value(self):
        html = render(
            "{{ U.field('c', 'Case', kind='choice', value='cap', choices=[('cap', 'Capitalised')]) }}"
        )
        assert '<option value="cap" selected>Capitalised</option>' in html

    def test_a_switch_is_a_tick_with_its_label_beside_it(self):
        html = render("{{ U.field('for_sale', 'For sale', kind='switch', value=true) }}")
        assert '<label class="check">' in html
        assert 'type="checkbox" id="for_sale" name="for_sale" value="1" checked>' in html

    def test_a_pinned_field_is_disabled_and_says_it_is(self):
        html = render("{{ U.field('site_name', 'Name', value='The Loft', pinned=true) }}")
        assert 'class="field is-pinned"' in html
        assert " disabled" in html

    def test_an_error_marks_the_field_and_prints_the_message_under_it(self):
        html = render(
            "{{ U.field('year', 'Year', value='88', error='Needs four digits, like 1988.') }}"
        )
        assert 'class="field is-invalid"' in html
        assert 'aria-invalid="true"' in html
        assert 'aria-describedby="year-err"' in html
        assert '<p class="err" id="year-err">Needs four digits, like 1988.</p>' in html
        assert html.index("<input") < html.index('class="err"')

    def test_a_hint_is_printed_under_the_control_and_tied_to_it(self):
        html = render("{{ U.field('cpu', 'CPU', hint='Maker model-MHz.') }}")
        assert re.search(r'<input [^>]*aria-describedby="cpu-hint"', html)
        assert '<p class="hint" id="cpu-hint">Maker model-MHz.</p>' in html
        assert html.index("<input") < html.index('class="hint"')

    def test_a_hint_and_an_error_both_describe_the_control(self):
        html = render("{{ U.field('year', 'Year', hint='As made.', error='Four digits.') }}")
        assert 'aria-describedby="year-hint year-err"' in html
        assert html.index('class="hint"') < html.index('class="err"')

    def test_a_switch_ties_its_hint_to_the_tick(self):
        html = render("{{ U.field('private', 'Private', kind='switch', hint='Kept back.') }}")
        assert re.search(r'<input type="checkbox" [^>]*aria-describedby="private-hint"', html)

    def test_any_other_attribute_reaches_the_control(self):
        html = render(
            "{{ U.field('year', 'Year', type='number', min=0, list='dl_years',"
            " required=true, autofocus=false) }}"
        )
        control = re.search(r"<input [^>]*>", html).group(0)
        assert ' type="number"' in control and ' min="0"' in control
        assert ' list="dl_years"' in control and re.search(r" required[ >]", control)
        assert "autofocus" not in control

    def test_no_error_leaves_no_trace(self):
        html = render("{{ U.field('year', 'Year') }}")
        assert "aria-invalid" not in html and "err" not in html

    def test_an_error_on_a_choice_is_tied_to_the_select(self):
        html = render(
            "{{ U.field('c', 'Condition', kind='choice', choices=['A'], error='Choose one.') }}"
        )
        assert re.search(r'<select [^>]*aria-invalid="true" aria-describedby="c-err"', html)


class TestErrorSummary:
    def test_nothing_when_there_is_nothing_to_fix(self):
        assert render("{{ U.error_summary([]) }}") == ""

    def test_it_counts_the_errors_and_links_each_to_its_field(self):
        html = render(
            "{{ U.error_summary(errors) }}",
            errors=[
                ("year", "Year", "Needs four digits, like 1988."),
                ("acquired", "Acquired date", "Not a date."),
            ],
        )
        assert 'class="errsum" role="alert" tabindex="-1"' in html
        assert "<h2>2 things to fix before this can be saved</h2>" in html
        assert '<a href="#year">Year</a>' in html
        assert '<a href="#acquired">Acquired date</a>' in html

    def test_one_is_one_thing(self):
        html = render("{{ U.error_summary([('year', 'Year', 'Needs four digits.')]) }}")
        assert "<h2>1 thing to fix before this can be saved</h2>" in html


class TestChip:
    def test_a_plain_chip(self):
        assert render("{{ U.chip('Computer') }}") == '<span class="chip">Computer</span>'

    def test_a_tone_is_a_class(self):
        assert render("{{ U.chip('Done', tone='ok') }}") == '<span class="chip ok">Done</span>'

    def test_a_chip_with_an_href_is_a_link(self):
        assert render("{{ U.chip('Acorn A3000', href='/computers/RH-1') }}") == (
            '<a class="chip" href="/computers/RH-1">Acorn A3000</a>'
        )


class TestTable:
    COLS: ClassVar = [("Project", ""), ("Status", ""), ("Items", "num tight")]
    ROWS: ClassVar = [["Tandon PCA", "Planned", 4], ["IR AC control", "Done", ""]]

    def test_every_heading_carries_scope(self):
        html = render("{{ U.table(cols, rows) }}", cols=self.COLS, rows=self.ROWS)
        assert html.count('<th scope="col"') == 3

    def test_stacked_every_cell_after_the_first_says_what_it_is(self):
        html = render("{{ U.table(cols, rows) }}", cols=self.COLS, rows=self.ROWS)
        assert 'class="table stack"' in html
        assert html.count('data-label="Status"') == 2
        assert html.count('data-label="Items"') == 2
        assert 'data-label="Project"' not in html

    def test_a_column_class_reaches_its_heading_and_its_cells(self):
        html = render("{{ U.table(cols, rows) }}", cols=self.COLS, rows=self.ROWS)
        assert '<th scope="col" class="num tight">Items</th>' in html
        assert '<td class="num tight" data-label="Items">4</td>' in html

    def test_the_heading_row_is_the_tables_first_row(self):
        # The stacking rule hides tr:first-child, so a <thead> would hide the first
        # row of data along with the headings.
        html = render("{{ U.table(cols, rows) }}", cols=self.COLS, rows=self.ROWS)
        assert "<thead" not in html
        assert html.index("<th") < html.index("<td")

    def test_scroll_wraps_the_table_in_its_own_box(self):
        html = render("{{ U.table(cols, rows, mode='scroll') }}", cols=self.COLS, rows=self.ROWS)
        assert html.startswith('<div class="hscroll"><table class="table">')
        assert "data-label" not in html

    def test_plain_is_just_a_table(self):
        html = render("{{ U.table(cols, rows, mode='plain') }}", cols=self.COLS, rows=self.ROWS)
        assert html.startswith('<table class="table">')

    def test_a_cell_of_markup_is_kept_and_a_cell_of_text_is_escaped(self):
        rows = [[Markup('<a href="/p/1">Tandon</a>'), "<b>"]]
        html = render("{{ U.table(cols, rows) }}", cols=self.COLS[:2], rows=rows)
        assert '<a href="/p/1">Tandon</a>' in html
        assert "&lt;b&gt;" in html


class TestBanner:
    def test_a_warning_is_a_status_with_its_lead_word_first(self):
        html = render("{{ U.banner('warning', 'No login set.', 'Anyone can edit it.') }}")
        assert html == (
            '<div class="banner warning" role="status"><b>No login set.</b><span>Anyone can edit it.</span></div>'
        )

    def test_danger_interrupts(self):
        assert 'role="alert"' in render("{{ U.banner('danger', 'Not saved.') }}")

    def test_a_toast_is_the_same_banner_with_a_class(self):
        assert 'class="banner danger toast" role="alert"' in render(
            "{{ U.banner('danger toast', 'Changed') }}"
        )

    def test_no_text_leaves_no_empty_span(self):
        assert "<span" not in render("{{ U.banner('success', 'Saved.') }}")


class TestStats:
    def test_a_stat_tile_has_its_label_value_and_note(self):
        html = render("{{ U.stattile('Ports counted', 222, 'on 63 boards') }}")
        assert html == (
            '<div class="stattile"><div class="k">Ports counted</div>'
            '<div class="v">222</div><div class="n">on 63 boards</div></div>'
        )

    def test_a_stat_tile_with_somewhere_to_go_is_the_link(self):
        html = render("{{ U.stattile('Ports counted', 222, 'on 63 boards', href='/browse?f=x') }}")
        assert html.startswith('<a class="stattile" href="/browse?f=x"><div class="k">')
        assert html.endswith("</a>")

    def test_a_bar_names_what_it_counted_when_given_a_field(self):
        html = render("{{ U.bars([('Tseng Labs', 4, 'Tseng Labs')], f='maker') }}")
        assert '<a href="/browse?f=maker&v=Tseng%20Labs">Tseng Labs</a>' in html

    def test_bars_against_a_ceiling_are_drawn_against_it_not_the_largest(self):
        html = render("{{ U.bars([('Halfco', 50), ('Nearlyco', 83)], full=100, suffix='%') }}")
        assert '<i class="fill w-500"></i>' in html and '<i class="fill w-830"></i>' in html
        assert '<span class="n">83%</span>' in html

    def test_bars_are_sized_by_class_against_the_largest(self):
        html = render("{{ U.bars([('Storage', 124), ('Motherboard', 62), ('Power', 0)]) }}")
        assert '<i class="fill w-1000"></i>' in html
        assert '<i class="fill w-500"></i>' in html
        assert '<i class="fill w-0"></i>' in html
        # The number is always beside its bar, so the bar is never the only telling.
        assert '<span class="n">124</span>' in html

    def test_bars_of_nothing_do_not_divide_by_zero(self):
        assert 'class="fill w-0"' in render("{{ U.bars([('Storage', 0)]) }}")

    def test_every_bar_width_has_a_rule_to_paint_it(self):
        from app.datacss import DATA_CSS

        widths = set(
            re.findall(
                r"w-(\d+)", render("{{ U.bars(rows) }}", rows=[(str(n), n) for n in range(1, 200)])
            )
        )
        for w in widths:
            assert f".bars .fill.w-{w}" in DATA_CSS


class TestNavigation:
    def test_itemnav_has_back_position_and_neighbours(self):
        html = render(
            "{{ U.itemnav('/', 'All', '12 of 439', '/computers/RH-1', '/computers/RH-3') }}"
        )
        assert html.startswith('<nav class="itemnav" aria-label="Item">')
        assert '<span class="where">12 of 439</span>' in html
        assert 'rel="prev"' in html and 'rel="next"' in html

    def test_a_missing_neighbour_is_left_out_not_disabled(self):
        html = render("{{ U.itemnav('/', 'All', '1 of 439', '', '/computers/RH-2') }}")
        assert 'rel="prev"' not in html and "disabled" not in html
        assert 'rel="next"' in html

    def test_the_arrows_are_not_read_out(self):
        html = render("{{ U.itemnav('/', 'All', '2 of 3', '/a', '/b') }}")
        assert html.count('aria-hidden="true"') == 3

    def test_pager_links_the_pages_either_side(self):
        html = render("{{ U.pager(2, 12, '/?page=') }}")
        assert '<span class="where">Page 2 of 12</span>' in html
        assert 'href="/?page=1" rel="prev"' in html
        assert 'href="/?page=3" rel="next"' in html

    def test_pager_leaves_out_what_is_not_there(self):
        first = render("{{ U.pager(1, 3, '/?page=') }}")
        last = render("{{ U.pager(3, 3, '/?page=') }}")
        assert 'rel="prev"' not in first and 'rel="next"' in first
        assert 'rel="next"' not in last and 'rel="prev"' in last

    def test_one_page_needs_no_pager(self):
        assert render("{{ U.pager(1, 1, '/?page=') }}") == ""


class TestCard:
    """The gallery tile. `card(item)` takes a row as the gallery builds it."""

    @staticmethod
    def row(**over: object) -> dict[str, object]:
        class Obj:
            asset_id = "RH-0042"
            disposed = False

        row: dict[str, object] = {
            "obj": Obj(),
            "kind": "computer",
            "cat": "computer",
            "cat_label": "Computer",
            "name": "Acorn A3000",
            "year": 1989,
            "parent": "",
            "image": "",
            "placeholder": "placeholders/computer.svg",
            "ref_photo": False,
            "ref_icon": "",
        }
        row.update(over)
        return row

    def test_the_whole_card_is_one_link_to_the_item(self):
        html = render("{{ U.card(r) }}", r=self.row())
        assert html.startswith('<a class="card" href="/computers/RH-0042"')
        assert html.count("<a ") == 1 and html.endswith("</a>")

    def test_a_part_links_to_the_parts_page(self):
        html = render("{{ U.card(r) }}", r=self.row(kind="part"))
        assert 'href="/parts/RH-0042"' in html

    def test_it_reads_tag_name_and_chips(self):
        html = render("{{ U.card(r) }}", r=self.row())
        assert '<span class="aid">RH-0042</span>' in html
        assert '<span class="nm">Acorn A3000</span>' in html
        assert (
            '<span class="chips"><span class="chip">Computer</span>'
            '<span class="chip">1989</span></span>' in html
        )

    def test_a_part_in_a_machine_says_which(self):
        html = render("{{ U.card(r) }}", r=self.row(kind="part", parent="RH-0001"))
        assert '<span class="chip">in RH-0001</span>' in html

    def test_disposed_fades_the_photograph_and_says_so_in_a_chip(self):
        r = self.row()
        r["obj"].disposed = True
        html = render("{{ U.card(r) }}", r=r)
        assert html.startswith('<a class="card is-disposed"')
        assert '<span class="chip">Disposed</span>' in html

    def test_a_photograph_is_described_by_the_item_name(self):
        html = render("{{ U.card(r) }}", r=self.row(image="computers/RH-0042/a.jpg"))
        assert 'alt="Acorn A3000"' in html and 'loading="lazy"' in html
        assert "srcset=" in html

    def test_no_photograph_draws_the_placeholder_named_for_its_kind(self):
        html = render("{{ U.card(r) }}", r=self.row())
        assert '<img class="ph" src="/static/placeholders/computer.svg" alt="Computer"' in html

    def test_a_reference_photograph_is_marked(self):
        html = render(
            "{{ U.card(r) }}", r=self.row(image="computers/RH-0042/ref-a.jpg", ref_photo=True)
        )
        assert 'class="ref-badge"' in html and "Illustrative image" in html


class TestBezel:
    def test_a_recorded_bezel_takes_its_generated_class(self):
        from app.entry import bezel_class

        cls = bezel_class("Beige", "Yellowed")
        assert cls
        html = render("{{ U.bezel('Beige', 'Yellowed') }}")
        assert html == f'<span class="bezel {cls}" aria-hidden="true"></span>'

    def test_no_shade_is_hatched(self):
        assert (
            render("{{ U.bezel('', '') }}") == '<span class="bezel none" aria-hidden="true"></span>'
        )

    def test_small_is_a_class(self):
        assert 'class="bezel none sm"' in render("{{ U.bezel('', '', size='sm') }}")


class TestIcons:
    NEW: ClassVar = [
        "projects",
        "numbers",
        "models",
        "files",
        "settings",
        "theme",
        "logout",
        "plus",
        "collapse",
    ]

    def test_an_account_has_an_icon_of_its_own(self):
        """The menu's Account row, beside Log out (ADR-0032)."""
        html = render("{% import '_icons.html' as I %}{{ I.ico('user') }}")
        assert html.startswith("<svg ")

    @pytest.mark.parametrize("name", NEW)
    def test_the_nine_new_icons_are_drawn(self, name):
        html = render(f"{{% import '_icons.html' as I %}}{{{{ I.ico('{name}') }}}}")
        assert html.startswith("<svg ")

    def test_every_icon_is_hidden_from_a_screen_reader(self):
        # Beside a word the word names the control; on its own the control carries an
        # aria-label. Either way the drawing itself says nothing.
        source = templates.env.loader.get_source(templates.env, "_icons.html")[0]
        svgs = re.findall(r"<svg [^>]*>", source)
        assert len(svgs) == 23
        assert all('aria-hidden="true"' in s for s in svgs)
