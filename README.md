# Retro Hardware Database

A GitHub-friendly catalogue of retro computers and their parts — built as a
small **relational** database in plain CSV, published as a static website on
**GitHub Pages**, with printable **6×4 labels** carrying a QR code that opens
each item's page.

## The model in one picture

```
computers.csv (1) ────< (many) parts.csv
    asset_id    <───────  computer_id
```

- **computers.csv** — the machines (assemblies).
- **parts.csv** — every individual item: CPUs, motherboards, cards, RAM,
  storage, drives, peripherals. Each part's `computer_id` says which machine
  it's installed in (blank = standalone).
- One shared asset-number register across both tables, so every physical
  object has a single unique tag (`RH-0001`, `RH-0002`, …).

A computer's web page shows its full build (parts grouped by type); each part
links back to the machine it lives in. Full field reference: **`docs/schema.md`**.

## What's in the box

```
data/computers.csv      your machines
data/parts.csv          your parts (FK: computer_id -> computers.asset_id)
images/computers, images/parts   photos (auto-filled by enrichment)
scripts/enrich.py       fill summaries/photos (Wikipedia) + specs (The Retro Web, best effort)
scripts/build_site.py   CSVs -> ./site/ (one page per computer and per part)
scripts/make_labels.py  CSVs -> labels/labels.pdf (6x4 + QR)
templates/              site look (edit base.html for styling)
docs/schema.md          the data model + recommended fields per part type
.github/workflows/      auto-build + deploy to GitHub Pages on push
```

## One-time setup

1. Install Python 3.10+ and the dependencies — ideally in a virtual
   environment (kept out of git by `.gitignore`):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # run this in each new terminal
   pip install -r requirements.txt
   ```

   (No venv? Use `pip install -r requirements.txt`, adding
   `--break-system-packages` if pip reports an "externally-managed environment".)
2. Create a GitHub repo (public is fine), push this folder.
3. Repo **Settings → Pages → Source = GitHub Actions**.
4. In `config.yml`, set `base_url` to your Pages URL
   (`https://you.github.io/retro-hardware-database`) — the QR codes encode it,
   so set it before printing. Update the `user_agent` strings with your repo URL too.

## Adding things

Easiest: the **guided helper**. It assigns the next `RH-####` across both
tables, writes valid CSV, and links parts to computers for you:

```bash
python scripts/add.py                  # interactive prompts
python scripts/add.py computer --name "Amiga 1200" --year 1992
python scripts/add.py part --type cpu --computer RH-0002 \
    --model "i486 DX2-66" --specs "Socket: 3 | Speed: 66 MHz"
```

Add the computer first to get its asset number, then add each part with
`--computer <that id>` (omit it for a standalone spare). It can run enrichment
straight after and prints the build/label/push commands.

**Generic/common parts** (PSU, RAM, floppy, video — the things every PC has)
come from presets, so you don't retype them and they're never sent to Wikipedia:

```bash
python scripts/add.py preset --list
python scripts/add.py preset --computer RH-0001 floppy35 vga ram hdd
python scripts/add.py preset --computer RH-0001 standard   # a typical PC set
```

Interactive `add.py` also offers to attach a standard generic set right after
you create a computer. Edit `data/presets.csv` to change or add presets.

Prefer to edit by hand? You can still edit the CSVs directly:

**A computer:** add a row to `data/computers.csv` (asset_id, name, form factor,
OS, …).

**Its parts:** add rows to `data/parts.csv`, each with `computer_id` set to that
computer's asset_id. "One or more CPUs / cards / storage" is just several rows.
Leave `computer_id` blank for a spare that isn't installed. Set `type` to one of:
`motherboard, cpu, ram, gpu, sound, network, io, storage, optical, floppy, psu,
cooler, peripheral, other`. Put type-specific detail in `specs` as
`Key: value | Key: value` (see `docs/schema.md` for recommended keys).

Then:

```bash
python scripts/enrich.py            # summaries + photos from Wikipedia (free)
python scripts/build_site.py        # rebuild ./site
open site/index.html                # preview
```

Commit and push — GitHub Actions rebuilds and publishes within a minute or two.

## Photos & specs from references

**Wikipedia/Wikimedia** (free, no key) fills `summary`, `wikipedia_url` and a
photo for common items. Only blank fields are touched unless you pass `--force`.

**The Retro Web** (`theretroweb.com`) is the best source for PC-clone parts, but
it has **no public API** and sits behind Cloudflare, so automated spec-pulling
isn't guaranteed (and this project never bypasses bot protection). Workflow:

1. Paste the part's page URL into its `theretroweb_url` cell.
2. Optionally: `python scripts/enrich.py --source theretroweb --only RH-0003`
   — one polite, identifying request that reads the spec table + image if the
   page comes back. If Cloudflare blocks it you'll see "blocked/empty — keeping
   link only"; fill the specs by hand in that case (add `--dump-html` to inspect
   what came back). The reference link is always kept regardless.

Their robots policy allows general access but disallows AI-training crawlers;
this personal, link-targeted use respects that. For bulk/sanctioned data,
contact the project (GitHub `TheRetroWeb`, or their Discord).

## Printing labels

```bash
python scripts/make_labels.py                  # every item -> labels/labels.pdf
python scripts/make_labels.py RH-0002 RH-0003  # just these
```

A computer's label summarises its build (CPU, RAM, video, sound, storage…)
pulled from its parts; a part's label shows its own specs. Print at 100% /
"actual size". Size/units are set in `config.yml` (`label:`).

## Licensing

Code is MIT (`LICENSE`). Your catalogue data and photos are yours; third-party
images/specs (Wikipedia, The Retro Web) keep their own licences — check and
attribute before redistributing.
