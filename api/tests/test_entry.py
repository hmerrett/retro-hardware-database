"""Vocabularies, amount handling and the quick-entry expanders."""
import pytest

from app import entry


class TestAmounts:
    @pytest.mark.parametrize("text,kb", [
        ("2MB", 2048), ("512KB", 512), ("512K", 512), ("2", 2048), ("1GB", 1048576),
    ])
    def test_to_kb(self, text, kb):
        assert entry.to_kb(text) == kb

    @pytest.mark.parametrize("text", ["", "lots", "20MB (36MB?!)", "64-256KB"])
    def test_to_kb_refuses_what_it_cannot_read(self, text):
        assert entry.to_kb(text) is None

    @pytest.mark.parametrize("kb,text", [(8192, "8 MB"), (640, "640 KB"), (0, "")])
    def test_fmt_kb(self, kb, text):
        assert entry.fmt_kb(kb) == text


class TestWhichUnitAFigureIsSaidIn:
    """Quantities are stored as plain KB integers so they sort in SQL; the unit to
    say them in is decided here, once, for spec columns and memory totals alike.
    """

    @pytest.mark.parametrize("kb,text", [
        (1024, "1 MB"),                 # not '1024 KB'
        (2048, "2 MB"),
        (8192, "8 MB"),
        (640, "640 KB"),                # below a megabyte, so KB is the right word
        (512, "512 KB"),
        (20971520, "20 GB"),            # not '20971520 KB'
        (1258291, "1.2 GB"),            # exact at one decimal
        (1475, "1.44 MB"),              # a floppy, exact at two
    ])
    def test_a_figure_that_can_be_said_exactly_is_said_that_way_everywhere(self, kb,
                                                                          text):
        """No split to make here: the same words serve the page and the form."""
        assert entry.fmt_kb(kb) == text
        assert entry.fmt_kb(kb, display=True) == text
        # And it survives the trip back, which is what lets the form use it: the
        # value shown is parsed again on the next save.
        assert entry.to_kb(text.replace(" ", "")) == kb

    @pytest.mark.parametrize("kb,text", [(2096128, "2047 MB"), (1572864, "1536 MB")])
    def test_a_whole_number_of_megabytes_stays_in_megabytes(self, kb, text):
        """2096128 KB is the 2047 MB BIOS limit, and calling it '2 GB' would lose the
        one thing about it worth knowing. The rule is not applied only to that one
        number, so 1536 MB keeps its unit too."""
        assert entry.fmt_kb(kb) == text
        assert entry.fmt_kb(kb, display=True) == text

    @pytest.mark.parametrize("kb,exact,shown", [
        (38828, "38828 KB", "37.9 MB"),        # a 38 MB drive, from its geometry
        (2116800, "2116800 KB", "2.02 GB"),
    ])
    def test_a_figure_that_cannot_is_rounded_only_where_it_is_read(self, kb, exact,
                                                                  shown):
        """Rounding cannot be undone, so it is offered to a page and a label and
        withheld from the form and the specs string, which are parsed back."""
        assert entry.fmt_kb(kb) == exact
        assert entry.fmt_kb(kb, display=True) == shown
        # Genuinely lossy -- which is the whole reason for the split, and worth
        # stating outright rather than implying.
        assert entry.to_kb(shown.replace(" ", "")) != kb

    def test_rounding_never_reaches_for_scientific_notation(self):
        """Three significant figures via '%g' would render 1000 as '1e+03'."""
        assert entry.fmt_kb(1024000 + 1, display=True) == "1000 MB"

    @pytest.mark.parametrize("kb", [1, 511, 640, 1023])
    def test_under_a_megabyte_stays_in_kilobytes(self, kb):
        assert entry.fmt_kb(kb, display=True) == f"{kb} KB"

    def test_nothing_is_nothing_rather_than_zero(self):
        """A machine with no memory recorded has no memory string, not '0 KB'. A
        spec column that says zero is a different matter -- see test_specstruct."""
        assert entry.fmt_kb(0) == ""
        assert entry.fmt_kb(None) == ""

    def test_memory_spec_amounts_normalise_to_kb(self):
        assert entry.normalise_amount("Size", "2MB") == "2048 KB"
        assert entry.normalise_amount("Interface", "2MB") == "2MB"


