"""Reading a typed drives field into rows, and rendering them back.

The parametrised cases are the eleven notations that were actually in the
collection when drives became rows, so a change here that mis-reads real data
fails rather than quietly restructuring it.
"""

import pytest

from app import drivedb, entry


def drive(**fields):
    """A drive row with everything unsaid left blank, so a case says only what it
    is about."""
    return {
        "count": 1,
        "kind": "",
        "form_factor": "",
        "size": "",
        "media": "",
        "speed": "",
        "model": "",
        "colour": "",
        "yellowing": "",
    } | fields


REAL_VALUES = [
    ("3.5-inch 1.44 MB floppy drive", [drive(kind="floppy", form_factor='3.5"', size="1.44MB")]),
    ('2 x 5.25" 360K', [drive(count=2, kind="floppy", form_factor='5.25"', size="360K")]),
    ('2x 5.25" 360K Floppy', [drive(count=2, kind="floppy", form_factor='5.25"', size="360K")]),
    ("Custom GOTEK 2.88MB", [drive(kind="Gotek", size="2.88MB", model="Custom")]),
    ("Gotek floppy emulator (1.44MB)", [drive(kind="Gotek", size="1.44MB")]),
    ("Integral 2GB SD", [drive(kind="SD", size="2GB", model="Integral")]),
    ("1GB CF", [drive(kind="CF", size="1GB")]),
    (
        "Mitsubishi MF504A-318U (1.2MB)",
        [drive(kind="floppy", size="1.2MB", model="Mitsubishi MF504A-318U")],
    ),
    # The two optical drives on file, as their descriptions read before 0017 gave
    # the two things they say fields of their own.
    ("CDRW 48x", [drive(kind="optical", media="CD-RW", speed="48×")]),
    ("48x CD-ROM Drive", [drive(kind="optical", media="CD-ROM", speed="48×")]),
]


class TestParsingRealValues:
    @pytest.mark.parametrize("text,expected", REAL_VALUES)
    def test_a_segment_reads_as_recorded(self, text, expected):
        assert drivedb.from_string(text)[0] == expected

    def test_semicolons_separate_drives(self):
        drives, note = drivedb.from_string('1x GOTEK; 1x 5.25" 360K')
        assert [d["kind"] for d in drives] == ["Gotek", "floppy"]
        assert note == ""

    def test_a_stray_semicolon_does_not_make_an_empty_drive(self):
        drives, _ = drivedb.from_string('1x 5.25" 1.2MB ; 1x 5.25" 360K')
        assert len(drives) == 2

    def test_three_drives_of_different_kinds(self):
        drives, _ = drivedb.from_string(
            "3.5-inch 1.44 MB floppy drive; SanDisk Extreme 4GB; Gotek floppy emulator (1.44MB)"
        )
        assert [d["kind"] for d in drives] == ["floppy", "", "Gotek"]


class TestInference:
    def test_a_floppy_size_implies_a_floppy(self):
        """'2 x 5.25" 360K' names no kind, but nothing else comes in 360K."""
        assert drivedb.parse_segment('2 x 5.25" 360K')["kind"] == "floppy"

    def test_an_emulator_is_a_gotek_even_beside_the_word_floppy(self):
        assert drivedb.parse_segment("Gotek floppy emulator")["kind"] == "Gotek"

    def test_a_card_capacity_implies_nothing(self):
        """A bare '4GB' could be SD or CF, so neither is asserted."""
        assert drivedb.parse_segment("SanDisk Extreme 4GB")["kind"] == ""

    def test_unrecognised_words_become_the_model(self):
        assert drivedb.parse_segment("Mitsumi D503V")["model"] == "Mitsumi D503V"

    def test_descriptive_noise_is_dropped(self):
        d = drivedb.parse_segment("3.5-inch 1.44 MB floppy drive")
        assert d["model"] == ""

    @pytest.mark.parametrize(
        "text,form",
        [
            ('5.25"', '5.25"'),
            ("5.25 inch", '5.25"'),
            ("3.5-inch", '3.5"'),
            ("3.5in", '3.5"'),
        ],
    )
    def test_form_factors_are_written_several_ways(self, text, form):
        assert drivedb.parse_segment(f"{text} 360K")["form_factor"] == form

    @pytest.mark.parametrize(
        "text,size",
        [
            ("360K", "360K"),
            ("360KB", "360K"),
            ("1.44 MB", "1.44MB"),
            ("2GB", "2GB"),
        ],
    )
    def test_sizes_canonicalise(self, text, size):
        assert drivedb.parse_segment(f"floppy {text}")["size"] == size


