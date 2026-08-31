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
        assert render("storage", "Capacity: 840MB") == "Capacity: 840 MiB"
        assert render("storage", "Capacity: 20GiB") == "Capacity: 20 GiB"

    def test_whole_megabytes_do_not_become_fractional_gigabytes(self):
        assert render("storage", "Capacity: 2047MB") == "Capacity: 2047 MiB"

    def test_a_value_that_is_not_a_number_is_kept_not_dropped(self):
        st = specstruct.parse("motherboard", "Cache: Fake")
        assert st.scalars["cache_kb"] is None
        assert st.attributes == [("Cache", "Fake")]

    def test_zero_is_a_value_not_an_absence(self):
        assert render("motherboard", "Cache: 0") == "Cache: 0 KiB"


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


class TestTheTwoSortsOfDriveSpeed:
    """One Speed key, two columns behind it: a spindle turns at 5400 rpm and an
    optical drive reads at 48×, and neither is a number of the other. Which is
    meant is written in the value, so a person types one Speed and reads one back.
    """

    def test_a_spindle_speed_is_still_rpm(self):
        st = specstruct.parse("storage", "Kind: Hard disk | Speed: 5400")
        assert st.scalars["speed_rpm"] == 5400
        assert "speed_x" not in st.scalars

    def test_a_rating_goes_to_its_own_column(self):
        st = specstruct.parse("storage", "Kind: Optical | Speed: 48x")
        assert st.scalars["speed_x"] == 48
        assert "speed_rpm" not in st.scalars

    @pytest.mark.parametrize("text,rendered", [
        ("48x", "48×"), ("48X", "48×"), ("48 x", "48×"), ("48×", "48×"),
        ("5400", "5400 rpm"), ("5400rpm", "5400 rpm"), ("7200 rpm", "7200 rpm"),
    ])
    def test_each_renders_in_the_unit_it_was_read_in(self, text, rendered):
        assert render("storage", f"Speed: {text}") == f"Speed: {rendered}"

    def test_a_speed_that_is_neither_is_still_not_lost(self):
        """The same fallback every unparseable quantity has: kept verbatim rather
        than dropped on the floor."""
        st = specstruct.parse("storage", "Speed: variable")
        assert st.attributes == [("Speed", "variable")]

    def test_a_medium_says_what_the_discs_are(self):
        st = specstruct.parse("storage", "Kind: Optical | Media: CD-RW")
        assert st.scalars["media"] == "CD-RW"

    def test_an_optical_drive_renders_in_the_canonical_order(self):
        assert render("storage", "Speed: 48x | Kind: Optical | Media: CD-RW") == \
            "Kind: Optical | Media: CD-RW | Speed: 48×"

    def test_it_reads_back_as_it_renders(self):
        once = render("storage", "Kind: Optical | Media: CD-RW | Speed: 48x")
        assert render("storage", once) == once
        assert specstruct.parse("storage", once).scalars["speed_x"] == 48


class TestABezel:
    """A full-height drive shows its bezel on the front of the machine, so a storage
    part records the same two things a fitted drive row does -- and so does a
    display, which is the same beige plastic gone the same colour.
    """

    def test_the_two_keys_map_to_their_own_columns(self):
        st = specstruct.parse("storage", "Kind: Hard disk | Colour: Beige | "
                                         "Yellowing: Heavily yellowed")
        assert st.scalars == {"kind": "Hard disk", "colour": "Beige",
                              "yellowing": "Heavily yellowed"}

    def test_they_come_last_in_the_canonical_order(self):
        assert render("storage", "Yellowing: Yellowed | Colour: Beige | "
                                 "Kind: Hard disk") == \
            "Kind: Hard disk | Colour: Beige | Yellowing: Yellowed"

    def test_either_alone_survives(self):
        assert render("storage", "Yellowing: Browned") == "Yellowing: Browned"
        assert render("storage", "Colour: Black") == "Colour: Black"

    def test_a_display_records_the_same_two(self):
        """A monitor's front is plastic that was made in a shade and has yellowed
        since, exactly as a drive's bezel is, so it answers in the same words."""
        st = specstruct.parse("display", "Type: CRT | Colour: Beige | "
                                         "Yellowing: Yellowed")
        assert st.scalars == {"tech": "CRT", "colour": "Beige",
                              "yellowing": "Yellowed"}

    def test_a_type_with_no_bezel_keeps_the_keys_verbatim(self):
        """A card has no plastic to describe, so on a type that is not asked the
        keys stay attributes rather than being quietly adopted."""
        st = specstruct.parse("video", "Chip: S3 | Colour: Beige")
        assert st.attributes == [("Colour", "Beige")]


