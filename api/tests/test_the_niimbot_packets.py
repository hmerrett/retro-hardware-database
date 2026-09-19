"""The NIIMBOT driver's constants, against traffic recorded from a real printer.

`static/niimbot.js` cannot be run here -- it needs a browser and a printer, and the
suite has neither. What it can be held to is the part that is pure fact and the
easiest to get wrong by a keystroke: the framing, the checksum rule and the command
numbers. A mistyped byte there is a printer that sits there doing nothing, with no
error to read and nothing on screen to suggest which of two hundred lines is wrong.

The packets below were recorded from a NIIMBOT B1 (firmware 5.22) and are published
in niimbluelib's `test/dumps.js` (MIT, https://github.com/MultiMote/niimbluelib),
which is also where the command numbers were read from. They are quoted here as
what a real printer actually said.

What this does **not** test is whether the print sequence is right. Those packets
are not in the recording -- it captures only the opening exchange -- so they come
from the reference implementation's source rather than from a wire. Until this
driver has met a printer, that part is read and not proven, and saying so is worth
more than a test that implies otherwise.
"""

import re
from pathlib import Path

import pytest

DRIVER = Path(__file__).resolve().parent.parent / "app" / "static" / "niimbot.js"

# Recorded from a B1 on firmware 5.22. Each is a whole packet, head to tail.
RECORDED = {
    "Connect": "55 55 c1 01 01 c1 aa aa",
    "In_Connect": "55 55 c2 01 03 c0 aa aa",
    "PrinterStatusData": "55 55 a5 01 01 a5 aa aa",
    "In_PrinterStatusData": "55 55 b5 10 30 30 03 20 00 c8 00 00 00 0f 01 02 04 01 98 00 df aa aa",
    "PrinterInfo": "55 55 40 01 08 49 aa aa",
    "In_PrinterInfoSerialNumber": "55 55 4b 0a 47 33 32 37 30 37 31 31 38 35 3a aa aa",
    "In_PrinterInfoBluetoothAddress": "55 55 4d 06 27 03 07 17 6e 82 93 aa aa",
    "In_PrinterInfoChargeLevel": "55 55 4a 01 04 4f aa aa",
    "Heartbeat": "55 55 dc 01 01 dc aa aa",
}

# What the driver sends and what it waits to hear back, as niimbluelib names and
# numbers them.
COMMANDS = {
    "printStart": 0x01,
    "pageStart": 0x03,
    "setPageSize": 0x13,
    "setDensity": 0x21,
    "setLabelType": 0x23,
    "printEmptyRow": 0x84,
    "printBitmapRow": 0x85,
    "printStatus": 0xA3,
    "pageEnd": 0xE3,
    "printEnd": 0xF3,
}

ANSWERS = {
    "printStart": 0x02,
    "pageStart": 0x04,
    "setPageSize": 0x14,
    "setDensity": 0x31,
    "setLabelType": 0x33,
    "printStatus": 0xB3,
    "pageEnd": 0xE4,
    "printEnd": 0xF4,
}


def table(name):
    """One of the driver's constant tables, read out of the file."""
    source = DRIVER.read_text(encoding="utf-8")
    body = source.split(f"const {name} = {{", 1)[1].split("};", 1)[0]
    return {k: int(v, 16) for k, v in re.findall(r"(\w+):\s*(0x[0-9a-f]+)", body)}


def bytes_of(recorded):
    return [int(b, 16) for b in recorded.split()]


@pytest.mark.parametrize("name", sorted(RECORDED))
def test_the_checksum_rule_matches_what_a_real_printer_sends(name):
    """Command, length and every byte of the data, exclusive-ored together. Checked
    against packets the printer itself produced, so a rule that is nearly right --
    leaving out the length, say, which would agree on about half of these -- cannot
    pass."""
    raw = bytes_of(RECORDED[name])
    command, length = raw[2], raw[3]
    data, checksum = raw[4 : 4 + length], raw[4 + length]
    worked = command ^ length
    for byte in data:
        worked ^= byte
    assert worked == checksum


