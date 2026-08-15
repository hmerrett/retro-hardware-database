# Retro Hardware Database

A catalogue of retro PCs and the parts they are built from, and of the home
computers and consoles that are not built from parts but come in documented
variations of their own. It runs under Docker Compose and has five services:

```
docker compose
├── caddy  reverse proxy, auto HTTPS   (:80 and :443, https://db.2600.me)
│          proxies to api, Let's Encrypt certificate
├── db     MariaDB 11                   (volume: dbdata)
├── api    FastAPI + uvicorn            (127.0.0.1:8000, public via caddy)
│          /            web GUI (public read-only, login to edit)
│          /api/...     JSON REST API (login required)
│          /images/...  uploaded photos (volume: images)
│          /docs        OpenAPI docs (login required)
├── mcp    MCP server                   (127.0.0.1:8001/mcp)
│          list/get/create/update/delete tools over the REST API
└── goaccess  traffic report from caddy's access log, rebuilt every minute
           (volume: goaccess_report, served by the api at /traffic)
```

Anyone can browse the gallery and item pages at https://db.2600.me without
logging in. Editing, photo upload, the JSON API and the docs need an HTTP Basic
login. Only Caddy is exposed to the internet, on ports 80 and 443; the API and
MCP server listen on localhost and are reached through the proxy or on the host.

## What the GUI does

Beyond browsing and editing: photo upload with rotate/crop and a chosen default
image; a per-photo "reference image" marker for a picture of the same model
rather than this exact unit, badged with the source site's favicon; a dated
history for every asset (automatic change records plus free-text notes, with a run
of the same thing done in one sitting -- ten photographs deleted one after another
-- read out as one line);
the files kept beside the register (a driver disk, a manual, a ROM dump), shown on
every item tagged with a name they are for and sitting above the history, since
they are part of what the item is where the history is a log to be consulted;
printable label PDFs; duplicating an item; marking one disposed and restoring it;
deleting a disposed record for good; and a build walk that steps through a
machine's motherboard and cards.

The search bar sits in the banner, so a search starts from whatever page you are
on. Enter hands the query to the server, which reads every field of every item
and its history; on the gallery the same box also filters the cards as you type.
Typing two characters also drops down the first ten matches — the arrow keys and
Enter walk them, and the last line says how many more there are. It is the same
search Enter runs, so the list previews that answer rather than a narrower one,
ordered so that what you typed being an asset tag, or the start of a name, comes
before a hit buried in a spec or a history note.
Beside it, on a device with a camera, is a scan button that reads the QR code on
a printed label and opens that item — labels printed against the old GitHub
Pages URL included, since only the asset tag is taken from the code.

Clicking a photo opens it as large as the window allows, and from there it zooms by
the usual gestures -- double-click or double-tap, the wheel or a trackpad or
two-finger pinch, `+`/`-`/`0` -- with a drag to move about the enlarged photo and the
arrow keys, a swipe or `Esc` for the rest. Zooming is the big view's own, so the
gallery and item pages pinch-zoom as any page does.

Disposing a machine disposes what is in it -- the parts installed in it and
anything mounted on those in turn -- on the same date and for the same reason.
A part already disposed keeps its own record, and restoring the machine brings
back only the parts that went out with it.

Disposal is how something leaves the collection while keeping its record. For
when the record itself should not exist -- a duplicate, a mistake, a thing
scrapped that was never worth a line -- a disposed item can be deleted outright
from the banner on its page. Only a disposed one: the reversible step is a
precondition of the irreversible one, so nothing goes that has not already been
marked as gone once, deliberately, on an earlier day. The confirmation lists what
will go (photos are deleted from disk, history with them) and asks for the item's
own URL to be pasted in, which makes a delete a deliberate act rather than a
stray click. Whatever pointed at it is unlinked first and keeps a line in its own
history saying why it is suddenly standing alone; a machine's disposed parts can
be deleted along with it by ticking a box, while any part still in the collection
is kept whatever the box says.

Photos upload as soon as they are chosen -- picking them is the whole gesture.

The camera that takes the picture belongs to a phone, and the register is edited at
a desk, so every item page ends in a QR code of its own URL. Scan it and the phone
is on that item, where choosing a photo shoots it or picks it from the camera roll.
It is shown only when logged in -- a visitor has nothing to upload with -- and a
phone that arrives not logged in is put back on the item after logging in rather
than handed the gallery.

