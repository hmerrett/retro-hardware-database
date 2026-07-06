# Data model

Two tables, one relationship.

```
computers.csv  (1) ───────< (many)  parts.csv
   asset_id  ◄──────────────  computer_id
```

- **computers.csv** — the machines (assemblies). One row per computer.
- **parts.csv** — every individual hardware item: CPUs, motherboards, cards,
  RAM, storage, drives, and peripherals. One row per part.
- A part's **`computer_id`** is a foreign key pointing at a computer's
  `asset_id`. It means "installed in, or paired with, that machine". Leave it
  **blank** for a standalone/uninstalled part (a spare in a box, a peripheral
  not tied to one machine).

The foreign key lives on the part (the "many" side) — standard one-to-many.
A computer's full build is simply "every part whose `computer_id` is this
computer".

## Asset numbers

One shared register across **both** tables, e.g. `RH-0001`. Every physical
object — whole computer or individual part — gets exactly one unique tag, so a
label/QR is unambiguous. `scripts/` will refuse to build if an id is duplicated
across the two files. (Prefix/width set in `config.yml`.)

## computers.csv columns

| column | meaning |
|---|---|
| `asset_id` | unique tag, e.g. `RH-0001` |
| `name` | display name (overrides manufacturer+model) |
| `manufacturer`, `model` | identity (`Custom build` is fine for clones) |
| `year` | year built / released |
| `chassis` | the physical **case**: desktop, tower, mini-tower, breadbin, brand/model |

Form factor isn't stored on the computer — it's a motherboard property, shown on
the computer's page from its linked `motherboard` part. `add.py` prompts you to
link or create that board when you add a computer.
| `os` | installed operating system(s) |
| `cpu` | processor(s) fitted, e.g. `Intel 486DX2-66` or `2× Pentium III 500` — an attribute, not a separate part |
| `installed_ram` | RAM fitted, e.g. `8× 1MB 30-pin (8 MB)` — quick entry `8x1MB 30-pin` computes the total. No separate RAM objects. |
| `condition`, `source` | your tracking (e.g. `Working`; where/how you acquired it) |
| `acquired_date` | optional record-keeping (YYYY-MM-DD) |
| `image` | photo path under `images/` (auto-filled) |
| `url` | reference link (Wikipedia, The Retro Web, or another site) |
| `summary` | short description (auto-filled from Wikipedia) |
| `notes` | anything else |
| `disposed` | non-empty = disposed of; hidden from the index by default. The value doubles as your note/date. |

## parts.csv columns

| column | meaning |
|---|---|
| `asset_id` | unique tag, e.g. `RH-0003` |
| `computer_id` | the computer this part is installed in / paired with — or blank |
| `type` | see vocabulary below; drives grouping, filtering and labels |
| `manufacturer`, `model`, `name` | identity |
| `year` | year of manufacture |
| `specs` | `Label: value | Label: value` — the type-specific detail (see below) |
| `condition`, `source` | your tracking; where/how acquired |
| `acquired_date` | optional (YYYY-MM-DD) |
| `disk_image` | storage only: filename of the disk image you took when it arrived |
| `image` | photo path under `images/` (auto-filled) |
| `url` | reference link (Wikipedia, The Retro Web, or another site) |
| `summary` | short description (auto-filled) |
| `notes` | anything else |
| `disposed` | non-empty = disposed of; hidden from the index by default. The value doubles as your note/date. |

`manufacturer` and `model` are auto-tidied on entry: an all-caps word of 5+
letters is de-shouted to sentence case (`MODEL` → `Model`), while tokens up to
4 letters (`TYPE`, `IFSP`, `SCSI`), protected acronyms and part numbers
(`CL-PCIVT6421E`, `3C905B-TXNM`) are left untouched.

### `type` vocabulary

`motherboard`, `cpu`, `ram`, `video`, `sound`, `network`, `io`, `storage`,
`psu`, `cooler`, `peripheral`, `other`.

(Free text is allowed, but sticking to these keeps grouping and filtering tidy.
Add new ones to `TYPE_ORDER` in `scripts/common.py` to control their order.)

`storage` is the umbrella for all drives/media (its `Kind` says which). CPU and
RAM live on the computer (`cpu`, `installed_ram`), not as parts. To build out a
machine, `python scripts/add.py build RH-0001` walks storage, cards and PSU —
creating as many real parts as needed (nothing generic).

### Recommended `specs` keys per type

The `specs` field is deliberately flexible (one column, any keys) so parts of
different kinds can live in one table. These are conventions, not rules —
`build_site.py` prints a gentle warning for a key outside these lists, a
duplicated key, or a URL left in a value, so typos and crossed data get caught
(`peripheral`/`other` accept any keys):