class TestDriveCapacityFromGeometry:
    """A drive's geometry gives its capacity, so it need not be typed twice.

    What is typed always wins, because the geometry is not always the truth: a 20 GiB
    drive reports 16383/16/63 because CHS cannot address beyond about 8 GiB, and an
    RLL drive's sector count gives a different figure from its MFM formatted size.
    """

    def test_the_arithmetic_is_sectors_of_512_bytes(self):
        assert specstruct.chs_capacity_kb((615, 4, 17)) == 20910
        assert specstruct.chs_capacity_kb((1024, 16, 63)) == 516096

    def test_a_geometry_alone_gives_a_capacity(self):
        st = specstruct.parse("storage", "Kind: Hard disk | CHS: 1024/16/63")
        assert st.scalars["capacity_kb"] == 516096
        assert "Capacity: 504 MiB" in specstruct.format("storage", st)

    def test_a_stated_capacity_is_never_overwritten(self):
        st = specstruct.parse("storage", "CHS: 16383/16/63 | Capacity: 20GB")
        assert st.scalars["capacity_kb"] == 20971520

    def test_a_stated_capacity_the_columns_cannot_read_still_wins(self):
        """It is the reader's figure either way; it stays verbatim and no number is
        invented to replace it."""
        st = specstruct.parse("storage", "CHS: 615/4/17 | Capacity: 20MB (36MB?!)")
        assert st.scalars["capacity_kb"] is None
        assert ("Capacity", "20MB (36MB?!)") in st.attributes

    def test_no_geometry_derives_nothing(self):
        st = specstruct.parse("storage", "Kind: Hard disk")
        assert "capacity_kb" not in st.scalars

    def test_a_malformed_geometry_derives_nothing(self):
        st = specstruct.parse("storage", "Kind: Hard disk | CHS: lots")
        assert "capacity_kb" not in st.scalars

    def test_only_drives_are_measured_this_way(self):
        st = specstruct.parse("video", "Chip: ET4000")
        assert "capacity_kb" not in st.scalars

    def test_a_derived_capacity_survives_being_saved_again(self):
        """The rendered figure must re-read as the same number, or it would drift
        every time the part was saved."""
        once = specstruct.format(
            "storage", specstruct.parse("storage", "CHS: 615/4/17"))
        twice = specstruct.format("storage", specstruct.parse("storage", once))
        assert once == twice
        assert specstruct.parse("storage", once).scalars["capacity_kb"] == 20910


