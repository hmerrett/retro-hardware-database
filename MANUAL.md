# The Retro Hardware Database — manual

Everything the software does, and how to use it.

New here? [README.md](README.md) is the short introduction. Putting it on your
own server is [INSTALL.md](INSTALL.md).

**Contents**

1. [The idea](#1-the-idea)
2. [Getting around](#2-getting-around)
3. [Searching](#3-searching)
4. [An item page](#4-an-item-page)
5. [Adding a computer](#5-adding-a-computer)
6. [Machines the catalogue names](#6-machines-the-catalogue-names)
7. [Memory](#7-memory)
8. [Drives](#8-drives)
9. [Adding a part](#9-adding-a-part)
10. [Photographs](#10-photographs)
11. [Files](#11-files)
12. [Labels and QR codes](#12-labels-and-qr-codes)
13. [History](#13-history)
14. [Disposing, restoring and deleting](#14-disposing-restoring-and-deleting)
15. [Statistics](#15-statistics)
16. [Logging in](#16-logging-in)
17. [The REST API](#17-the-rest-api)
18. [The tool server](#18-the-tool-server)
19. [Command-line tools](#19-command-line-tools)
20. [Housekeeping](#20-housekeeping)

---

## 1. The idea

### Asset tags

Everything in the register — every machine and every part — has one asset tag,
unique across the whole collection: `RH-` followed by four characters, like
`RH-4K7Q`. The server allocates it; you never choose one. The alphabet leaves out
I, L and O, so nothing is ambiguous when you read a tag off a label and type it
back in. Tags are case-insensitive: `rh-4k7q` finds `RH-4K7Q`. (Early records
were numbered sequentially, `RH-0001` upwards; those tags still work.)

The tag is the thing's identity. It is what the label carries, what the QR code
encodes, what the URL uses, and what a file or a photograph is pinned to.

### Two tables

**Computers** are whole machines. **Parts** are components. A part records which
computer it is installed in, and optionally which other part it is mounted on —
so a hard disk can be mounted on a controller card which is fitted in a machine.
Both are NULL for a spare sitting on a shelf.

Pull a card out of a machine and unlink it, and its record stays exactly as it
was; it is now a spare. Put it in another machine and link it there. The card's
history records both moves.

### Two ways of describing a machine

This is the one idea worth understanding before you start typing.

**A PC is described by what is fitted in it.** A 486 tower is a motherboard, a
video card, a sound card, a hard disk, a floppy drive. Each of those is a real
object you can hold, shelve, photograph and swap, so each gets a tag and a page.
The machine's own record says very little — its case, its CPU, its OS — because
everything else is a part.

**A home computer or a console is described by which version of itself it is.** A
ZX Spectrum is a sealed box. What identifies one is its board issue (3B or 6A),
its memory (16K or 48K), the number on its ULA (5C102E or 6C001E-7), its keyboard
(rubber or moulded), and the region it was sold in. None of that is a part to
tag. Nobody shelves a ULA on its own, photographs one, or gives it an asset
number, and a register that made you do so would claim to hold forty more objects
than it does.

So a machine can be filed against a **catalogue model** instead, and its
variations recorded as attributes. See [section 6](#6-machines-the-catalogue-names).

A machine can of course be both — a Spectrum with a divIDE fitted has a catalogue
identity *and* a tagged part in it — and the pages adjust to show whichever
sections have something in them.

---

## 2. Getting around

### The gallery

The front page is every item as a photo card. Items with no photograph get a
placeholder icon appropriate to what they are: a board, a chip, a card, a floppy,
a disc, a keyboard.

The toolbar above the grid gives you:

- **Category** — computers, or one kind of part.
- **Sort** — Random (the default), Recently updated, Recently added, Recently
  acquired, Year newest/oldest first, Name A–Z, Maker A–Z, Category, Asset
  number. Your choice is remembered in a cookie. Choosing Random again deals a
  new hand.
- **Show disposed** — items that have left the collection are hidden by default.

The default is Random on purpose: a shelf is more interesting shuffled than in
the order things were last touched, and a recency sort only ever shows you the
same dozen items. Recency and random sorts both put photographed items first, so
the page does not open on a screenful of placeholder icons.

### The header

- **numbers** — the [statistics page](#15-statistics).
- **files** — everything [kept beside the register](#11-files).
- **API docs** — the interactive API console (login required).
- The **☾ button** toggles light and dark.
- **+ Computer** and **+ Part** appear once you are logged in.
- **traffic** and **log out** likewise.

### Moving between items

An item page has **prev** and **next** buttons. They walk the list the gallery
was last showing — that sort, that search, that category — which the browser
hands over as you leave the gallery. Arrive from a printed label instead, with no
gallery visit behind you, and they walk the register in asset order.

The buttons are the whole gesture. A sideways swipe used to do this as well, but
that is the phone's own back gesture, and taking it over left no way to go back.

### Photographs, full size

Click any photograph to open it as large as the window allows. From there:

| Gesture | Does |
|---|---|
| Double-click, double-tap | Zoom in and out |
| Wheel, trackpad, two-finger pinch | Zoom |
| Drag | Move about the enlarged photo |
| `+` `-` `0` | Zoom in, out, reset |
| ← → , sideways swipe | The other photographs of this item (arrow keys move about the photo instead while zoomed in) |
| `Esc` | Close |

The zoom belongs to the big view only, so the gallery and item pages still
pinch-zoom the way any web page does.

---

## 3. Searching

The search box is in the banner, so a search starts from whatever page you are
on.

**Press Enter** and the server searches every field of every item *and* its whole
history — specs, notes, source, condition, disposal reasons, the lot. Search for
`8580R5` and you get the C64 that part number is fitted in. Search for `recapped`
and you get everything whose history says so.

**On the gallery, typing filters the cards as you type**, without a round trip.
That filter reads a condensed blob on each card rather than the full text, so it
is the faster, narrower answer; press Enter for the real one.

**Type two characters** and a dropdown offers the first ten matches. Arrow keys
and Enter walk them; the last line says how many more there are. It runs exactly
the same search Enter does, so the list is a preview of the real answer rather
than a second, narrower search that disagrees with it. What it adds is an order:
what you typed being an asset tag, or the start of a name, comes before a hit
buried in a spec or a history note.

**Quoting works.** `"sound blaster"` is one term that must appear as a phrase;
`sound blaster` is two terms that must both appear somewhere. Multiple terms are
all-must-match.

### Scanning a label

Beside the search box, on a device with a camera, is a **scan** button. It reads
the QR code on a printed label and opens that item. Labels printed against an
older URL still work, because only the asset tag is taken from the code.

---

## 4. An item page

The page is a stack of panels — each section in a box with its title on a band
across the top.

Down the main column:

- **Summary** — the prose description, if one is written.
- **Details** — the record's own fields.
- **Machine** — for a machine filed against the catalogue: its model, its board
  issue, style and region, and a card per chip socket. ([Section 6](#6-machines-the-catalogue-names).)
- **Motherboard** and **Parts** — what is fitted in this machine, each as a card
  showing its tag, kind, name and specs. A part with nothing recorded gets no
  spec pairs at all, so the list also shows at a glance which parts have been
  written up.
- **Mounted parts** — on a part's page: what is mounted on this card.
- **Files** — [drivers, manuals, ROM dumps](#11-files) covering this item.
- **History** — [everything that has happened to it](#13-history).

Down the side column: the photographs, the disposal box, and the item's own QR
code.

Above it all, when logged in: **edit**, **duplicate**, **small label** and **full
label**.

### Duplicating

The copy button on an item page creates a second record of the same thing
immediately, with a new tag: same maker, model, specs, condition, and so on, but
none of the things that belong to the particular object — no photographs, no
history, no acquisition date, and for a machine, none of its parts.

If you would rather edit before saving, the new-part form takes a `from`
parameter — the "start from this one" route — which fills the form in and saves
nothing until you submit it.

---

## 5. Adding a computer

**+ Computer** in the header. Field by field:

| Field | What goes in it |
|---|---|
| **Catalogue model** | If this is a home computer or console the catalogue knows, pick it here first — it fills in half of what follows. See [section 6](#6-machines-the-catalogue-names). |
| **Name** | A display name. Overrides maker + model on the page and in lists. Leave blank and the machine is called "Compaq Deskpro 386". |
| **Manufacturer** | Or `Custom build`. |
| **Model** | |
| **Year** | |
| **Chassis / case** | desktop, tower, mini-tower, breadbin… |
| **Operating system** | |
| **CPU** | An attribute of the machine, not a part — unless you have the chip out on a shelf, in which case it is also a part. Write it as maker model-MHz: `Intel 486DX2-66`, `Intel 80286-6`, `2x Pentium III 500`. |
| **TopBench score** | The DOS benchmark's score for *this* machine. Only shown while the machine is not a catalogue model — there is no TopBench for a Spectrum. |
| **Memory** | Three inputs; see [section 7](#7-memory). |
| **Drives** | A table of rows; see [section 8](#8-drives). |
| **Condition** | Working, Untested, Partially working, Faulty, For parts/repair, Restored. Blank by default — "not recorded" is a real answer and should not be guessed as "Working". |
| **Source** | Where or how you got it. |
| **Acquired date** | |
| **Reference URL** | Wikipedia, The Retro Web, a forum thread. Also what the "fetch photo from reference" button reads. |
| **Summary** | The prose shown at the top of the page. |
| **Notes** | Anything else. |
| **Photographs** | Only on the new-machine form — there is no tag to file them under until it is saved. Afterwards they upload from the machine's own page. |

### About TopBench

`topbench` is the one measured number in a record that otherwise only says what a
machine was built as. It is worth having because the parts list does not always
predict it: two 486DX2-66s with the same score are the same machine, and one
scoring half is telling you something — a cache left disabled, a turbo button, a
chipset set up wrong. Blank means it has not been run on that machine, which is
most of them. Nothing infers a score from a CPU; having actually run it is the
whole value of the field.

### Building the machine out

Save the machine and its page offers, under **Motherboard** and **Parts**:

- **Create motherboard**, or **Link existing board** if you have an unlinked one.
- **Add:** storage/drive, video card, sound card, network card, I/O card, other
  expansion card, cpu, ram, peripheral.
- **Link existing part** — type an asset tag or a name.

Creating a part from here links it to the machine automatically and returns you
to the machine, so building out a PC is a straight run down the list.

---

## 6. Machines the catalogue names

The catalogue holds a little over three hundred home computers and consoles, from
seventy-odd makers, and for each model its standard memory sizes, board issues,
case and keyboard styles, regions, and chip sockets with the part numbers that
turn up in them. It runs from the 1975 Altair to the last of the 16-bit machines.

| | |
|---|---|
| **Britain** | Sinclair (ZX80 to the QL), Acorn (Atom, BBC, Electron, Archimedes to the Risc PC), Amstrad (CPC, PCW, GX4000, Notepad), Oric, Dragon, and the independents — Jupiter Cantab, Camputers, Memotech, Tatung, Enterprise, Grundy, MGT, Nascom, Research Machines, Tangerine, Science of Cambridge, Compukit |
| **Europe** | Thomson's MO and TO, Philips, Olivetti, Luxor, Matra, Exelvision, EACA, VTech — and the Eastern bloc: Robotron, Didaktik, Pravetz, Elwro, Videoton, Elektronika |
| **America** | Commodore PET, 8-bit and Amiga; Atari 8-bit, ST and consoles; Apple II, Macintosh and Lisa; Tandy TRS-80 and CoCo; TI-99; the consoles — Intellivision, ColecoVision, Vectrex, Channel F, Odyssey², Astrocade, Arcadia; and the S-100 and CP/M era — MITS, IMSAI, Processor Technology, Exidy, Osborne, Kaypro, Heathkit |
| **Japan** | Sega from the SG-1000 to the Saturn, Nintendo from the Game & Watch to the Virtual Boy, NEC's PC-88, PC-98 and PC Engine, Sharp's MZ, X1 and X68000, Fujitsu's FM line, SNK's Neo Geo, Sord, Casio, Epson, Epoch, Tomy, Toshiba, Sony, Hitachi, and twenty-five MSX machines from all of them |

Families are offered alphabetically by who made them, and each family's machines
alphabetically by name — with numbers read as numbers, so an Amiga 500 comes
before an Amiga 1000. Both orders are worked out when the file is read, so a
machine or a maker added anywhere in it still appears in the right place.

Pick a model from the menu at the top of the machine form and two things happen:

1. **The blanks fill in.** Manufacturer, model, year, CPU, chassis and OS are
   written into whichever of those boxes are still empty — never over the top of
   something you typed. The memory sizes that model was sold with are offered on
   the memory box.
2. **The variations appear underneath** — the board issue, the case or keyboard
   style, the region, and a box per chip socket with the part numbers that turn
   up in it.

A model that has no such socket says so and is not asked: a VIC-20 has no SID, a
ZX80 no ULA. A model can replace its family's chip for a socket with its own — a
Spectrum +2A has Amstrad's gate array where the family has a Ferranti ULA.

### Why they are boxes and not menus

Every list names what is **commonly seen**, not everything that exists. So each
variation is a set of choices with a **custom** box beside it. A late board nobody
has written up, a chip swapped in during a repair, a Spectrum+ converted from a
rubber-key machine: all of those are recorded by typing them.

And **what is typed once is offered ever after**. Discover a ULA the catalogue has
never heard of, and it is a choice on the next machine of that model — the
curated order first, discoveries after it. Two spellings that differ only in case
or spacing count as one answer, so a chip does not appear twice for having been
typed twice. What one model teaches is not offered on another: a ULA found in a
Spectrum says nothing about a Commodore 64.

That is what lets these lists be the common cases rather than an inventory. The
register completes them as you use it, and anything that turns up often enough to
be worth curating can be written into the catalogue later.

### Changing your mind

Changing the model keeps the chips whose sockets the new model also has, and
drops the rest. Filing a machine out of the catalogue altogether forgets the lot —
a machine that is no longer a Spectrum has no Spectrum ULA.

Memory chips are the exception to all of this. They are counted rather than
identified, so they keep their own grid on the form; see below.

### Finding a machine by a chip

Every part number recorded this way is searchable, because search reads every
text column. Type `8580R5` in the search box and you get the C64 it is fitted in.

### Adding a machine to the catalogue

The catalogue is one file — **`api/app/machines.yaml`** — and it is meant to be
edited by hand. No programming: it is an indented list, and the instructions for
adding to it are written at the top of the file itself. Find the family your
machine belongs to, copy the model above it, and correct the values. Restart the
API and it is in the picker.

A few things worth knowing before you start:

- **The `key` is permanent.** It is the only part of the catalogue a real machine's
  record stores. Every other word — a name, a label, a note, a part number — can be
  corrected whenever, and every machine already filed under it picks the correction
  up. Change a key and those machines are orphaned.
- **Get it wrong and the register will not start**, on purpose. The message names
  the family, the model and the field, and suggests the spelling you probably
  meant. A catalogue that half-loaded would quietly offer a Spectrum no ULA.
- **A family's chip sockets are asked of every model in it**, so the Z80 is written
  once for all the Spectrums. A model can name a different part for one socket, or
  give it an empty list to say it has not got that socket at all.
- After correcting wording that machines are already filed under, run
  `python -m app.resync --write` to bring their rendered lines into step
  (section 20).

---

## 7. Memory

A machine's memory is entered three ways, and all three are combined:

- **Memory modules (SIMMs / SIPPs)** — a grid of how many of each fitted module:
  256KiB/1MiB/4MiB 30-pin, the same in SIPP, and 1MiB through 32MiB 72-pin. The total
  is computed.
- **RAM chips (installed directly)** — for DRAM soldered or socketed on the board
  rather than on modules: 4116, 4164, 41256, 44256, 41464 and so on, each with
  its organisation shown. Enter how many of each.
- **Installed RAM — other / notes** — free text for anything the grids do not
  cover (DIMMs, unusual sizes), or just a plain total like `16MiB`.

### Parity

A count of chips that comes to a multiple of nine bits wide is treated as a bank
with parity, and the parity chips are not counted as capacity. Chips are grouped
by their addressable depth before that arithmetic is done, because a bank's data
and parity chips are often different part numbers — an Amstrad PC1640 carries
four 4464s for data with two 4164s alongside for their parity, and counting those
two as data would overstate the machine by 16 KiB.

### How amounts are stored

Memory amounts are normalised to KiB in the database, so they sort and compare
properly, and rendered back in the unit a person would use. A whole number of MiB
stays in MiB rather than climbing to GiB, because for this hardware the difference
is meaningful: 2096128 KiB is the 2047 MiB BIOS limit, not "2 GiB".

The units are the IEC ones — KiB, MiB, GiB — because the arithmetic behind them
has always been binary here: a K in this register is 1024 bytes and an M is 1024
of those, which is exactly what KiB and MiB mean. Nothing about the figures has
changed, only the word beside them. The older spellings are still read: type
`640KB` or `2MB` and it is understood, and written back as `640 KiB` and `2 MiB`.
A floppy's capacity is the exception, because it is a name rather than a
measurement — see section 8.

Once the units changed, every string already stored still said `KB`. Bring them
into line in one pass with `python -m app.resync --write` (section 20).

---

## 8. Drives

**Which drives are parts and which are fields on the machine?**

- **Hard disks and tape drives** are their own tagged parts. They have serial
  numbers, they get swapped between machines, they are worth photographing.
- **Floppy drives, Goteks, optical drives and SD/CF adapters** are rows on the
  machine's own record. They are a property of how the machine is configured.

The part form knows this. Add a "storage" part from inside a machine, pick
`Floppy/Gotek` or `Optical` or `SD/CF card` as its kind, and it is filed as a
drive row on that machine rather than becoming a part. Pick `Hard disk` or `Tape`
and it becomes a part with its own tag.

(A floppy drive on a shelf, with no machine to fit it to, becomes a part after
all — there is nowhere else to put it.)

### The drives table

On the machine form, each row has: how many, kind, form factor, size, media,
speed, make/model, and a bezel. Clear a row to remove that drive.

### The pickers

A drive's bay and what it takes are picked rather than typed, as short lists with
a **custom** box each:

| Picked | From | For |
|---|---|---|
| **Bay size** | 5.25", 3.5", 8" — custom for a 3" Amstrad CF-2, a 2.5" | every drive |
| **Capacity** | 160K, 180K, 320K, 360K, 720K, 1.2MB, 1.44MB, 2.88MB — custom for a Floptical or an LS-120 | floppies |

A floppy's capacity keeps the spelling it was sold under, and is the one figure in
the register that is not converted to KiB. It is a designation rather than a
measurement: nobody has ever called a 1.44MB disk anything else, and it is neither
1.44 million bytes nor 1.44 MiB but 1440 KiB. A hard disk's or a card's capacity
*is* a measurement, goes through the same arithmetic as everything else, and is
said in MiB and GiB.
| **Media** | CD-ROM, CD-R, CD-RW, DVD-ROM, DVD/CD-RW combo, DVD±RW, DVD-RAM, Blu-ray | optical |
| **Media** | QIC, Travan, DC6150, DDS/DAT, DLT, LTO | tape |
| **Speed** | 1× through 52× | optical |
| **Speed** | 3600 / 5400 / 7200 / 10000 / 15000 rpm | hard disks |

A capacity is what a floppy takes; a medium is what an optical drive takes. A
CD-ROM drive is not a "650MB anything", it is a drive that takes CDs — which is
why those are separate questions rather than one picker pointed at different
words. Each medium names the *most* the drive does, on the understanding that it
reads everything below it. A writer quoting three figures (48×/24×/48× for write,
rewrite and read) goes in the custom box, because which of the three a single
number would mean is not a question the catalogue should answer on your behalf.

A pick is a deliberate answer, so it beats the same thing said in the drive's
description. Picking nothing leaves the description to say it.

### The description box

With the pickers answered, a drive's description usually has nothing left to say,
so the box is out of the way until it is wanted: when "custom" is chosen and the
thing has to be spelled out, when the kind has no pickers of its own (a card
standing in for a drive), or when it already holds something. What survives in a
description after the pickers have taken their share is the words they could not
say — the `SS/DD` on a Tandon TM100-1.

The description is read as well as stored, so typing `3.5in 1.44MB floppy beige,
lightly yellowed` fills the same fields the pickers would, and renders back as
`3.5" 1.44MB floppy (beige, lightly yellowed)`. Curly quotes (`3.5”`), `″`, `''`,
`in` and `inch` are all understood as the inch mark.

### The bezel

Two separate fields: **the shade it was made in**, and **how far it has
yellowed**. Either can be recorded without the other, because an unrestored find
often shows only how yellow it is and a pristine spare only what shade it is.

The shades run from black through the greys to the beiges (Black, Dark grey,
Grey, Light grey, White, Off-white, Beige, Warm beige, Grey-beige) and the
yellowing levels from Lightly yellowed through Yellowed, Heavily yellowed and
Browned to Unevenly yellowed.

They are separate on purpose: a beige drive that has yellowed is still a beige
drive, which is what makes "did these two start the same colour" an answerable
question. The names are the data; the swatches beside the menus are only there to
choose by, and the same arithmetic draws the chart on the form, the swatch beside
a menu and the swatch on the item page, so none of them can disagree about what
"heavily yellowed beige" looks like.

Storage parts record the same two things as their `Colour` and `Yellowing` specs,
so a drive on the shelf and one fitted in a machine are described alike.

---

## 9. Adding a part

**+ Part** in the header, or one of the "Add" buttons on a machine's page.

Every part, whatever its type, has: **Type**, **Manufacturer**, **Model**,
**Name** (optional; defaults to maker + model), **Year**, **Condition**,
**Source**, **Acquired date**, **Reference URL**, **Summary**, **Notes**,
**Installed in** and **Mounted on**.

What differs by type is the specification section.

### Motherboard

- **Chipset** — e.g. Intel 430FX, OPTi 495
- **CPU family** — tick all that fit: 8088-class through Athlon-class, plus Z80
- **Form factor** — AT, Baby-AT, ATX, LPX, NLX, proprietary. *The machine's form
  factor is read from here.*
- **RAM slots** — how many of each: 30-pin SIMM, 72-pin SIMM, 168-pin DIMM,
  184-pin DIMM
- **Expansion slots** — how many of each: 8-bit ISA, 16-bit ISA, EISA, MCA, VLB,
  PCI, AGP, PCIe x16
- **Onboard RAM** — RAM soldered or socketed on the board itself
- **Cache** — e.g. 256 KiB, COAST socket
- **BIOS** — e.g. AMI 1992, Award 4.51
- **Onboard video** — e.g. VGA, or VGA C&T 65545
- **Onboard I/O ports** — how many of each

### CPU

Socket, Speed, FSB, Cores, Cache.

### Memory

Type (e.g. 72-pin FPM, EDO, SDRAM), Size (normalised to KiB), Speed.

### Video / Sound / Network / I/O

All four share **Main chip** and **Interface (bus)**, then:

- **Video** — Connector(s) (comma-separate several), Memory, Type
- **Sound** — FM synthesis, Ports
- **Network** — Connector (e.g. 10BASE-T, BNC, AUI)
- **I/O** — Ports

### Storage

See [section 8](#8-drives). A storage part is asked for its Kind first, and the
rest of the form is built from that: Interface (required), Protocol, Bay size,
Media, Capacity, Speed, CHS geometry, Role, bezel, and a disk-image filename for
hard disks.

Interface is required because "every SCSI drive" should stay a question the
collection can answer. The list is IDE, SATA, SCSI, MFM, RLL, ESDI, 34-pin
floppy, 26-pin floppy, CF, SD, USB, Proprietary — with a custom box.

### Cooling, Peripheral, Other

A free-text specs box, written as `Key: value | Key: value`.

### Quick entry

Two fields take shorthand and expand it for you:

- **Ports** takes letters: `IFSSP` becomes `IDE, Floppy, 2× Serial, Parallel`.
  The codes are I=IDE, C=SCSI, A=SATA, M=MFM, R=RLL, F=Floppy, S=Serial,
  P=Parallel, G=Game, K=PS/2 keyboard, O=PS/2 mouse, D=DIN keyboard, U=USB. Order
  does not matter; repeated letters become a count.
- **Expansion slots** takes `8I:2 16I:6 VLB` and gives `2× 8-bit ISA, 6× 16-bit
  ISA, VLB`. Tokens are `key`, `key:n`, `key*n` or `keyxn`.

Both fields also accept, and correctly re-read, the expanded form — so editing a
part does not corrupt what is already there.

### Where specifications are stored

Not in one text field. Each part type has a table of typed columns —
`motherboard_spec`, `cpu_spec`, `ram_spec`, `video_spec`, `sound_spec`,
`network_spec`, `io_spec`, `storage_spec` — with child tables for the things that
are naturally lists (slots, RAM slots, ports) and key/value rows for anything
free-form.

That is what makes "every board with a VLB slot" a query rather than a text
search, and what makes the [statistics page](#15-statistics) count things rather
than guess at them.

The `Key: value | ...` string you see on the page is a rendering of those
columns, refreshed on every write. It drives the search index and the label text.
Nothing writes to it directly.

### Small conveniences

Manufacturer and model are de-shouted as they are saved: a purely uppercase word
of five letters or more that is not a known acronym is capitalised normally, so
`CREATIVE LABS` becomes `Creative Labs` while `SCSI`, `BIOS` and part numbers are
left alone.

---

## 10. Photographs

**Upload** by choosing the files — that is the whole gesture, the upload goes as
soon as they are picked. Several at once is fine.

**From a phone.** Every item page ends in a QR code of its own URL, shown only
when you are logged in (a visitor has nothing to upload with). Scan it and the
phone is on that item, where choosing a photo shoots it or picks it from the
camera roll. A phone that arrives not logged in is put back on the item after
logging in, rather than dumped on the gallery.

**Per photo**, once logged in:

- **★ make default** — which photo represents the item in lists and previews.
- **🏷 mark as reference image** — this is a picture of *this model*, not of *this
  unit*. Reference images get a badge, and where the source site can be
  identified the badge is that site's favicon. They are never watermarked.
- **🗑 delete**.

**Rotate and crop** are in the full-size view: two rotate buttons and a crop tool.

**Fetch photo from reference** appears when the item has a reference URL. It
takes the lead image from a Wikipedia page, or the preview image any other site
advertises, downscales it and files it as a reference image. It bypasses nothing,
so a site behind bot protection simply returns nothing.

**Watermarking.** Your own photographs are stamped with the site logo as they are
served; reference images are not. Set `RHDB_WATERMARK=0` to serve everything
untouched. The originals on disk are never modified — the watermark is applied to
a cached copy.

---

## 11. Files

The **Files** panel on every item page, and the `/files` page in the header,
hold the things that come with hardware but are not hardware: a driver disk, a
manual, a ROM dump, the utility disk that shipped with a card.

Files are **not** attached to an asset tag. They are **tagged with the names they
are for**, and every item answering to one of those names offers them.

That is deliberate. A Trident 8900 driver is a fact about that card *as a model*,
not about the particular one on your shelf. A collection holding three of them
would otherwise carry the same download three times and lose two of them the day
two of the cards were disposed of.

### How the matching works

An item answers to its display name, its model, its maker and model together, and
its own asset tag.

A tag matches an item when the item's name **contains** the tag. So one file
tagged `Creative Labs Sound Blaster` appears on the AWE32, the 16 and the Pro,
because each of their names has it in. It goes one way only — the broader name
reaches the narrower thing, never the other way about — so a driver tagged for
the AWE32 does not turn up on a plain Sound Blaster.

Case and spaces make no difference: `Sound Blaster`, `soundblaster` and
`SOUND  BLASTER` are one name written by three people.

**To pin a file to one particular unit** — a receipt, a photograph of a repair —
tag it with that unit's asset tag. The upload box on an item page offers both:
it arrives prefilled with what the item is called, and the hint reminds you of
the tag.

Uploads are limited to 64 MiB each. The stored filename is generated, never taken
from the upload; the name you uploaded is kept as data, and used for the download.

---

## 12. Labels and QR codes

Every item page has two printer buttons: **small label** and **full label**, each
a PDF.

- **The full label** (6×4 inches by default) carries the asset tag, the name, the
  specifications and a QR code.
- **The small label** (51×19 mm by default, sized for a DYMO LabelWriter) carries
  the QR code, the asset tag and the make and model. A drive's bay size and
  capacity go on one line the way a drive is spoken of — `3.5" 1.44MB`; a hard
  disk's capacity and CHS geometry keep a line each.

**The QR code encodes `<base_url>/items/<asset_tag>/`**, which the app resolves
to the right computer or part page. Because only the tag is taken from a scanned
code, labels printed against an older URL still resolve.

`<base_url>` comes from `RHDB_BASE_URL` in `.env` for labels rendered by the
site, and from `base_url` in `tools/config.yml` for the command-line tool. **Set
it correctly before you print anything.**

For bulk printing, or for printing from the machine the label printer is attached
to, see [command-line tools](#19-command-line-tools).

---

## 13. History

Every item has a dated history, and it fills itself in. Creating, editing,
photographing, linking, unlinking, disposing and restoring all write a line
saying what changed.

**You can add a note** from the box at the top of the History panel — `tested`,
`cleaned`, `recapped`, `bought a replacement PSU for it`. Notes are marked as
notes; everything else is an automatic change record.

**A run of the same thing done in one sitting reads as one line.** Ten
photographs deleted one after another is "deleted 10 photographs", not ten
consecutive identical entries.

**A visitor sees the date; whoever can edit also sees the time of day.** The
gallery's recency sort keys are trimmed to match, so an anonymous visitor and a
logged-in one see the same ordering rules applied to the precision each of them
is shown.

History is searchable, which is often the point of writing it. Searching
`recapped` finds everything you have recapped.

---

## 14. Disposing, restoring and deleting

### Disposal

**Disposal is how something leaves the collection while keeping its record.** Sold,
binned, donated, given away, cannibalised. The disposal box on an item page takes
a reason and a date.

A disposed item keeps everything — its page, its photographs, its history, its
tag. It is hidden from the gallery unless you tick **show disposed**, and left
out of every figure on the statistics page except the count of disposals itself,
because a disposed item is a record of something gone.

**Disposing a machine disposes what is in it** — the parts installed in it, and
anything mounted on those in turn — on the same date and for the same reason. A
part already disposed keeps its own record.

**Restore** puts it back. Restoring a machine brings back only the parts that
went out with it.

### Deletion

For when the record itself should not exist — a duplicate, a mistake, a thing
scrapped that was never worth a line — a disposed item can be deleted outright
from the banner on its page.

**Only a disposed one.** The reversible step is a precondition of the
irreversible one, so nothing goes that has not already been marked as gone once,
deliberately, on an earlier day.

The confirmation page lists exactly what will go — the photographs, which are
deleted from disk, and the history with them — and asks you to **paste the item's
own URL** into a box. Nothing about that asks the database a question it does not
already know the answer to; the point is that deleting the wrong thing takes a
deliberate act, so a delete cannot be a stray click on a page you landed on by
accident.

Whatever pointed at the deleted item is unlinked first, and keeps a line in its
own history saying why it is suddenly standing alone.

A machine's **disposed** parts can be deleted along with it by ticking a box. Any
part still in the collection is kept whatever the box says.

---

## 15. Statistics

`/stats` is the collection by numbers, and it is public.

- **A headline** — how many things, how many machines, how many parts, how many
  photographs.
- **Eight things about it** — a pool of figures nobody strictly needs (most and
  least reliable maker, the longest wait between a thing being made and arriving
  here, what every floppy would hold if each had a disk in it), from which the
  page draws eight at random on each visit. A figure only joins the pool when it
  has something to say, so a young register offers fewer rather than offering
  blanks. Reload to shuffle.
- **Ranked charts** — makers by parts held, what the parts are, expansion buses,
  ports, condition, and makers by how much of their hardware still works.

**Every number is a link** to the items it counted, shown in the same grid as the
gallery. That is the point of the page: a figure you cannot get behind is a
figure you cannot check.

### About the reliability chart

"Reliability" there means one thing: **the share of a maker's parts recorded as
Working.** Not "Restored" — a part that had to be restored is evidence of the
opposite. And only parts still in the register, since a disposed one may have
been sold in perfect working order. A maker needs five parts to qualify;
"Unknown" and "Generic" are not makers. The caption on the page says so, because
a league table whose entry conditions are hidden is an opinion with a bar chart.

### Everything counts what it says it counts

Figures are counted live, from typed columns rather than by reading numbers back
out of text — so a figure on the page is the same figure the database sorts on.
Where a figure adds up quantities rather than counting assets (slots, chips,
drives), the note under the heading says whose they are.

### Traffic

`/traffic`, behind the login, is a GoAccess report built from the proxy's access
log and rebuilt every minute.

---

## 16. Logging in

**Reads are public. Writes need a login.**

Anonymous visitors can browse the gallery, item pages, the statistics, the files
and the photographs. The new and edit forms, the label PDFs, every write, the
JSON API and the API docs require authentication.

There is one account, set with `RHDB_AUTH_USER` and `RHDB_AUTH_PASSWORD`. Leave
both blank and the site runs with no authentication at all, which is only
sensible for local development.

- **In a browser**, you sign in through a login page and get a signed session
  cookie. The log out button is in the header. The cookie is signed with
  `RHDB_SECRET_KEY`.
- **The JSON API and the docs** also accept HTTP Basic, which is how the tool
  server and the command-line tools authenticate.

Editing controls simply do not appear when you are not logged in.

---

## 17. The REST API

Interactive documentation and a console are at `/docs` (login required). The
schema is at `/openapi.json`.

| Method | Path | |
|---|---|---|
| `GET`, `POST` | `/api/computers`, `/api/parts` | list, or create — the server assigns the asset tag |
| `GET`, `PATCH`, `DELETE` | `/api/computers/{id}`, `/api/parts/{id}` | fetch, partial update, delete |
| `GET` | `/api/items/{id}/log` | an item's history |
| `GET` | `/api/machines` | the catalogue of known home machines and consoles, and the variations each was built in |
| `GET` | `/api/files` | the files kept beside the register |

`GET /api/parts?computer_id=RH-4K7Q` and `?type=sound` filter the list.

`PATCH` changes only the fields you send.

A computer's catalogue identity is the one nested shape, because it is not a
string. Its `machine` object takes `model_key`, `issue`, `style`, `region` and
`chips` (a `{role: variant}` map). Omitting it leaves a machine's existing
identity alone; sending `null` forgets it. A model key or a chip socket the
catalogue does not have is refused rather than stored.

Authenticate with HTTP Basic:

```sh
curl -u user:pass https://db.example.com/api/parts?type=video
```

---

## 18. The tool server

The `mcp` service wraps the REST API and exposes it as a set of tools over the
Model Context Protocol, on `http://localhost:8001/mcp` (streamable HTTP
transport). It starts with the rest of the stack. A project configuration file,
`.mcp.json`, is committed at the repository root.

The tools are:

- `list_computers`, `get_computer`, `create_computer`, `update_computer`,
  `delete_computer`
- `list_parts` (filter by `computer_id` or `type`), `get_part`, `create_part`,
  `update_part`, `delete_part`
- `list_machine_models` — the catalogue behind the `machine_*` arguments of
  `create_computer` and `update_computer`, which file a Spectrum, a C64 or a Mega
  Drive against a model and record its board issue, style, region and chips

It stores nothing of its own. Every call is an HTTP request to the API, so the
tool server, the GUI and the command-line tools all work against the same
database and obey the same rules. `create_*` assigns the next asset tag;
`update_*` changes only the fields you pass.

---

## 19. Command-line tools

The scripts in `tools/` talk to the REST API over the network, so they can run on
whichever machine has the hardware attached — the one with the label printers, or
the one with the floppy reader.

```sh
cd tools
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export RHDB_API=https://db.example.com
export RHDB_AUTH_USER=... RHDB_AUTH_PASSWORD=...
```

Shared access and configuration live in `tools/rhdb.py` and `tools/config.yml`
(base URL, label sizes, printer names — nothing secret). Every script also takes
`--api` to override the URL for one run.

### make_labels.py

Label PDFs with a QR code for each item.

```sh
python make_labels.py                 # every item
python make_labels.py RH-4K7Q RH-9J2X # named items
python make_labels.py --small RH-4K7Q # the small label
python make_labels.py --auto RH-4K7Q  # full + small for a computer,
                                      # small for a part
python make_labels.py --print RH-4K7Q # send it to a CUPS printer
python make_labels.py -o out.pdf ...  # write somewhere specific
```

Label geometry, the QR error-correction level, rotation, the display font and the
printer names are all in `tools/config.yml`. List your printers with
`lpstat -p`.

### import_report.py

Reads a hardware detection report from a boot disk — HWiNFO on a 386 or better,
MSD on an XT or 286 — and **proposes** updates. It writes nothing until you
confirm.

Put the report at `tools/imports/<asset_tag>.txt` and run:

```sh
python import_report.py               # every report in imports/
python import_report.py RH-4K7Q       # just one
```

What it maps:

| From the report | Onto |
|---|---|
| Main Processor, OS | the computer |
| Onboard video, BIOS, Chipset, onboard I/O ports | the motherboard linked to it |
| each detected, non-empty drive | one storage part |

Memory is deliberately left alone: HWiNFO's total is unreliable on pre-Pentium
machines, so a machine's memory is entered by hand.

---


### catalogue_list.py

`catalogue.txt` in the repository root is the machine catalogue as plain text —
every maker and every machine, and none of the detail — for the question that is
asked far more often than any question about a board issue: what is in it?

```sh
python tools/catalogue_list.py            # rewrite it
python tools/catalogue_list.py --check    # is it in step?
```

It is generated from `api/app/machines.yaml`, so it goes stale the moment a
machine is added. Add one, run this, and commit both; a test fails if you forget.
Unlike the other scripts here it reads the catalogue file directly rather than the
API, so it needs no network and no login.

## 20. Housekeeping

### Derived values

Three things in the database are rendered caches, written from their source rows
on every change and never parsed back:

- `parts.specs` — the `Key: value | ...` string, over the typed spec tables
- `computers.installed_ram` / `installed_ram_kb` — over the memory tables
- `computers.variant` — over the catalogue identity tables

They drift only when something changes *underneath* them — most often when you
edit the machine catalogue (`api/app/machines.yaml`), whose words are read from
that file rather than from the record. Any item you edit fixes itself. To bring the whole database into step
in one pass:

```sh
docker compose exec api python -m app.resync
```

It prints what it would change before changing anything.

### Schema changes

Alembic manages the schema and the app runs `alembic upgrade head` on start, so
an upgrade needs no separate migration step. To make a schema change, edit
`api/app/models.py` and then:

```sh
docker compose exec api alembic revision --autogenerate -m "describe change"
docker compose exec api alembic upgrade head
```

The migrations are deliberately MariaDB-specific. The test suite builds its
tables from the models instead, against a throwaway SQLite database.

### Backups

`tools/backup.sh` writes a timestamped database dump and photo archive into
`./backups`. Restore instructions are in the script's header comment, and the
whole subject is covered in [INSTALL.md](INSTALL.md#7-back-it-up).

### Tests

```sh
python3 -m venv .venv-test
.venv-test/bin/pip install -r api/requirements.txt -r api/requirements-dev.txt
.venv-test/bin/pytest
.venv-test/bin/ruff check .
```

The suite is in two halves: the pure functions where silent data corruption lives
(the specs string against the typed columns, drive parsing, memory arithmetic,
the quick-entry expanders), and the behaviour that has actually broken before
(typed columns taking form input, a menu keeping a value from outside its
vocabulary, links unlinking rather than dangling when their target is deleted,
derived strings never being written to directly). The drive cases are the real
notations this collection was recorded in, so a change that misreads them fails.

Both run in CI on every push and pull request.