- **motherboard** — `Chipset`, `CPU family` (e.g. 486-class, Pentium-class), `Form factor` (the computer's form factor is taken from here), `RAM slots`, `Slots` (count each type in turn, or quick entry `8I:2 16I:6 VLB:1` → `2× 8-bit ISA, 6× 16-bit ISA, VLB`; types: 8-bit ISA, 16-bit ISA, EISA, MCA, VLB, PCI, AGP, PCIe x16), `Cache`, `BIOS`, `Onboard video` (e.g. VGA, or VGA C&T 65545), `Ports` (onboard I/O — same letter quick-entry as io cards: IDE/Floppy/Serial/Parallel/PS-2 keyboard/PS-2 mouse/USB…)
- **cpu** — `Socket`, `Speed`, `FSB`, `Cores`, `L1/L2 cache`
- **ram** — `Type` (e.g. 72-pin FPM, EDO, SDRAM), `Size`, `Speed`
- **video** — `Interface` (ISA/VLB/PCI/AGP/PCIe x16), `Chip` (main chip), `Connector` (VGA/DVI/MDA/CGA/EGA/HDMI…), `Memory`, `Type`
- **sound** — `Interface` (bus), `Chip` (main chip), `FM`, `Ports`
- **network** — `Interface` (ISA/PCI bus), `Chip` (main chip), `Connector` (10BASE-T/BNC/AUI)
- **io** — `Interface` (bus), `Chip` (main chip), `Ports` (quick entry: letters I=IDE C=SCSI A=SATA M=MFM R=RLL F=Floppy S=Serial P=Parallel G=Game K=PS/2 keyboard O=PS/2 mouse D=DIN keyboard U=USB, e.g. `IFSSP` → `IDE, Floppy, 2× Serial, Parallel`)
- **storage** — the umbrella for every drive/medium (one part per device): `Kind` (Hard disk / SD-CF card / Tape / Optical / Floppy-Gotek), `Interface` (IDE/SCSI/SATA/USB/34-pin floppy/CF/SD…), `Protocol` (ATA/ATAPI/XTA/RLL/MFM/ESDI), `Capacity`, `CHS` (cylinders/heads/sectors), `Media` (disc/floppy format), `Speed`, `Role`
- **peripheral** — `Interface` (USB, parallel, serial, PS/2, …), plus
  type-appropriate keys (e.g. monitor `Size`, `Tube`; printer `Type`, `Resolution`)

## Generic component presets

`data/presets.csv` is a small library of reusable generic parts (Generic VGA,
floppy drive, RAM, PSU, keyboard …). Attach them to a computer with the helper
instead of retyping:

    python scripts/add.py preset --computer RH-0001 floppy35 vga ram   # or: standard

They're added as ordinary `parts.csv` rows (each with its own asset id) but are
**never** sent to Wikipedia — generic items match junk. Add an amount with
`key:value` — `ram:16MB`, `hdd:540MB`, `vga:1MB` fill Size/Capacity/Memory
(memory is normalised to KB, so 16MB is stored as 16384 KB).
Columns: `key, type, manufacturer, name, specs`.

## Photos

Each item shows one photo by default: `images/<computers|parts>/<asset_id>.jpg`
(auto-filled by enrichment, or just drop a file in). For **multiple photos**, add
more files with a numeric suffix:

    images/parts/RH-0088.jpg      (primary — also shown on the index)
    images/parts/RH-0088-2.jpg
    images/parts/RH-0088-3.jpg

The item page then shows the primary plus a thumbnail strip; click any photo to
open the full-size viewer and use the on-screen arrows or arrow keys to move
between them. Any image format works — `publish.sh` optimises and converts each
to JPEG.

## Disposed items

Flag anything you've sold, scrapped or given away as **disposed** and it drops
out of the index by default. Its page still exists, and the "Show disposed"
box on the index brings it back (dimmed). The `disposed` value is free text — a
date or a short note — and appears as a banner on the item's page.

    # flag it (a blank note defaults to today's date)
    python scripts/add.py dispose RH-0060 "sold on eBay"
    # clear the flag again
    python scripts/add.py restore RH-0060

## Reference sources

- **Wikipedia / Wikimedia** — free, used for summaries and photos for common
  items. See `scripts/enrich.py`.
- **The Retro Web** (`theretroweb.com`) — community database, great for PC-clone
  parts (motherboards, CPUs, cards). There is **no public API** and the site is
  behind Cloudflare, so reliable automated spec-pulling isn't guaranteed and we
  never bypass their bot protection. The workflow is:
  1. Paste the part's page URL into `url`.
  2. Optionally run `python scripts/enrich.py --only RH-0003 --browser`
     — a single, identifying, rate-limited request (headless Chrome) that tries
     to read the spec table and image. If Cloudflare blocks it, it logs that and
     keeps just the link; fill the specs by hand in that case.
  Their robots policy allows general access but disallows AI-training crawlers
  (`ai-train=no`); this personal, link-targeted use respects that. For bulk or
  sanctioned data access, contact the project (GitHub: `TheRetroWeb`, or their
  Discord).
