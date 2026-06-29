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
| `form_factor` | the board/spec **standard**: AT / Baby-AT / ATX / proprietary / all-in-one … (physical orientation like desktop/tower belongs in `chassis`) |
| `chassis` | the physical **case**: desktop, tower, mini-tower, breadbin, brand/model |
| `os` | installed operating system(s) |
| `condition`, `source` | your tracking (e.g. `Working`; where/how you acquired it) |
| `acquired_date` | optional record-keeping (YYYY-MM-DD) |
| `image` | photo path under `images/` (auto-filled) |
| `theretroweb_url`, `wikipedia_url` | reference links |
| `summary` | short description (auto-filled from Wikipedia) |
| `notes` | anything else |

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
| `theretroweb_url`, `wikipedia_url` | reference links |
| `summary` | short description (auto-filled) |
| `notes` | anything else |

### `type` vocabulary

`motherboard`, `cpu`, `ram`, `gpu`, `sound`, `network`, `io`, `storage`,
`optical`, `floppy`, `psu`, `cooler`, `peripheral`, `other`.

(Free text is allowed, but sticking to these keeps grouping and filtering tidy.
Add new ones to `TYPE_ORDER` in `scripts/common.py` to control their order.)

### Recommended `specs` keys per type

The `specs` field is deliberately flexible (one column, any keys) so parts of
different kinds can live in one table. These are conventions, not rules:

- **motherboard** — `Chipset`, `Socket`, `Slots`, `RAM`, `Form factor`
- **cpu** — `Socket`, `Speed`, `FSB`, `Cores`, `L1/L2 cache`
- **ram** — `Type` (e.g. 72-pin FPM, EDO, SDRAM), `Size`, `Speed`
- **gpu** — `Interface` (ISA/VLB/PCI/AGP), `Memory`, `Chipset`, `Type`
- **sound** — `Interface` (bus), `Chipset`, `FM`, `Ports`
- **network** — `Interface` (ISA/PCI bus), `Connector` (10BASE-T/BNC/AUI), `Chipset`
- **io** — `Interface` (bus), `Ports` (quick entry: letters I=IDE C=SCSI A=SATA M=MFM F=Floppy S=Serial P=Parallel G=Game, e.g. `IFSSP` → `IDE, Floppy, 2× Serial, Parallel`)
- **storage** — `Interface` (IDE/SCSI/MFM/CF/SD), `Protocol` (ATA/ATAPI/XTA/RLL/MFM/ESDI), `Capacity`, `CHS` (cylinders/heads/sectors), `Role`
- **optical / floppy** — `Media`, `Interface`, `Speed`
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

## Reference sources

- **Wikipedia / Wikimedia** — free, used for summaries and photos for common
  items. See `scripts/enrich.py`.
- **The Retro Web** (`theretroweb.com`) — community database, great for PC-clone
  parts (motherboards, CPUs, cards). There is **no public API** and the site is
  behind Cloudflare, so reliable automated spec-pulling isn't guaranteed and we
  never bypass their bot protection. The workflow is:
  1. Paste the part's page URL into `theretroweb_url`.
  2. Optionally run `python scripts/enrich.py --source theretroweb --only RH-0003`
     — a single, identifying, rate-limited request that tries to read the spec
     table and image. If Cloudflare blocks it, it logs that and keeps just the
     link; fill the specs by hand in that case.
  Their robots policy allows general access but disallows AI-training crawlers
  (`ai-train=no`); this personal, link-targeted use respects that. For bulk or
  sanctioned data access, contact the project (GitHub: `TheRetroWeb`, or their
  Discord).