class TestADisplay:
    """A screen: what makes the picture, how big it is, and what it will show.

    The two questions about the picture-making are kept apart on purpose. A
    Trinitron is a CRT with an aperture grille in it, and if the trade name went in
    the same field as the technology then filing one would take it out of the count
    of CRTs -- so the tube or panel construction is its own column and both
    questions stay answerable.
    """

    def test_the_technology_and_the_tube_are_separate_columns(self):
        st = specstruct.parse("display", "Type: CRT | "
                                         "Panel: Aperture grille (Trinitron)")
        assert st.scalars == {"tech": "CRT",
                              "panel": "Aperture grille (Trinitron)"}

    def test_a_trinitron_still_counts_as_a_crt(self):
        """The whole reason for two columns: asking for every CRT finds this one."""
        st = specstruct.parse("display", "Type: CRT | Panel: Aperture grille "
                                         "(Trinitron) | Screen size: 21\"")
        assert st.scalars["tech"] == "CRT"

    @pytest.mark.parametrize("text,tenths", [
        ('14"', 140), ("14", 140), ('13.3"', 133), ("15in", 150),
        ("17 inch", 170), ("21.5", 215),
    ])
    def test_a_screen_size_is_tenths_of_an_inch(self, text, tenths):
        assert specstruct.parse(
            "display", f"Screen size: {text}").scalars["screen_in_tenths"] == tenths

    def test_a_whole_size_does_not_render_a_fraction(self):
        """A 14" monitor is a 14-inch monitor, not a 14.0-inch one."""
        assert render("display", "Screen size: 14") == 'Screen size: 14"'

    def test_a_fractional_size_survives_the_round_trip(self):
        assert render("display", 'Screen size: 13.3"') == 'Screen size: 13.3"'

    def test_a_refresh_rate_is_kept_as_written(self):
        """It stopped being one whole number when a screen was allowed to say it
        does several: 50 Hz for a television-rate mode and 85 for its best VGA one
        are both true of the same tube, and an integer could hold one of them."""
        st = specstruct.parse("display", "Refresh: 50 Hz, 85 Hz")
        assert st.scalars["refresh"] == "50 Hz, 85 Hz"

    def test_a_refresh_range_is_kept_as_written(self):
        st = specstruct.parse("display", "Refresh: 47–90 Hz")
        assert st.scalars["refresh"] == "47–90 Hz"

    @pytest.mark.parametrize("text,um", [
        ("0.28", 280), ("0.28 mm", 280), ("0.25mm", 250), ("280um", 280),
        ("280 µm", 280),
    ])
    def test_a_dot_pitch_is_micrometres_however_it_is_written(self, text, um):
        assert specstruct.parse(
            "display", f"Dot pitch: {text}").scalars["dot_pitch_um"] == um

    def test_a_dot_pitch_reads_back_in_millimetres(self):
        """Which is how it is written on the box and how anyone would type it."""
        assert render("display", "Dot pitch: 280um") == "Dot pitch: 0.28 mm"

    def test_a_resolution_is_kept_as_written(self):
        """A multisync tube does 640x480 through 1280x1024, and picking one of those
        to store as two numbers would be recording a fact nobody stated."""
        st = specstruct.parse("display", "Resolution: 640×480 to 1280×1024")
        assert st.scalars["resolution"] == "640×480 to 1280×1024"

    def test_a_size_that_is_not_a_number_is_kept_not_dropped(self):
        st = specstruct.parse("display", "Screen size: 9-inch-ish, unbadged")
        assert st.scalars["screen_in_tenths"] is None
        assert st.attributes == [("Screen size", "9-inch-ish, unbadged")]

    def test_the_canonical_order_runs_picture_size_signal_plastic(self):
        assert render("display", 'Yellowing: Yellowed | Interface: VGA (HD-15) | '
                                 'Screen size: 17" | Type: CRT') == \
            'Type: CRT | Screen size: 17" | Interface: VGA (HD-15) | ' \
            'Yellowing: Yellowed'

    def test_it_reads_back_as_it_renders(self):
        specs = ('Type: CRT | Panel: Aperture grille (Trinitron) | '
                 'Screen size: 21" | Aspect: 4:3 | Resolution: 1600×1200 | '
                 'Refresh: 85 Hz | Dot pitch: 0.25 mm | Interface: VGA (HD-15), '
                 'BNC | Picture: Colour | Colour: Beige | Yellowing: Yellowed')
        assert render("display", specs) == specs

    def test_a_screen_is_not_measured_like_a_drive(self):
        """Only a display has a screen size, so the key stays an attribute on
        anything else rather than being read as inches."""
        st = specstruct.parse("storage", 'Kind: Hard disk | Screen size: 14"')
        assert st.attributes == [("Screen size", '14"')]