An item page has prev/next buttons, and a swipe does the same on a phone. They
walk the list the gallery was last showing -- that sort, that search, that
category -- which the browser hands over in `sessionStorage`; arrive from a
printed label instead and they walk the register in asset order.

Our own photos are watermarked with the site logo as they are served (reference
images are not). Set `RHDB_WATERMARK=0` to serve everything untouched.

`/stats` is the collection by numbers, and public: totals, a handful of ranked
charts, and "the pointless department" -- a pool of figures nobody needs (most and
least reliable maker, the longest wait between a thing being made and arriving
here, what every floppy would hold if each had a disk in it) from which the page
draws six at random on each visit, so a figure too silly to earn permanent space
still gets seen. A figure only joins the pool when it has something to say, so a
young register offers fewer rather than offering blanks, and every one links to
the items behind it like the rest of the page.

Reliability there means one thing: the share of a maker's parts recorded as
Working. Not "Restored" -- a part that had to be restored is evidence of the
opposite -- and only parts still in the register, since a disposed one may have
been sold in perfect order. Makers need five parts to qualify, "Unknown" and
"Generic" are not makers, and the caption on the page says so, because a league
table whose entry conditions are hidden is an opinion with a bar chart.

`/traffic` (login required) shows the GoAccess traffic report.

