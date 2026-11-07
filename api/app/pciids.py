"""Names for what a later PC's PCI bus says is on it (MANUAL §23; ADR-0043).

A survey reports each PCI function as `vvvv:dddd cccc`: its maker's number, its own
number and its class. The numbers are exact and say nothing to a person, so the
register names the ones it knows, from a short table of what turns up in the machines
it is written for -- the chipsets from Intel's Triton to the 440BX and their rivals,
and the video, sound, network and disk cards of the same years. Anything else is named
by its maker and its number, which is still enough to look up.

The chipset is the board's, so its bridges are never asked about: they name the
chipset and nothing more. Every other function is a card, or something built into
the board, and the class says which kind of part it would be.
"""

VENDORS: dict[str, str] = {
    "1000": "Symbios Logic",
    "1002": "ATI",
    "1011": "DEC",
    "1013": "Cirrus Logic",
    "1022": "AMD",
    "1023": "Trident",
    "1033": "NEC",
    "1039": "SiS",
    "1045": "OPTi",
    "105A": "Promise",
    "105D": "Number Nine",
    "1073": "Yamaha",
    "1095": "CMD",
    "109E": "Brooktree",
    "10B7": "3Com",
    "10B9": "ALi",
    "10DE": "NVIDIA",
    "10EC": "Realtek",
    "1102": "Creative Labs",
    "1106": "VIA",
    "1163": "Rendition",
    "121A": "3dfx",
    "125D": "ESS",
    "1274": "Ensoniq",
    "12D2": "NVIDIA",
    "12EB": "Aureal",
    "4005": "Avance Logic",
    "5333": "S3",
    "8086": "Intel",
    "9004": "Adaptec",
    "9005": "Adaptec",
    "100C": "Tseng Labs",
    "102B": "Matrox",
}

