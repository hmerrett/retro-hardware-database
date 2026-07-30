"""Reading a typed drives field into rows, and rendering them back.

The parametrised cases are the eleven notations that were actually in the
collection when drives became rows, so a change here that mis-reads real data
fails rather than quietly restructuring it.
"""
import pytest

from app import drivedb

REAL_VALUES = [
    ("3.5-inch 1.44 MB floppy drive",
     [{"count": 1, "kind": "floppy", "form_factor": '3.5"', "size": "1.44MB",
       "model": ""}]),
    ('2 x 5.25" 360K',
     [{"count": 2, "kind": "floppy", "form_factor": '5.25"', "size": "360K",
       "model": ""}]),
    ('2x 5.25" 360K Floppy',
     [{"count": 2, "kind": "floppy", "form_factor": '5.25"', "size": "360K",
       "model": ""}]),
    ("Custom GOTEK 2.88MB",
     [{"count": 1, "kind": "Gotek", "form_factor": "", "size": "2.88MB",
       "model": "Custom"}]),
    ("Gotek floppy emulator (1.44MB)",
     [{"count": 1, "kind": "Gotek", "form_factor": "", "size": "1.44MB",
       "model": ""}]),
    ("Integral 2GB SD",
     [{"count": 1, "kind": "SD", "form_factor": "", "size": "2GB",
       "model": "Integral"}]),
    ("1GB CF",
     [{"count": 1, "kind": "CF", "form_factor": "", "size": "1GB", "model": ""}]),
    ("Mitsubishi MF504A-318U (1.2MB)",
     [{"count": 1, "kind": "floppy", "form_factor": "", "size": "1.2MB",
       "model": "Mitsubishi MF504A-318U"}]),
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
            "3.5-inch 1.44 MB floppy drive; SanDisk Extreme 4GB; "
            "Gotek floppy emulator (1.44MB)")
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

    @pytest.mark.parametrize("text,form", [
        ('5.25"', '5.25"'), ("5.25 inch", '5.25"'), ("3.5-inch", '3.5"'),
        ("3.5in", '3.5"'),
    ])
    def test_form_factors_are_written_several_ways(self, text, form):
        assert drivedb.parse_segment(f"{text} 360K")["form_factor"] == form

    @pytest.mark.parametrize("text,size", [
        ("360K", "360K"), ("360KB", "360K"), ("1.44 MB", "1.44MB"), ("2GB", "2GB"),
    ])
    def test_sizes_canonicalise(self, text, size):
        assert drivedb.parse_segment(f"floppy {text}")["size"] == size


class TestRendering:
    def test_a_count_of_one_is_not_written(self):
        assert drivedb.render([{"count": 1, "kind": "floppy", "form_factor": '5.25"',
                                "size": "360K", "model": ""}]) == '5.25" 360K floppy'

    def test_a_count_is_written_when_there_is_more_than_one(self):
        assert drivedb.render([{"count": 2, "kind": "floppy", "form_factor": '5.25"',
                                "size": "360K", "model": ""}]) == '2× 5.25" 360K floppy'

    def test_the_model_leads(self):
        assert drivedb.render([{"count": 1, "kind": "SD", "form_factor": "",
                                "size": "2GB", "model": "Integral"}]) == "Integral 2GB SD"

    def test_drives_are_joined_with_semicolons(self):
        out = drivedb.render([
            {"count": 2, "kind": "floppy", "form_factor": '5.25"', "size": "360K",
             "model": ""},
            {"count": 1, "kind": "Gotek", "form_factor": "", "size": "1.44MB",
             "model": ""}])
        assert out == '2× 5.25" 360K floppy; 1.44MB Gotek'

    def test_a_note_comes_last(self):
        assert drivedb.render([], "and a tape streamer") == "and a tape streamer"

    @pytest.mark.parametrize("text,_expected", REAL_VALUES)
    def test_rendering_a_parse_is_stable(self, text, _expected):
        drives, note = drivedb.from_string(text)
        once = drivedb.render(drives, note)
        assert drivedb.render(*drivedb.from_string(once)) == once


class TestEmpties:
    @pytest.mark.parametrize("text", ["", "   ", ";", " ; "])
    def test_nothing_in_nothing_out(self, text):
        assert drivedb.from_string(text) == ([], "")

    def test_a_segment_of_punctuation_yields_no_drive(self):
        assert drivedb.parse_segment(" - ") is None