class TestRendering:
    def test_a_count_of_one_is_not_written(self):
        assert (
            drivedb.render(
                [
                    {
                        "count": 1,
                        "kind": "floppy",
                        "form_factor": '5.25"',
                        "size": "360K",
                        "model": "",
                    }
                ]
            )
            == '5.25" 360K floppy'
        )

    def test_a_count_is_written_when_there_is_more_than_one(self):
        assert (
            drivedb.render(
                [
                    {
                        "count": 2,
                        "kind": "floppy",
                        "form_factor": '5.25"',
                        "size": "360K",
                        "model": "",
                    }
                ]
            )
            == '2× 5.25" 360K floppy'
        )

    def test_the_model_leads(self):
        assert (
            drivedb.render(
                [{"count": 1, "kind": "SD", "form_factor": "", "size": "2GB", "model": "Integral"}]
            )
            == "Integral 2GB SD"
        )

    def test_drives_are_joined_with_semicolons(self):
        out = drivedb.render(
            [
                {"count": 2, "kind": "floppy", "form_factor": '5.25"', "size": "360K", "model": ""},
                {"count": 1, "kind": "Gotek", "form_factor": "", "size": "1.44MB", "model": ""},
            ]
        )
        assert out == '2× 5.25" 360K floppy; 1.44MB Gotek'

    def test_a_note_comes_last(self):
        assert drivedb.render([], "and a tape streamer") == "and a tape streamer"

    @pytest.mark.parametrize("text,_expected", REAL_VALUES)
    def test_rendering_a_parse_is_stable(self, text, _expected):
        drives, note = drivedb.from_string(text)
        once = drivedb.render(drives, note)
        assert drivedb.render(*drivedb.from_string(once)) == once


class TestTheBezel:
    """Two things about one piece of plastic: the shade it was made in, and how far
    it has yellowed. Typed text has to read the same as the two menus, or the same
    drive would be recorded differently depending on where it was entered.
    """

    @pytest.mark.parametrize(
        "text,colour,level",
        [
            ("3.5in 1.44MB floppy beige", "Beige", ""),
            ("3.5in 1.44MB floppy (beige)", "Beige", ""),
            ("5.25in 360K floppy, yellowed", "", "Yellowed"),
            ("1.44MB floppy heavily yellowed", "", "Heavily yellowed"),
            ("Gotek black", "Black", ""),
            ("3.5in 1.44MB floppy (beige, heavily yellowed)", "Beige", "Heavily yellowed"),
            ("floppy yellowed beige", "Beige", "Yellowed"),
        ],
    )
    def test_both_are_read_from_what_was_typed(self, text, colour, level):
        d = drivedb.parse_segment(text)
        assert (d["colour"], d["yellowing"]) == (colour, level)

    @pytest.mark.parametrize(
        "text,colour",
        [
            ("floppy off-white", "Off-white"),
            ("floppy light grey", "Light grey"),
            ("floppy grey-beige", "Grey-beige"),
        ],
    )
    def test_a_two_word_shade_is_one_shade(self, text, colour):
        """'off-white' is not 'white' with a stray word, and 'light grey' is not
        'grey' after one -- either mistake would leave half of it in the model."""
        d = drivedb.parse_segment(text)
        assert (d["colour"], d["model"]) == (colour, "")

    @pytest.mark.parametrize(
        "text,level",
        [
            ("floppy unevenly yellowed", "Unevenly yellowed"),
            ("floppy badly yellowed", "Heavily yellowed"),
            ("floppy yellowing", "Yellowed"),
            ("floppy patchy", "Unevenly yellowed"),
        ],
    )
    def test_a_two_word_level_is_one_level(self, text, level):
        d = drivedb.parse_segment(text)
        assert (d["yellowing"], d["model"]) == (level, "")

    @pytest.mark.parametrize(
        "text,colour",
        [
            ("floppy gray", "Grey"),
            ("floppy cream", "Off-white"),
            ("floppy light gray", "Light grey"),
        ],
    )
    def test_the_looser_words_land_on_a_label(self, text, colour):
        assert drivedb.parse_segment(text)["colour"] == colour

    def test_browning_is_a_level_not_a_shade(self):
        """'brown' describes what has happened to a bezel, not what it was made in
        -- there is no brown in the shade list to mistake it for."""
        d = drivedb.parse_segment("floppy brown")
        assert (d["yellowing"], d["colour"], d["model"]) == ("Browned", "", "")

    def test_every_label_answers_to_itself(self):
        for label in entry.BEZEL_COLOUR_LABELS:
            assert drivedb.parse_segment(f"floppy {label}")["colour"] == label
        for label in entry.YELLOWING_LABELS:
            assert drivedb.parse_segment(f"floppy {label}")["yellowing"] == label

    def test_a_bezel_alone_is_a_drive_worth_recording(self):
        """Half a drive is still a drive: the bezel is beige even if nobody has
        written down what kind it is yet."""
        assert drivedb.parse_segment("beige")["colour"] == "Beige"
        assert drivedb.parse_segment("yellowed")["yellowing"] == "Yellowed"

    def test_neither_is_taken_from_inside_a_word(self):
        d = drivedb.parse_segment("Greyhound 1.44MB floppy")
        assert (d["colour"], d["yellowing"]) == ("", "")

    def test_it_renders_in_brackets_at_the_end(self):
        assert (
            drivedb.render(
                [
                    {
                        "count": 1,
                        "kind": "floppy",
                        "form_factor": '3.5"',
                        "size": "1.44MB",
                        "model": "",
                        "colour": "Beige",
                        "yellowing": "Heavily yellowed",
                    }
                ]
            )
            == '3.5" 1.44MB floppy (beige, heavily yellowed)'
        )

    def test_either_alone_renders_too(self):
        row = {"count": 1, "kind": "floppy", "form_factor": "", "size": "", "model": ""}
        assert drivedb.render([row | {"colour": "Beige"}]) == "floppy (beige)"
        assert drivedb.render([row | {"yellowing": "Yellowed"}]) == "floppy (yellowed)"

    def test_a_count_still_leads(self):
        assert (
            drivedb.render(
                [
                    {
                        "count": 2,
                        "kind": "floppy",
                        "form_factor": '5.25"',
                        "size": "360K",
                        "model": "",
                        "colour": "Off-white",
                        "yellowing": "Yellowed",
                    }
                ]
            )
            == '2× 5.25" 360K floppy (off-white, yellowed)'
        )

    @pytest.mark.parametrize("colour", ["", "Beige", "Off-white", "Light grey"])
    @pytest.mark.parametrize("level", ["", "Yellowed", "Heavily yellowed", "Unevenly yellowed"])
    def test_rendering_a_bezel_reads_back_the_same(self, colour, level):
        """The string is a cache of the rows, so it has to parse back into them --
        a bezel that renders one way and reads another would drift on every save."""
        rows = [
            drive(
                kind="floppy",
                form_factor='3.5"',
                size="1.44MB",
                model="Mitsumi",
                colour=colour,
                yellowing=level,
            )
        ]
        once = drivedb.render(rows)
        assert drivedb.from_string(once)[0] == rows
        assert drivedb.render(*drivedb.from_string(once)) == once