DEVICES: dict[str, str] = {
    # Intel chipsets and the PIIX south bridges beside them
    "8086:04A3": "82434LX/NX Mercury/Neptune",
    "8086:122D": "82437FX 430FX Triton",
    "8086:122E": "82371FB PIIX ISA bridge",
    "8086:1230": "82371FB PIIX IDE",
    "8086:1250": "82439HX 430HX Triton II",
    "8086:7030": "82437VX 430VX Triton II",
    "8086:7000": "82371SB PIIX3 ISA bridge",
    "8086:7010": "82371SB PIIX3 IDE",
    "8086:7020": "82371SB PIIX3 USB",
    "8086:7100": "82439TX 430TX",
    "8086:7110": "82371AB PIIX4 ISA bridge",
    "8086:7111": "82371AB PIIX4 IDE",
    "8086:7112": "82371AB PIIX4 USB",
    "8086:7113": "82371AB PIIX4 ACPI",
    "8086:1237": "82441FX 440FX Natoma",
    "8086:7180": "82443LX 440LX",
    "8086:7190": "82443BX 440BX",
    "8086:7192": "82443BX 440BX",
    "8086:71A0": "82443GX 440GX",
    "8086:1229": "82557 EtherExpress PRO/100",
    "8086:7800": "i740",
    # VIA, SiS, ALi, OPTi, AMD
    "1106:0585": "VT82C585VP Apollo VP",
    "1106:0586": "VT82C586 ISA bridge",
    "1106:0571": "VT82C586 IDE",
    "1106:3038": "VT82C586 USB",
    "1106:0597": "VT82C597 Apollo VP3",
    "1106:0598": "VT82C598 Apollo MVP3",
    "1106:0691": "VT82C691 Apollo Pro",
    "1106:0596": "VT82C596 ISA bridge",
    "1106:0686": "VT82C686 ISA bridge",
    "1106:3058": "VT82C686 AC97 audio",
    "1106:3043": "VT86C100A Rhine",
    "1039:0496": "85C496 486 PCI",
    "1039:0008": "85C503 ISA bridge",
    "1039:5511": "5511",
    "1039:5513": "5513 IDE",
    "1039:5571": "5571",
    "1039:5597": "5597",
    "1039:0530": "530",
    "1039:0200": "5597 VGA",
    "1039:6326": "6326",
    "10B9:1521": "M1521 Aladdin III",
    "10B9:1531": "M1531 Aladdin IV",
    "10B9:1541": "M1541 Aladdin V",
    "10B9:1533": "M1533 ISA bridge",
    "10B9:5229": "M5229 IDE",
    "1045:C557": "82C557 Viper-M",
    "1045:C822": "82C822",
    "1045:C621": "82C621 IDE",
    "1022:2000": "PCnet-PCI",
    "1022:7006": "AMD-751 Irongate",
    # Video
    "1013:00A0": "GD 5430",
    "1013:00A8": "GD 5434",
    "1013:00AC": "GD 5436",
    "1013:00B8": "GD 5446",
    "1013:00BC": "GD 5480",
    "1013:00D0": "GD 5462",
    "1013:00D6": "GD 5465",
    "5333:8811": "Trio32/64/64V+",
    "5333:8812": "Aurora64V+",
    "5333:8901": "Trio64V2",
    "5333:5631": "ViRGE",
    "5333:8A01": "ViRGE/DX",
    "5333:8A10": "ViRGE/GX2",
    "5333:8C01": "ViRGE/MX",
    "5333:88C0": "Vision864",
    "5333:88F0": "Vision968",
    "5333:8A22": "Savage4",
    "1002:4158": "Mach32",
    "1002:4758": "Mach64 GX",
    "1002:4354": "Mach64 CT",
    "1002:4755": "3D Rage II+",
    "1002:4742": "Rage Pro",
    "1002:4C42": "Rage LT Pro",
    "1002:5246": "Rage 128",
    "1002:5144": "Radeon",
    "102B:0518": "MGA-II Atlas",
    "102B:0519": "Millennium",
    "102B:051A": "Mystique",
    "102B:051B": "Millennium II",
    "102B:0520": "G200",
    "102B:0521": "G200",
    "102B:0525": "G400",
    "10DE:0020": "RIVA TNT",
    "10DE:0028": "RIVA TNT2",
    "10DE:0100": "GeForce 256",
    "12D2:0018": "RIVA 128",
    "121A:0001": "Voodoo",
    "121A:0002": "Voodoo2",
    "121A:0003": "Voodoo Banshee",
    "121A:0005": "Voodoo3",
    "100C:3202": "ET4000/W32p",
    "100C:3208": "ET6000",
    "1023:9440": "TGUI 9440",
    "1023:9660": "TGUI 9660",
    "1023:9750": "3DImage 975",
    "105D:2309": "Imagine 128",
    "105D:2339": "Imagine 128 II",
    "1163:0001": "Verite 1000",
    "1163:2000": "Verite 2100",
    # Network
    "10EC:8029": "RTL-8029(AS)",
    "10EC:8129": "RTL-8129",
    "10EC:8139": "RTL-8139",
    "10B7:5900": "3c590",
    "10B7:5950": "3c595",
    "10B7:9000": "3c900",
    "10B7:9050": "3c905",
    "10B7:9200": "3c905C",
    "1011:0002": "21040 Tulip",
    "1011:0009": "21140 Tulip",
    "1011:0019": "21143 Tulip",
    # Sound
    "1274:5000": "ES1370 AudioPCI",
    "1274:1371": "ES1371 AudioPCI",
    "1102:0002": "SB Live!",
    "1102:0004": "SB Audigy",
    "125D:1968": "ES1968 Maestro-2",
    "125D:1978": "ES1978 Maestro-2E",
    "125D:1969": "ES1969 Solo-1",
    "1073:000D": "YMF724",
    "1073:0012": "YMF754",
    "4005:4000": "ALS4000",
    "12EB:0001": "Vortex AU8820",
    "12EB:0002": "Vortex2 AU8830",
    # Disk controllers, capture
    "9004:7178": "AHA-2940",
    "9004:8178": "AHA-2940U",
    "9005:001F": "AHA-2940U2",
    "1000:0001": "53c810",
    "1000:000F": "53c875",
    "1095:0640": "PCI0640 IDE",
    "1095:0646": "PCI0646 IDE",
    "105A:4D33": "Ultra33",
    "105A:4D38": "Ultra66",
    "109E:0350": "Bt848",
    "109E:036E": "Bt878",
}

