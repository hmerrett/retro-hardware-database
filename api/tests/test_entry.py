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

    def test_memory_spec_amounts_normalise_to_kb(self):
        assert entry.normalise_amount("Size", "2MB") == "2048 KB"
        assert entry.normalise_amount("Interface", "2MB") == "2MB"


class TestInstalledRam:
    def test_modules_render_with_a_total(self):
        assert entry.format_ram_modules([("30p1m", 8)]) == "8× 1MB 30-pin (8 MB)"

    def test_module_totals_add_up_across_types(self):
        assert entry.ram_total_kb([("30p1m", 4), ("72p2m", 2)], []) == 8192

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

    def test_wide_chips_are_summed_straight(self):
        assert entry.ram_total_kb([], [("44256", 9)]) == 9 * 128

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