A machine the catalogue names — a Spectrum, a C64, a CPC, a Mega Drive — is filed
against it from a menu at the top of the machine form, and its documented
variations appear underneath: the board issue, the case or keyboard style, the
region, and a box per chip socket with the part numbers that turn up in it.
Picking a model also fills the manufacturer, model, year, CPU, chassis and OS into
whichever of those boxes are still empty, and offers the memory sizes that model
was sold with on the memory box. See [Data model](#data-model) for what is stored
and why the boxes are boxes rather than menus.

## Data model

Two tables share a single asset register (RH-0001, RH-0002, and so on).
`computers` holds each machine and `parts` holds each component. A part's
`computer_id` is a foreign key to the computer it is installed in, and
`parent_id` to the part it is mounted on; both are NULL for a standalone spare,
and deleting a machine or a host card unlinks what pointed at it. A computer
carries its CPU, installed RAM and floppy/optical/CF-SD drives as attributes of
the machine; mechanical hard disks, tape and expansion cards are parts.

A machine's parts are listed with what each one is made of on a line of its own
underneath, as labelled pairs in columns, rather than in a `Specs` column beside
the name. A card's specs are longer than the rest of its row put together, so as a
column they took most of the table's width, squeezed the asset id and the name into
a few characters each, and still wrapped -- which made every row that tall whether
it had specs in it or not. A part with nothing recorded gets no second line, so the
list also shows at a glance which parts have been written up. One template
(`_partlist.html`) draws both the parts fitted in a machine and the parts mounted on
a card, since they are the same list and differ only in what taking one out is
called.

`computers.topbench` is the one measured number in a record that otherwise says
only what a machine was built as: what it scores in TopBench, the DOS benchmark
that puts a PC in order against a table of known ones. It lives beside the CPU,
because that is mostly what decides it, and it is worth having because the parts
list does not always predict it -- two 486DX2-66s with the same score are the same
machine, and the one scoring half is telling you something (a cache left disabled,
a turbo button, a chipset set up wrong). NULL is a machine it has not been run on,
which is most of them; nothing infers a score from a CPU, since having actually run
it is the whole value of the field. Only an x86 machine has one -- there is no
TopBench for a Spectrum -- so the form asks for it only while the machine is not a
catalogue model, which is how it already says "a PC or a custom build". The box is
hidden rather than removed when a catalogue model is picked, because a hidden input
still submits what it holds and a score on file must survive being mis-filed and
put back.

A machine's drives are rows (`computer_drive`), each with how many, kind, form
factor, media size, the discs an optical drive takes and the rating on its front,
make/model, and its bezel: the shade it was made in and how far it has yellowed
since. Storage parts record the same things -- as their `Colour` and `Yellowing`,
`Media` and `Speed` specs -- so a drive on the shelf and one fitted in a machine
are described alike.

A drive's bay and what it takes are picked rather than typed, as short closed
lists of radio buttons with a "custom" box each for the hardware the list does not
name: the form factor (`drivedb.FORM_FACTORS`, 5.25"/3.5"/8", custom for a 3"
Amstrad CF-2); for a floppy, the capacity (`drivedb.SIZES`, 160K through 2.88MB,
custom for a Floptical or an LS-120); and for an optical drive, the discs it takes
(`drivedb.MEDIA`, CD-ROM through Blu-ray) and the rating on its front
(`drivedb.SPEEDS`, 1× to 52×). A form factor fits every drive that
lives on the drives field, since an optical drive is 5.25" as surely as a floppy is
3.5"; the capacities are floppy media designations, so that picker is offered for
`Floppy/Gotek` alone, and the other two for `Optical` alone. Each medium names the
most the drive does, on the understanding that it reads everything below it, and a
writer quoting three figures (48×/24×/48× for write, rewrite and read) types them
into the custom box, because which of the three a single number means is not a
question this catalogue should answer on the owner's behalf.
A pick is a deliberate answer, so it beats the same thing
said in the drive's description -- the rule the bezel menus follow -- and picking
nothing leaves the description to say it. Routed to a machine they become the
row's `form_factor` and `size`; kept as a part they are the drive's `Form factor`
and `Size` specs. A `Size` here is a media designation and not a quantity, so
unlike a memory `Size` it never normalises to KB: 1.44MB is 1475 KB only by
convention, and nobody calls that disk a 1475 KB.

With its pickers answered a drive's description has nothing left to say, so the box
is out of the way until it is wanted: when "custom" is chosen and the thing has to
be spelled out, when the kind has no pickers of its own to say what it is (a card
standing in for a drive), or when it already holds something -- a hidden box still
submits what it holds, so a full one is never hidden. The make and model come from
Identity, which a routed drive now reads (it never becomes a Part, so what was
typed there used to be dropped); they fill a blank rather than winning, because
what survives in a description after the pickers have taken their share is the
words they could not say, like the `SS/DD` on a Tandon TM100-1.

Because the picks arrive after the description has been read, a description naming
no kind ("Sony MPF920") no longer reaches drivedb's rule that a floppy-only size
means a floppy. The kind menu that routed the drive answers instead, read back
through drivedb's own vocabulary, and only where the text did not say -- which is
also why an early 5.25" CD-ROM drive is not filed as a floppy.

The eight drives recorded before the pickers existed were split into them by
migration 0016, which writes down what each becomes and is held to the parser's own
answers by a test. Six were said entirely by the two pickers and lost their
descriptions; two also record their media (`SS/DD`, `DS/DD`), which no picker
offers, and kept that much. Six of the eight wrote the inch mark as a curly `”` --
what a phone or a Mac autocorrects it to -- which drivedb did not know, so `3.5”`
was read as the drive's *model*. `_FORM_RE` now takes `"`, `”`, `“`, `″`, `''`,
`in` and `inch`.

A drive's `Speed` reads from two columns: `storage_spec.speed_rpm` for a spindle
and `speed_x` for an optical drive, because 48× and 5400 rpm are different
quantities and one column could sort neither. They answer to one `Speed` key, and
the unit written in the value decides which column takes it (`specstruct.ALT_COLS`)
-- so a person types and reads one Speed. A rating a writer quotes as three figures
is no kind of a number and rides as a verbatim attribute, the way an unparseable
quantity always has. In typed text a rating is only ever looked for in a segment
that is an optical drive's, which is what keeps the `2 x` of `2 x 5.25" 360K` the
two floppies it has always been; there, a run of figures carrying the mark is one
rating (`52x32x52x`, `4x 2x 20x`), and the count is written as a bare number so
nothing has to guess between them. The four optical drives recorded before any of
this asked for them were split into the new fields by migration 0017, held to the
parser's own answers by a test as 0016's eight were.

The small label carries those two on one line, `3.5" 1.44MB`, the way a drive is
spoken of; a hard disk's capacity and CHS geometry keep a line each as before. One
table in `labels.SMALL_SPECS` serves both, because the keys do not overlap.

Both vocabularies live in `app/entry.py` -- the factory shades from black through
the greys to the beiges, and the yellowing levels from lightly through browned to
unevenly -- and either can be recorded without the other, because an unrestored
find often shows only how yellow it is. They are separate fields on purpose: a
beige drive that has yellowed is still a beige drive, which is what makes "did
these two start the same colour" answerable. The names are the data; the swatches
are only there to choose by, and `entry.bezel_css` mixes the shade with the
yellowing so the chart in the edit forms, the swatch beside a menu and the one on a
part page cannot disagree. A bezel typed into the drives field or a routed drive's
description ("3.5in 1.44MB floppy beige, lightly yellowed") reads the same as the
menus, and renders back as `3.5" 1.44MB floppy (beige, lightly yellowed)`.

### Machines the catalogue names

A PC is described by what is fitted in it, one tagged part at a time. A home
computer or a console is not that sort of object: a ZX Spectrum is a sealed machine
that was built in a handful of documented forms, and what identifies one is which
form it is -- Issue 3B or 6A, 16K or 48K, a 5C102E ULA or a 6C001E-7, rubber keys or
moulded ones. None of that is a part to tag. Nobody shelves a ULA, photographs it or
gives it an asset id, and a register that made them do so would claim to hold forty
more objects than it does.

So a machine can also have a catalogue identity. `computer_variant` holds one row per
machine: which model it is (`model_key`), the board as its make marked it (`issue` --
Sinclair and Acorn number an issue, Commodore an ASSY, an Amiga a Rev, a Mega Drive a
VA), the case or keyboard it was built with (`style`), and the market it was sold in
(`region`). `computer_chip` holds one row per socket -- the ULA, the SID, the CRTC
type, the Kickstart in the ROM socket -- keyed by the catalogue's role slug with the
number marked on the chip. Memory chips are the exception that proves the rule and
keep their own table: they are counted rather than identified (see
`computer_ram_chip`).

The catalogue itself is `app/machines.py`: families, the models in each, and for
every model its standard memory sizes, board issues, styles, regions and chip
sockets with the variants that turn up in them. Sinclair, Commodore 8-bit, Amiga,
Atari 8-bit, Atari consoles, Atari ST, Acorn, Amstrad and Sega, at fifty-odd models.
Only the slugs are stored; a model's name, year, CPU and lists are read from the
catalogue every time, so correcting an entry there corrects every machine filed under
it -- the lesson migration 0011 wrote down about memory modules, applied before it
could be learned twice.

Every list names what is commonly seen rather than everything that exists, which is
why each variation is a radio group with a "custom" box beside it rather than a closed
menu -- the rule the drive pickers follow. A late board nobody has written up, a chip
swapped in a repair, a Spectrum+ converted from a rubber-key machine: all of those are
recorded by typing them.

And what is typed once is offered ever after. `machinedb.recorded` reads back every
answer already on file, keyed by the model it was given for, and
`machines.with_recorded` folds those into the lists the form offers: discover a ULA
the catalogue has never heard of and it is a radio button on the next machine, the
curated order kept and the discoveries after it. Two spellings that differ only in
case or spacing are one answer, so a chip does not appear twice for having been typed
twice, and what one model teaches is not offered on another -- a ULA found in a
Spectrum says nothing about a Commodore 64. That is what lets these lists be the
common cases rather than an inventory: the register completes them as it is used, and
what turns up often enough to be worth curating can be written into `machines.py`
later. A field the catalogue has no list for at all stays a plain box, because
offering "not recorded" and "custom" as the only two choices would be a menu that asks
a question and answers none of it.

A model that has no such socket says so and is not asked (a VIC-20 has no
SID, a ZX80 no ULA), a model can replace its family's chip for a socket with its own
(a Spectrum +2A has Amstrad's gate array where the family has a Ferranti ULA), and
what a machine records is kept whether or not the catalogue still lists it.

`computers.variant` is the rendered cache of both tables, in the same relation to them
as `installed_ram` is to the memory tables: written from the rows on every change,
read by the machine page, the label, the search index and the wire format, and never
parsed back. That is what makes a part number a way back to the machine -- the search
reads every text column, so `8580R5` finds the C64 it is in -- and what
`python -m app.resync` brings back into line when the catalogue's own words change
underneath a machine that has not been edited since.

The form's variation fields are built in the browser from the catalogue, because sixty
models' worth of menus rendered at once would be most of the page and all but one set
of them would be wrong. The model menu itself is server-rendered, so choosing a model
works without JavaScript, and a save that arrives without the marker the script sets
changes only the model and leaves the board issue, style, region and chips on file
alone: a form that could not draw them must not be able to erase them either. A change
of model keeps the chips whose sockets the new model also has and drops the rest, and
filing a machine out of the catalogue forgets the lot -- a machine that is no longer a
Spectrum has no Spectrum ULA.

Over the API a catalogue identity is the one nested shape, because it is not a string:
`GET /api/machines` returns the catalogue, and a computer's `machine` object takes
`model_key`, `issue`, `style`, `region` and `chips` (a `{role: variant}` map). Omitting
it leaves a machine's rows alone, sending `null` forgets them, and a model key or a
chip socket the catalogue does not have is refused rather than stored.

`year` is an integer, `acquired_date` and `disposed_at` are dates, and
`disposed` is a boolean whose detail lives in `disposed_note` -- the remaining
columns are text.

Part specifications are stored in dedicated tables rather than a single field.
Each part type has a table of typed columns: `motherboard_spec`, `cpu_spec`,
`ram_spec`, `video_spec`, `sound_spec`, `network_spec`, `io_spec` and
`storage_spec`. Fields that are naturally lists have child tables (`part_slot`,
`part_ram_slot`, `part_port`), and free-form types use `part_attribute`
key/value rows. This keeps specifications queryable, for example finding every
board with a VLB slot. The `parts.specs` text column holds a `Key: value | ...`
rendering of the same data, refreshed on every write (see `app/specstruct.py`
and `app/specdb.py`), and drives the search index and label text.

## Quick start

```
cp .env.example .env
docker compose up --build
```

Set the database passwords in `.env`. Optionally set `RHDB_AUTH_USER` and
`RHDB_AUTH_PASSWORD` for the login, and `RHDB_BASE_URL` for the hostname the
labels encode. On the host the GUI is at http://localhost:8000 and the docs at
`/docs`. In production Caddy serves it over HTTPS; see Access and HTTPS below.

## REST API

| Method | Path | |
|---|---|---|
| GET, POST | `/api/computers`, `/api/parts` | list, or create (server assigns the next asset id) |
| GET, PATCH, DELETE | `/api/computers/{id}`, `/api/parts/{id}` | fetch, partial update, delete |
| GET | `/api/machines` | the catalogue of known home machines and consoles, and the variations each was built in |

`GET /api/parts?computer_id=RH-0010` and `?type=sound` filter the list. PATCH
changes only the fields you send. A computer's `machine` object files it against the
catalogue (see [Machines the catalogue names](#machines-the-catalogue-names)). The
full schema and an interactive console are at `/docs`.

## MCP server

The `mcp` service wraps the REST API and exposes tools over the Model Context
Protocol:

- `list_computers`, `get_computer`, `create_computer`, `update_computer`, `delete_computer`
- `list_parts` (filter by `computer_id` or `type`), `get_part`, `create_part`, `update_part`, `delete_part`
- `list_machine_models` — the catalogue behind the `machine_*` arguments of
  `create_computer` and `update_computer`, which file a Spectrum, a C64 or a Mega
  Drive against a model and record its board issue, style, region and chips

It stores nothing of its own; every call is an HTTP request to the API, so the
MCP server, the GUI and the command-line tools all work against the same
database. It uses the streamable-HTTP transport on port 8001 and starts with the
stack. Point an MCP client at the endpoint; a project `.mcp.json` is committed at
the repo root, and the URL is:

```
http://localhost:8001/mcp
```

`create_*` assigns the next asset id; `update_*` changes only the fields you pass.

## Command-line tools (`tools/`)

These talk to the REST API over the network, so they can run on whichever
machine has the hardware attached (for example the one with the DYMO printers
and the floppy reader). Shared access and configuration live in `tools/rhdb.py`
and `tools/config.yml` (base URL, label sizes, printer names; nothing secret).

```
cd tools
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export RHDB_API=http://localhost:8000
```

- `make_labels.py` produces label PDFs with a QR code for each item. Options:
  `--small`, `--auto` (a full and small label for a computer, a small label for a
  real part), and `--print` (macOS/CUPS `lp`). The QR encodes
  `<base_url>/items/<asset_id>/`, which the app resolves to the right computer or
  part page; `base_url` defaults to https://db.2600.me. The GUI also renders
  labels for download.
- `import_report.py` reads an HWiNFO or MSD boot-disk report from
  `tools/imports/<asset_id>.txt` and proposes updates: CPU and OS on the
  computer, BIOS, chipset, onboard video and ports on its motherboard, and a
  storage part per detected drive. It writes nothing until you confirm.

The catalogue used to be mirrored to GitHub Pages by a static-site builder. The
app itself is now the published site, so the builder is gone; the old Pages URL
serves redirect stubs so labels printed against it still resolve.

## Access and HTTPS

Reads are public; writes need a login. Anonymous requests may GET the gallery,
item pages, photos and static assets. The new and edit forms, label PDFs, all
writes (POST, PATCH, DELETE), the JSON API and `/docs` require authentication,
configured with `RHDB_AUTH_USER` and `RHDB_AUTH_PASSWORD` in `.env` (leave both
blank to run without auth for local development). The browser signs in through a
login page and gets a signed session cookie, with a log out button in the
header. The JSON API and `/docs` also accept HTTP Basic, which is how the MCP
server and command-line tools authenticate (the tools also accept `auth_user`
and `auth_password` in `tools/config.yml`). The cookie is signed with
`RHDB_SECRET_KEY`. Editing controls appear only when logged in, and a visitor is
given the date of a history entry where whoever can edit it also sees the time of
day (the gallery's recency sort keys are trimmed to match).

The `caddy` service terminates HTTPS. It obtains and renews a Let's Encrypt
certificate for the hostname in `caddy/Caddyfile` (`db.2600.me`), compresses what
it serves (zstd or gzip, whichever the browser takes; already-compressed types
such as the photos are passed through untouched), and proxies to the app. To use a different hostname, edit the Caddyfile and restart Caddy; DNS
must point at the host and ports 80 and 443 must be reachable for the ACME
challenge.

Deployment on a fresh host -- DNS, the firewall, the first `docker compose up`,
and renewing certificates -- is in [DEPLOY.md](DEPLOY.md).

## Migrations

Alembic manages the schema, and the api runs `alembic upgrade head` on start
(see `api/entrypoint.sh`). To change the schema, edit `api/app/models.py` and
then:

```
docker compose exec api alembic revision --autogenerate -m "describe change"
docker compose exec api alembic upgrade head
```

## Backups

The data lives in two Docker volumes: `dbdata` (the database) and `images` (the
photos). `tools/backup.sh` writes a timestamped database dump and photo archive
to `./backups` (override with `RHDB_BACKUP_DIR`):

```
tools/backup.sh
```

It dumps the database with `mariadb-dump` and tars the photos; restore
instructions are in the script header. Copy `backups/` off the host for an
off-site copy.

## Local development

The app falls back to SQLite if you set `DATABASE_URL`:

```
cd api && pip install -r requirements.txt
DATABASE_URL=sqlite:///dev.db uvicorn app.main:app --reload
```

## Tests

```
python3 -m venv .venv-test
.venv-test/bin/pip install -r api/requirements.txt -r api/requirements-dev.txt
.venv-test/bin/pytest
.venv-test/bin/ruff check .
```

`api/tests/` runs the whole app against a throwaway SQLite database, built from
the models rather than from Alembic -- the migrations are deliberately
MariaDB-specific. Two halves:

- the pure functions, where silent data corruption lives: `specstruct` (the specs
  string <-> typed columns), `drivedb` and `ramdb` (a machine's drives and fitted
  memory), and `entry`'s amount handling and quick-entry expanders. The drive
  cases are the real notations the collection was recorded in, so a change that
  mis-reads them fails.
- the behaviour that has actually broken: typed columns taking form input, a
  select keeping a value outside its vocabulary, links unlinking rather than
  dangling when their target is deleted, and derived strings never being written
  to directly.

Both run in CI (`.github/workflows/ci.yml`) on push and pull request.