# The chipset a host bridge belongs to, as the board's Chipset line names it.
CHIPSETS: dict[str, str] = {
    "8086:04A3": "Intel 430LX",
    "8086:122D": "Intel 430FX",
    "8086:1250": "Intel 430HX",
    "8086:7030": "Intel 430VX",
    "8086:7100": "Intel 430TX",
    "8086:1237": "Intel 440FX",
    "8086:7180": "Intel 440LX",
    "8086:7190": "Intel 440BX",
    "8086:7192": "Intel 440BX",
    "8086:71A0": "Intel 440GX",
    "1106:0585": "VIA Apollo VP",
    "1106:0597": "VIA Apollo VP3",
    "1106:0598": "VIA Apollo MVP3",
    "1106:0691": "VIA Apollo Pro",
    "1039:0496": "SiS 496",
    "1039:5511": "SiS 5511",
    "1039:5571": "SiS 5571",
    "1039:5597": "SiS 5597",
    "1039:0530": "SiS 530",
    "10B9:1521": "ALi Aladdin III",
    "10B9:1531": "ALi Aladdin IV",
    "10B9:1541": "ALi Aladdin V",
    "1045:C557": "OPTi Viper-M",
    "1045:C822": "OPTi 822",
    "1022:7006": "AMD 751",
}

# What kind of part a card of each class is, and what it is called when it is built
# into the board. The class and subclass first, then the class alone.
_KINDS: dict[str, tuple[str, str]] = {
    "0300": ("video", "video"),
    "0380": ("video", "video"),
    "03": ("video", "video"),
    "0200": ("network", "network"),
    "02": ("network", "network"),
    "0401": ("sound", "sound"),
    "0403": ("sound", "sound"),
    "04": ("io", "video capture"),
    "0100": ("io", "SCSI"),
    "0101": ("io", "disk controller"),
    "01": ("io", "disk controller"),
    "0C03": ("io", "USB"),
    "0C": ("io", "serial bus"),
    "07": ("io", "communications"),
}


def split(value: str) -> tuple[str, str, str]:
    """`vvvv:dddd cccc` as (vendor, device, class), in capitals; blanks for a value
    that is not in that shape."""
    head, _, cls = value.strip().upper().partition(" ")
    vendor, _, device = head.partition(":")
    return vendor, device, cls.strip()


def name(vendor: str, device: str) -> str:
    """What a device is called: its maker and its own name where the table knows
    them, and its numbers where it does not."""
    maker = VENDORS.get(vendor, "")
    own = DEVICES.get(f"{vendor}:{device}", "")
    if maker and own:
        return f"{maker} {own}"
    if maker:
        return f"{maker} {device}"
    return f"PCI {vendor}:{device}"


def known(vendor: str, device: str) -> bool:
    """Whether the table can say both who made a device and what it is."""
    return vendor in VENDORS and f"{vendor}:{device}" in DEVICES


def maker(vendor: str) -> str:
    return VENDORS.get(vendor, "")


def model(vendor: str, device: str) -> str:
    return DEVICES.get(f"{vendor}:{device}", "") or device


def is_chipset(cls: str) -> bool:
    """A bridge: the chipset's own, and so part of the board."""
    return cls.startswith("06")


def chipset(vendor: str, device: str) -> str:
    return CHIPSETS.get(f"{vendor}:{device}", "")


def kind(cls: str) -> tuple[str, str]:
    """(the part type, what it is called built in) for a card of class `cls`."""
    return _KINDS.get(cls[:4]) or _KINDS.get(cls[:2]) or ("io", "card")