class TestBezelSwatches:
    """The shades and the yellowing levels, and the colour that stands for a pair of
    them. The mixing lives here so the chart, a form's live swatch and an item page
    cannot disagree about what 'heavily yellowed beige' looks like.
    """

    def test_a_shade_on_its_own_is_its_own_hex(self):
        assert entry.bezel_css("Beige") == entry.bezel_colour("Beige")["hex"]

    def test_nothing_recorded_draws_nothing(self):
        assert entry.bezel_css("", "") == ""
        assert entry.bezel_css("puce", "faded") == ""

    def test_yellowing_darkens_and_warms_the_shade(self):
        """Each step has to move the same way, or the ladder would not read as one."""
        def rgb(css):
            return [int(css[i:i + 2], 16) for i in (1, 3, 5)]
        steps = [entry.bezel_css("White", lvl) for lvl in
                 ("", "Lightly yellowed", "Yellowed", "Heavily yellowed", "Browned")]
        blues = [rgb(s)[2] for s in steps]
        assert blues == sorted(blues, reverse=True)
        # ...and every step stays a colour a browser will accept.
        assert all(len(s) == 7 and s.startswith("#") for s in steps)

    def test_the_same_level_reads_differently_on_a_different_shade(self):
        assert entry.bezel_css("White", "Yellowed") != entry.bezel_css("Beige", "Yellowed")

    def test_uneven_yellowing_is_drawn_as_two_tones(self):
        """One shade in two states is the only honest way to draw a patchy bezel."""
        css = entry.bezel_css("Beige", "Unevenly yellowed")
        assert css.startswith("linear-gradient(") and css.count("#") == 2

    def test_yellowing_with_no_shade_recorded_still_draws(self):
        """An unrestored find often shows only how yellow it is; it is drawn on some
        pale plastic, which is what almost every yellowed bezel started as."""
        assert entry.bezel_css("", "Heavily yellowed").startswith("#")

    def test_the_swatch_map_covers_every_pair(self):
        m = entry.bezel_swatch_map()
        assert m["Beige|Heavily yellowed"] == entry.bezel_css("Beige",
                                                              "Heavily yellowed")
        # Every pair but the one where neither is recorded, which draws nothing.
        assert len(m) == (len(entry.BEZEL_COLOURS) + 1) * (len(entry.YELLOWING) + 1) - 1
        assert "|" not in m

    def test_every_entry_carries_what_the_chart_needs(self):
        for col in entry.BEZEL_COLOURS:
            assert len(col["hex"]) == 7 and col["note"]
        for lvl in entry.YELLOWING:
            assert 0 < lvl["weight"] < 1 and len(lvl["tint"]) == 7 and lvl["note"]

    def test_no_shade_is_also_a_yellowing_level(self):
        """They are separate fields; a word that meant both would make a typed drive
        ambiguous."""
        assert not (set(entry.BEZEL_COLOUR_LABELS) & set(entry.YELLOWING_LABELS))


class TestInstalledRam:
    def test_modules_render_with_a_total(self):
        assert entry.format_ram_modules([("30p1m", 8)]) == "8× 1MB 30-pin (8 MB)"

    def test_module_totals_add_up_across_types(self):
        assert entry.ram_total_kb([("30p1m", 4), ("72p2m", 2)], []) == 8192

    def test_parity_chips_of_a_different_type_are_not_capacity(self):
        """An Amstrad PC1640 carries 4x 4464 for data with 2x 4164 alongside for
        their parity. Counting a bank's parity chips as data made RH-FTXR read
        656 KB when the machine has 640, which is what its sibling records."""
        chips = [("4164", 2), ("4464", 4), ("41256", 18)]
        assert entry.chip_capacity(chips) == (640, True)
        assert entry.ram_total_kb([], chips) == 640

    def test_a_bank_is_made_of_chips_of_the_same_depth(self):
        """64K-deep and 256K-deep chips cannot share a bank, so they are counted
        as separate ones: 18 bits at each depth is 16 data bits at each."""
        assert entry.chip_capacity([("4464", 4), ("4164", 2)]) == (128, True)
        assert entry.chip_capacity([("41256", 18)]) == (512, True)

    def test_two_wide_chips_make_one_byte_wide_bank(self):
        assert entry.chip_capacity([("4464", 2)]) == (64, False)

    def test_a_bank_without_parity_is_all_data(self):
        assert entry.chip_capacity([("4164", 8)]) == (64, False)

    def test_the_ninth_chip_adds_no_capacity(self):
        assert entry.chip_capacity([("4164", 9)])[0] == \
            entry.chip_capacity([("4164", 8)])[0]

    def test_no_chips_is_no_capacity(self):
        assert entry.chip_capacity([]) == (0, False)
        assert entry.chip_capacity([("4164", 0)]) == (0, False)

    def test_nine_by_one_chips_are_eight_of_data_plus_parity(self):
        """A byte-wide bank of x1 chips is 8 data chips plus a 9th for parity, so
        nine 32KB chips are 256 KB usable, not 288."""
        assert entry.ram_total_kb([], [("41256", 9)]) == 256
        assert entry.format_ram_chips([("41256", 9)]) == "9× 41256 (256 KB + parity)"

    def test_eight_chips_are_a_plain_bank(self):
        assert entry.ram_total_kb([], [("41256", 8)]) == 256
        assert "parity" not in entry.format_ram_chips([("41256", 8)])

    def test_eighteen_chips_are_two_parity_banks(self):
        assert entry.ram_total_kb([], [("41256", 18)]) == 512

    def test_a_wide_chip_can_carry_parity_too(self):
        """The old rule only looked for parity among ×1 chips, so nine ×4 chips
        counted as 1152 KB -- 36 data bits, four and a half bytes wide, which no
        byte-organised machine is. Thirty-two of those bits are data."""
        assert entry.ram_total_kb([], [("44256", 9)]) == 1024

    def test_a_bare_total_renders_when_there_is_no_breakdown(self):
        assert entry.render_installed_ram([], [], 8192, "") == "8 MB"

    def test_a_breakdown_hides_the_bare_total(self):
        out = entry.render_installed_ram([("30p1m", 8)], [], 8192, "")
        assert out == "8× 1MB 30-pin (8 MB)"

    def test_a_note_is_appended_not_swallowed(self):
        out = entry.render_installed_ram([], [], None, "16MB (2 banks)")
        assert out == "16MB (2 banks)"

    def test_empty_everywhere_renders_empty(self):
        assert entry.render_installed_ram([], [], None, "") == ""

    def test_zero_counts_are_ignored(self):
        assert entry.format_ram_modules([("30p1m", 0)]) == ""