class TestOpticalDrives:
    """The drive with no capacity to state: what it does with a disc, and how fast.
    Typed text has to read the same as the two pickers, or the same drive would be
    recorded differently depending on where it was entered."""

    @pytest.mark.parametrize(
        "text,media",
        [
            ("CD-ROM", "CD-ROM"),
            ("cdrom", "CD-ROM"),
            ("CD", "CD-ROM"),
            ("CD-RW", "CD-RW"),
            ("cdrw", "CD-RW"),
            ("CDW", "CD-RW"),
            ("CD-R", "CD-R"),
            ("DVD", "DVD-ROM"),
            ("DVD-ROM", "DVD-ROM"),
            ("DVDRW", "DVD±RW"),
            ("DVD+RW", "DVD±RW"),
            ("DVD-RAM", "DVD-RAM"),
            ("Blu-ray", "Blu-ray"),
        ],
    )
    def test_the_ways_a_medium_is_written(self, text, media):
        assert drivedb.parse_segment(f"{text} drive")["media"] == media

    def test_every_medium_answers_to_itself(self):
        for label in entry.OPTICAL_MEDIA:
            assert drivedb.parse_segment(label)["media"] == label

    def test_a_medium_makes_it_an_optical_drive(self):
        """Nothing but an optical drive takes a CD-RW, so the kind need not be said
        as well -- and the word "cd" the kind list knows has been taken out of the
        text by the medium on its way past."""
        assert drivedb.parse_segment("CD-RW 48x")["kind"] == "optical"

    def test_a_medium_is_one_designation_not_a_kind_and_a_stray_word(self):
        d = drivedb.parse_segment("Plextor CD-RW")
        assert (d["media"], d["model"]) == ("CD-RW", "Plextor")

    def test_a_model_that_begins_with_one_keeps_it(self):
        """A drive modelled "CD-120" is an optical drive, but those two letters are
        its model's -- taking them would leave a bare "120" behind."""
        d = drivedb.parse_segment("Chinon CD-120 optical")
        assert (d["media"], d["kind"], d["model"]) == ("", "optical", "Chinon CD-120")

    @pytest.mark.parametrize("text", ["48x", "48X", "48 x", "48×"])
    def test_the_ways_a_rating_is_written(self, text):
        assert drivedb.parse_segment(f"{text} CD-ROM")["speed"] == "48×"

    def test_every_rating_answers_to_itself(self):
        for label in entry.OPTICAL_SPEEDS:
            assert drivedb.parse_segment(f"{label} CD-ROM")["speed"] == label

    def test_a_lone_rating_is_the_speed_not_a_count(self):
        """The one "N×" beside a medium is what the drive is being described by --
        a 2× CD-ROM is a real drive, and two of them is not what someone writing
        "2x CD-ROM" means."""
        for text, speed in (("48x CD-ROM", "48×"), ("2x CD-ROM", "2×")):
            d = drivedb.parse_segment(text)
            assert (d["count"], d["speed"]) == (1, speed)

    @pytest.mark.parametrize(
        "text,speed",
        [
            ("52x32x52x CD-RW", "52×/32×/52×"),
            ("4x 2x 20x CD RW", "4×/2×/20×"),
            ("CD-RW 48x/24x/48x", "48×/24×/48×"),
            ("CD-RW 8×/4×/32×", "8×/4×/32×"),
        ],
    )
    def test_a_writers_three_figures_are_one_rating(self, text, speed):
        """What it writes, rewrites and reads. Three of the four optical drives on
        file are written this way, and none of them is three drives."""
        d = drivedb.parse_segment(text)
        assert (d["count"], d["speed"], d["media"]) == (1, speed, "CD-RW")

    def test_a_bay_standing_after_a_rating_is_not_another_figure(self):
        d = drivedb.parse_segment('48x CD-RW 5.25"')
        assert (d["speed"], d["form_factor"]) == ("48×", '5.25"')

    def test_a_count_of_unrated_drives_is_written_without_the_mark(self):
        """Which is how render() writes it, so that it reads back as a count."""
        d = drivedb.parse_segment("2 CD-RW optical")
        assert (d["count"], d["speed"], d["media"]) == (2, "", "CD-RW")

    def test_a_rating_is_only_read_where_a_drive_could_have_one(self):
        """'2 x 5.25" 360K' is two floppies, and always was: nothing but an optical
        drive is rated in ×, so nothing else goes looking for one."""
        d = drivedb.parse_segment('2 x 5.25" 360K')
        assert (d["count"], d["speed"]) == (2, "")

    def test_a_rating_is_not_taken_from_inside_a_word(self):
        """A model number ending in a digit beside an x is not a speed."""
        assert drivedb.parse_segment("Sony CDU31A optical")["speed"] == ""

    def test_it_renders_as_it_is_said_out_loud(self):
        assert (
            drivedb.render([drive(kind="optical", form_factor='5.25"', media="CD-RW", speed="48×")])
            == '5.25" 48× CD-RW optical'
        )

    def test_the_model_still_leads_and_the_bezel_still_trails(self):
        assert (
            drivedb.render(
                [
                    drive(
                        kind="optical",
                        form_factor='5.25"',
                        media="CD-ROM",
                        speed="24×",
                        model="Mitsumi",
                        colour="Beige",
                        yellowing="Yellowed",
                    )
                ]
            )
            == 'Mitsumi 5.25" 24× CD-ROM optical (beige, yellowed)'
        )

    @pytest.mark.parametrize("media", ["", *entry.OPTICAL_MEDIA])
    @pytest.mark.parametrize("speed", ["", "2×", "48×"])
    def test_rendering_reads_back_the_same(self, media, speed):
        """The string is a cache of the rows, so it has to parse back into them."""
        rows = [
            drive(
                count=2,
                kind="optical",
                form_factor='5.25"',
                media=media,
                speed=speed,
                model="Plextor",
            )
        ]
        once = drivedb.render(rows)
        assert drivedb.from_string(once)[0] == rows
        assert drivedb.render(*drivedb.from_string(once)) == once


class TestEmpties:
    @pytest.mark.parametrize("text", ["", "   ", ";", " ; "])
    def test_nothing_in_nothing_out(self, text):
        assert drivedb.from_string(text) == ([], "")

    def test_a_segment_of_punctuation_yields_no_drive(self):
        assert drivedb.parse_segment(" - ") is None
