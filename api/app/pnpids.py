"""Who a Plug and Play ID says made something (ADR-0051).

A Plug and Play ISA card and a monitor's EDID both name their maker by the same
three-letter code, once EISA's and then Microsoft's to hand out: `CTL` is Creative
Labs, `DEL` Dell. The register needs only the makers of the cards and monitors a
collection like this one has, so this is a table of those and not the whole
registry; a code it does not know names nobody, and the thing is named by its own
words or asked about at the machine.
"""

import re

MAKERS = {
    # Plug and Play ISA cards: sound, network, modems, disk controllers.
    "ADP": "Adaptec",
    "ADS": "Analog Devices",
    "ALS": "Avance Logic",
    "AVM": "AVM",
    "AZT": "Aztech",
    "BRI": "Boca Research",
    "CMI": "C-Media",
    "CSC": "Crystal Semiconductor",
    "CTL": "Creative Labs",
    "DMB": "Diamond Multimedia",
    "ELS": "ELSA",
    "ENS": "Ensoniq",
    "ESS": "ESS Technology",
    "GRV": "Advanced Gravis",
    "HAY": "Hayes",
    "MOT": "Motorola",
    "OPT": "OPTi",
    "ROK": "Rockwell",
    "RTL": "Realtek",
    "SMC": "SMC",
    "SUP": "Supra",
    "TCM": "3Com",
    "TER": "Terratec",
    "USR": "U.S. Robotics",
    "YMH": "Yamaha",
    "ZTI": "Zoom Telephonics",
    # Monitors, and the panels in later laptops.
    "ACR": "Acer",
    "ADI": "ADI",
    "AOC": "AOC",
    "APP": "Apple",
    "AUO": "AU Optronics",
    "BNQ": "BenQ",
    "CMO": "Chi Mei",
    "CTX": "CTX",
    "DEL": "Dell",
    "DWE": "Daewoo",
    "ENC": "Eizo",
    "FUS": "Fujitsu Siemens",
    "GSM": "LG",
    "GWY": "Gateway",
    "HEI": "Hyundai",
    "HIT": "Hitachi",
    "HWP": "HP",
    "IVM": "Iiyama",
    "KFC": "KFC",
    "LEN": "Lenovo",
    "LGD": "LG Display",
    "LPL": "LG Philips",
    "MAG": "MAG Innovision",
    "MAX": "Belinea",
    "MEI": "Panasonic",
    "MEL": "Mitsubishi",
    "NAN": "Nanao",
    "NOK": "Nokia",
    "OQI": "Optiquest",
    "PHL": "Philips",
    "RHT": "Red Hat",
    "SAM": "Samsung",
    "SEC": "Seiko Epson",
    "SHP": "Sharp",
    "SNY": "Sony",
    "TAT": "Tatung",
    "TSB": "Toshiba",
    "VSC": "ViewSonic",
    # Both.
    "CPQ": "Compaq",
    "IBM": "IBM",
    "NEC": "NEC",
    "TOS": "Toshiba",
}


def maker(code: str) -> str:
    """The maker a three-letter code names, or "" for one this table does not know."""
    return MAKERS.get((code or "").strip().upper()[:3], "")


def model(own_name: str, made_by: str) -> str:
    """What a thing calls itself, without the maker's name it starts with: `Creative
    SB AWE64 PnP` from Creative Labs is `SB AWE64 PnP`, and `DELL P1110` is `P1110`.
    A name that does not start with the maker's is kept whole."""
    words = " ".join((own_name or "").split())
    if not made_by:
        return words
    for start in (made_by, made_by.split()[0]):
        pattern = re.compile(rf"^{re.escape(start)}\b[\s,.-]*", re.IGNORECASE)
        rest = pattern.sub("", words, count=1)
        if rest != words and rest:
            return rest
    return words