@pytest.mark.parametrize("name", sorted(RECORDED))
def test_every_packet_is_wrapped_the_way_the_driver_wraps_one(name):
    raw = bytes_of(RECORDED[name])
    source = DRIVER.read_text(encoding="utf-8")
    assert raw[:2] == [0x55, 0x55]
    assert raw[-2:] == [0xAA, 0xAA]
    assert len(raw) == 2 + 1 + 1 + raw[3] + 1 + 2
    assert "const HEAD = [0x55, 0x55];" in source
    assert "const TAIL = [0xaa, 0xaa];" in source


def test_the_driver_sends_the_commands_it_means_to():
    """The numbers are the protocol's, and a keystroke's difference between 0x83 and
    0x85 is a printer that does nothing and says nothing about why."""
    assert table("TX") == COMMANDS


def test_the_driver_waits_for_the_answers_those_commands_have():
    """Every one of them is the command plus one, except the four that are not --
    which is exactly why they are written down rather than worked out."""
    assert table("RX") == ANSWERS


def test_it_says_which_printers_it_is_for():
    """Other models differ in the print sequence rather than in the framing, so a
    driver that quietly claimed to be general would fail on a D11 in a way nobody
    could read."""
    source = DRIVER.read_text(encoding="utf-8")
    assert "Covers the B1 and the B21" in source
    assert "PRINTHEAD = 384" in source
    # And says why the B18 is not in that list, having once been: same family by
    # name, 96 dots and a sideways page by every number that matters.
    assert "Not the B18" in source


def test_it_says_where_it_came_from():
    """It is a reimplementation of somebody else's reverse engineering, and the
    licence it was read under asks for the notice that honesty would ask for
    anyway."""
    source = DRIVER.read_text(encoding="utf-8")
    assert "niimbluelib" in source
    assert "MIT" in source


def test_the_chooser_looks_for_the_name_as_well_as_the_service():
    """A NIIMBOT serves that service and does not necessarily advertise it -- an
    advertisement has 31 bytes and these printers spend them on their name. Filtered
    on the service alone the chooser comes up empty, with nothing on screen to say
    the printer was ever there, which is exactly what happened the first time this
    met a real one."""
    source = DRIVER.read_text(encoding="utf-8")
    assert "filters: [{ namePrefix: NAME_PREFIX }, { services: [SERVICE] }]" in source
    # And the service has to be asked for as optional, or a device matched by its
    # name connects and shows no services at all.
    assert "optionalServices: [SERVICE]" in source


def test_there_is_a_way_past_a_chooser_that_shows_nothing():
    """Filters behave differently in Bluefy, which is the only browser that reaches
    Bluetooth on iOS, and differently enough that the Web Bluetooth group has an
    open report about it with no answer in it. A chooser listing every radio in the
    room is a poor thing to offer; one listing nothing at all, on the platform we
    cannot debug, is worse -- so the wide chooser exists and is offered."""
    source = DRIVER.read_text(encoding="utf-8")
    assert "acceptAllDevices: true" in source
    # Offered rather than taken automatically: a browser opens its chooser only in
    # answer to a press, so the second go has to be a press too.
    assert "showEverything" in source
    sender = DRIVER.parent / "labelsend.js"
    assert "show every Bluetooth device" in sender.read_text(encoding="utf-8")


def test_picking_the_wrong_thing_from_the_wide_chooser_says_so():
    """In a list of every radio in the room it is entirely possible to pick a pair
    of headphones, and "no suitable characteristic" is not a sentence about that."""
    source = DRIVER.read_text(encoding="utf-8")
    assert "is not a NIIMBOT" in source


def test_a_refused_connection_says_what_to_do_about_it():
    """A BLE printer talks to one thing at a time, and the thing holding it is
    almost always the vendor's own app. "GATT operation failed" is not something
    anybody can act on; "close the NIIMBOT app" is."""
    source = DRIVER.read_text(encoding="utf-8")
    assert "close the NIIMBOT app" in source