class TestPortsAndSlots:
    def test_port_letter_codes_expand(self):
        assert entry.expand_ports("SSP") == "2× Serial, Parallel"

    def test_an_already_expanded_list_is_left_alone(self):
        assert entry.expand_ports("2× Serial, Game") == "2× Serial, Game"

    def test_a_port_list_parses_back_into_counts(self):
        assert entry.parse_port_list("2× Serial, Game") == [("Serial", 2), ("Game", 1)]

    def test_slot_shorthand_expands(self):
        assert entry.expand_slots("8I:2 16I:6 VLB") == \
            "2× 8-bit ISA, 6× 16-bit ISA, VLB"

    def test_slot_shorthand_is_order_independent(self):
        assert entry.expand_slots("VLB 16I:6") == entry.expand_slots("16I:6 VLB")

    def test_an_unknown_slot_token_is_ignored(self):
        assert entry.expand_slots("16I:2 nonsense") == "2× 16-bit ISA"

    def test_counts_render_without_a_one(self):
        assert entry.format_counts([("Serial", 2), ("Game", 1)]) == "2× Serial, Game"


class TestSpecStrings:
    def test_parse_specs_splits_on_pipes_and_colons(self):
        assert entry.parse_specs("Chip: S3 | Interface: PCI") == \
            [("Chip", "S3"), ("Interface", "PCI")]

    def test_a_keyless_chunk_keeps_an_empty_key(self):
        assert entry.parse_specs("840MB") == [("", "840MB")]

    def test_merge_spec_replaces_a_key_in_place(self):
        assert entry.merge_spec("Chip: S3 | Interface: PCI", "Chip", "Trident") == \
            "Chip: Trident | Interface: PCI"

    def test_merge_spec_appends_a_new_key(self):
        assert entry.merge_spec("Chip: S3", "Interface", "PCI") == \
            "Chip: S3 | Interface: PCI"

    def test_build_specs_drops_blanks(self):
        assert entry.build_specs([("Chip", "S3"), ("Interface", "")]) == "Chip: S3"


class TestNames:
    def test_deshout_lowers_shouted_words(self):
        assert entry.deshout("COMPAQ DESKPRO") == "Compaq Deskpro"

    def test_deshout_leaves_known_acronyms(self):
        assert entry.deshout("SCSI SDRAM") == "SCSI SDRAM"

    def test_deshout_leaves_short_words(self):
        assert entry.deshout("IBM PS/2") == "IBM PS/2"

    def test_display_name_prefers_an_explicit_name(self):
        assert entry.display_name({"name": "Beast", "manufacturer": "Acme"}) == "Beast"

    def test_display_name_falls_back_to_maker_and_model(self):
        assert entry.display_name(
            {"name": "", "manufacturer": "Acme", "model": "5000"}) == "Acme 5000"

    def test_display_name_falls_back_to_the_asset_id(self):
        assert entry.display_name({"asset_id": "RH-0001"}) == "RH-0001"

    @pytest.mark.parametrize("ptype,label", [
        ("io", "I/O"), ("ram", "Memory"), ("psu", "Power supply"),
        ("optical", "Optical drive"), ("floppy", "Floppy drive"),
    ])
    def test_every_vocabulary_type_has_a_written_label(self, ptype, label):
        """These three were missing, so type_label fell back to .title() and gave
        back "Psu"."""
        assert entry.type_label(ptype) == label

    def test_an_unknown_type_still_gets_something_readable(self):
        assert entry.type_label("gizmo") == "Gizmo"
