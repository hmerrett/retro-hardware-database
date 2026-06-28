#!/usr/bin/env python3
"""Generate simple line-art SVG placeholder icons (one per part type) into
assets/placeholders/. Theme-neutral grey so they read on light and dark.
Re-run after editing to regenerate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "placeholders"

HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" '
        'stroke="#8a93a0" stroke-width="3" stroke-linecap="round" '
        'stroke-linejoin="round">')

ICONS = {
    "chip": '<rect x="20" y="20" width="24" height="24" rx="2"/>'
            '<rect x="27" y="27" width="10" height="10" rx="1"/>'
            '<path d="M26 20V14M32 20V14M38 20V14M26 44v6M32 44v6M38 44v6'
            'M20 26h-6M20 32h-6M20 38h-6M44 26h6M44 32h6M44 38h6"/>',
    "ram": '<rect x="8" y="23" width="48" height="18" rx="1"/>'
           '<rect x="13" y="28" width="6" height="8"/><rect x="22" y="28" width="6" height="8"/>'
           '<rect x="31" y="28" width="6" height="8"/><rect x="40" y="28" width="6" height="8"/>'
           '<path d="M28 41v3h8v-3"/>',
    "card": '<rect x="9" y="18" width="38" height="22" rx="1"/>'
            '<rect x="16" y="24" width="11" height="10" rx="1"/>'
            '<path d="M47 13v34"/>'
            '<path d="M13 40v4M19 40v4M25 40v4M31 40v4M37 40v4"/>',
    "drive": '<rect x="12" y="16" width="40" height="32" rx="3"/>'
             '<circle cx="30" cy="32" r="10"/><circle cx="30" cy="32" r="2"/>'
             '<path d="M37 25l7-5"/>',
    "disc": '<circle cx="32" cy="32" r="21"/><circle cx="32" cy="32" r="5"/>',
    "floppy": '<path d="M14 13h28l8 8v30H14z"/>'
              '<rect x="22" y="13" width="17" height="12"/>'
              '<rect x="20" y="33" width="24" height="18" rx="1"/>',
    "psu": '<rect x="11" y="19" width="42" height="27" rx="2"/>'
           '<circle cx="26" cy="32" r="9"/><path d="M26 23v18M17 32h18"/>'
           '<rect x="43" y="25" width="7" height="6"/>',
    "fan": '<circle cx="32" cy="32" r="20"/><circle cx="32" cy="32" r="4"/>'
           '<path d="M32 12v8M32 44v8M12 32h8M44 32h8M18 18l6 6M40 40l6 6M46 18l-6 6M24 40l-6 6"/>',
    "keyboard": '<rect x="7" y="22" width="50" height="22" rx="3"/>'
                '<path d="M14 29h0M22 29h0M30 29h0M38 29h0M46 29h0"/>'
                '<path d="M18 37h22"/>',
    "board": '<rect x="9" y="9" width="46" height="46" rx="2"/>'
             '<rect x="14" y="14" width="14" height="14" rx="1"/>'
             '<rect x="44" y="14" width="7" height="22"/>'
             '<path d="M14 40h24M14 46h24"/>',
    "computer": '<rect x="22" y="10" width="22" height="44" rx="2"/>'
                '<circle cx="33" cy="18" r="2"/>'
                '<rect x="27" y="24" width="12" height="5" rx="1"/>'
                '<path d="M28 40h10M28 46h10"/>',
    "box": '<rect x="14" y="18" width="36" height="30" rx="2"/>'
           '<circle cx="26" cy="33" r="1.6"/><circle cx="32" cy="33" r="1.6"/>'
           '<circle cx="38" cy="33" r="1.6"/>',
}

OUT.mkdir(parents=True, exist_ok=True)
for name, body in ICONS.items():
    (OUT / f"{name}.svg").write_text(HEAD + body + "</svg>\n", encoding="utf-8")
print(f"wrote {len(ICONS)} placeholder icons -> {OUT}")
