"""The specs string <-> Struct conversion, which every part write goes through."""
import pytest

from app import specstruct


def render(ptype, specs):
    """Parse and format again: what a part's specs string canonicalises to."""
    return specstruct.format(ptype, specstruct.parse(ptype, specs))


class TestScalars:
    def test_keys_map_to_columns(self):
        st = specstruct.parse("video", "Chip: Trident 9440 | Interface: PCI")
        assert st.scalars == {"chip": "Trident 9440", "interface": "PCI"}

    def test_aliases_collapse(self):
        assert specstruct.parse("video", "Chipset: S3").scalars["chip"] == "S3"

    def test_unknown_key_is_kept_as_an_attribute(self):
        st = specstruct.parse("video", "Chip: S3 | Voltage: 5V")
        assert st.scalars == {"chip": "S3"}
        assert st.attributes == [("Voltage", "5V")]

    def test_keyless_value_is_kept_verbatim(self):
        st = specstruct.parse("sound", "ES1869F")
        assert st.attributes == [("", "ES1869F")]

    def test_free_form_type_keeps_everything_as_attributes(self):
        st = specstruct.parse("peripheral", "Type: Mouse | Interface: PS/2")
        assert st.scalars == {}
        assert st.attributes == [("Type", "Mouse"), ("Interface", "PS/2")]


class TestNumbers:
    @pytest.mark.parametrize("text,kb", [
        ("2MB", 2048), ("512KB", 512), ("1.44MB", 1475), ("20GB", 20971520),
    ])
    def test_memory_amounts_become_kb(self, text, kb):
        assert specstruct.parse("ram", f"Size: {text}").scalars["size_kb"] == kb

    def test_a_bare_capacity_is_megabytes(self):
        assert specstruct.parse("storage", "Capacity: 44").scalars["capacity_kb"] == 45056

    def test_a_bare_cache_is_kilobytes(self):
        assert specstruct.parse("motherboard", "Cache: 256").scalars["cache_kb"] == 256

    def test_speeds_become_khz_and_survive_fractions(self):
        assert specstruct.parse("cpu", "Speed: 4.77MHz").scalars["speed_khz"] == 4770
        assert render("cpu", "Speed: 4.77MHz") == "Speed: 4.77 MHz"

    def test_capacity_renders_in_the_unit_a_person_would_type(self):
        assert render("storage", "Capacity: 840MB") == "Capacity: 840 MB"
        assert render("storage", "Capacity: 20GB") == "Capacity: 20 GB"

    def test_whole_megabytes_do_not_become_fractional_gigabytes(self):
        assert render("storage", "Capacity: 2047MB") == "Capacity: 2047 MB"

    def test_a_value_that_is_not_a_number_is_kept_not_dropped(self):
        st = specstruct.parse("motherboard", "Cache: Fake")
        assert st.scalars["cache_kb"] is None
        assert st.attributes == [("Cache", "Fake")]

    def test_zero_is_a_value_not_an_absence(self):
        assert render("motherboard", "Cache: 0") == "Cache: 0 KB"


class TestCountLists:
    def test_slots_parse_into_counts(self):
        st = specstruct.parse("motherboard", "Slots: 2× 8-bit ISA, 6× 16-bit ISA, VLB")
        assert st.slots == [("8-bit ISA", 2), ("16-bit ISA", 6), ("VLB", 1)]

    def test_a_single_item_renders_without_a_count(self):
        assert render("motherboard", "Slots: 1× VLB") == "Slots: VLB"

    def test_ports_and_ram_slots_are_separate_lists(self):
        st = specstruct.parse("motherboard", "RAM slots: 4× 72-pin SIMM | Ports: 2× Serial")
        assert st.ram_slots == [("72-pin SIMM", 4)]
        assert st.ports == [("Serial", 2)]


class TestStorageGeometry:
    def test_chs_splits_into_three_numbers(self):
        assert specstruct.parse("storage", "CHS: 1647/16/63").chs == (1647, 16, 63)

    def test_a_malformed_chs_is_kept_as_text(self):
        st = specstruct.parse("storage", "CHS: lots")
        assert st.chs is None
        assert st.attributes == [("CHS", "lots")]


class TestCanonicalOrder:
    def test_keys_come_out_in_display_order(self):
        assert render("sound", "Interface: ISA | Chip: ES1869F") == \
            "Chip: ES1869F | Interface: ISA"

    def test_formatting_is_idempotent(self):
        once = render("storage", "Kind: Hard disk | Capacity: 840MB | CHS: 1647/16/63")
        assert render("storage", once) == once

    def test_attributes_come_after_the_known_keys(self):
        assert render("video", "Voltage: 5V | Chip: S3") == "Chip: S3 | Voltage: 5V"
