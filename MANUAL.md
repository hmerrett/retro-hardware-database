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
12. [Projects](#12-projects)
13. [Labels and QR codes](#13-labels-and-qr-codes)
14. [History](#14-history)
15. [Disposing, restoring and deleting](#15-disposing-restoring-and-deleting)
16. [Statistics](#16-statistics)
17. [Logging in](#17-logging-in)
18. [The REST API](#18-the-rest-api)
19. [The tool server](#19-the-tool-server)
20. [Command-line tools](#20-command-line-tools)
21. [Housekeeping](#21-housekeeping)

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

**A branded PC is described both ways at once.** An IBM 5170 is a box with cards
in it *and* a machine with a planar type, a BIOS date and a badge — so it gets a
catalogue identity saying which machine it is and tagged parts saying what is
fitted in it, and neither answers the other's question. A clone nobody documented
gets the first description only, because there is no model to name it as.

So a machine can be filed against a **catalogue model** instead, and its
variations recorded as attributes. See [section 6](#6-machines-the-catalogue-names).

A machine can of course be both — a Spectrum with a divIDE fitted has a catalogue
identity *and* a tagged part in it — and the pages adjust to show whichever
sections have something in them.

The two meet at the motherboard. A board lifted out of a sealed machine becomes a
tagged object the moment it is a thing on a shelf, and it is still an Amiga 500
board — so a motherboard can carry a catalogue identity of its own. See [a board
on its own](#a-board-on-its-own).

---

## 2. Getting around

### The gallery

The front page is every item as a photo card. Items with no photograph get a
placeholder icon appropriate to what they are: a board, a chip, a card, a floppy,
a disc, a keyboard. The item's own page draws the same icon where the photograph
would be, so a card and the page it opens show the same picture and the column
keeps its shape whether or not anybody has been round with a camera yet.

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

On a desktop the banner reads in three bands: where you can go on the left, the
search box in the middle, and what you can do on the right.

- **browse**, **projects**, **numbers**, **models**, **files** — the sections.
  The one you are in is shown in bold. **models** is the catalogue of machines the
  register knows as models; **browse** is the machines it actually holds;
  **projects** is what is being done to them — see
  [section 12](#12-projects). **projects** sits next to **browse** because the two
  are a pair: what is owned, and the work in hand.
- **Search anything…** and **scan** — see [Finding things](#3-searching).
  The scan button appears only where there is a camera to use.
- **+ New** — offers Computer, Part or Project. Logged in only.
- **⋯** — the theme, **traffic** and **log out**, and (in the installed app,
  where the browser provides neither) share and reload.
- **API docs** — the interactive API console (login required), at the foot of
  the page.

### The header on a phone

The banner keeps the name and the search box; everything else moves to a bar
across the bottom of the screen, where your thumb already is.

- **Browse** — the gallery.
- **Find** — scrolls back up and puts the cursor in the search box.
- **Scan** — reads a label's code. Appears only where there is a camera.
- **More** — one list holding the sections (**projects**, **numbers**,
  **models**, **files**), **+ Computer**, **+ Part**, **+ Project**, the theme,
  **traffic** and **log out**.

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
| Pinch — two fingers, or a trackpad | Zoom |
| Scroll, two-finger scroll | Zoom in from the whole photograph, and move about it once you are in |
| `⌘` or `ctrl` with a scroll | Zoom, at any point |
| Drag, flick | Move about the enlarged photograph |
| `+` `-` `0` | Zoom in, out, reset |
| ← → , sideways swipe | The other photographs of this item (arrow keys move about the photo instead while zoomed in) |
| Flick up or down | Close, on a phone: the photograph comes with your finger and the page shows through behind it. Let go past the mark and it drops back into its thumbnail; short of the mark it springs back out to the window |
| `Esc` | Close |

It opens out of the photograph you clicked, and shuts back into it. The big view
grows from that thumbnail, and however you leave — flicked away, `Esc`, the ×, a
click on the black beside the photograph — it shrinks back into the same one,
cropping to the thumbnail's shape as it goes, so what was on the screen a moment
ago is where your eye already is. Walk on to another photograph with the arrows
and it is that one's thumbnail it returns to, scrolled back into view if it had
gone off the page: the item page is left showing the photograph you were actually
looking at. The thumbnail's own copy stands in behind the big view until the
original has loaded, which is why the first moment of a photograph you have not
opened before is a soft one.

Logged in, the big view is also the editor: a toolbar along the bottom rotates,
crops and deletes the photograph you are looking at. See [what a photo can
have done to it](#10-photographs).

A tall photograph opens on a wide screen with a black band down either side, and
a wide one on a phone with a band above and below. Zooming in spends those bands
rather than magnifying inside them: the photograph spreads into the whole window,
and a double-click or double-tap goes straight to filling it.

It moves like something with weight, on a trackpad as on a phone. A flick carries
on and slows; an edge pulled past resists, and springs back when let go; a pinch
past the last of the zoom stretches a little and is taken back. If your system is
set to reduce motion, none of that happens — the photograph is simply where it
should be, at once.

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

Projects are searched by the same words, and the match reaches their jobs and the
things they have on order as well as their own text — so `Gotek` finds the project
with one in the post. They do not become cards in the gallery, which stays a wall
of photographs of things owned; the line above the results says how many projects
matched and links to them. See [section 12](#12-projects).

**On the gallery, typing filters the cards as you type**, without a round trip.
That filter reads a condensed blob on each card rather than the full text, so it
is the faster, narrower answer; press Enter for the real one.

**Type two characters** and a dropdown offers the first ten matches — computers,
parts and projects alike. Arrow keys and Enter walk them; the last line says how
many more there are. It runs exactly
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
- **History** — [everything that has happened to it](#14-history).

Down the side column: the photographs, the disposal box, and the item's own QR
code.

Above it all, when logged in: **edit**, **duplicate**, **small label** and **full
label**.

A URL written into any of that — a summary, a note, a spec value, where the item
came from, a history entry — is a link you can follow. Anything with a scheme in
front of it (`http://`, `https://`, `ftp://`, `mailto:`), anything beginning
`www.`, and anything with the shape of an email address. Off-site links open in a
tab of their own, so following one out of the register does not lose your place in
it. Nothing else is touched, and that is deliberate: `config.sys` and `1.44MB`
have a hostname's shape and neither is one, so a bare hostname stays text. Put the
`www.` or the scheme in front of it and it is a link.

### When it changes while you are looking at it

The register gets used from two places at once: you scan the label with a phone
and photograph the thing while the desktop still shows its page. The desktop used
to sit there showing a record that was no longer true.

An item page now notices. It asks a small endpoint what the record amounts to now
and compares that with what it was built from — a photograph added, rotated,
cropped or deleted, a field edited, a note written, a file uploaded. It asks every
fifteen seconds, and once immediately whenever the tab is looked at again, which
is the moment that matters: you photograph on the phone, turn back to the desktop,
and the check has already run by the time your eyes arrive. A tab in the
background asks nothing at all.

It reloads on its own only when that takes nothing away from you. If the
full-size view is open, or you are part-way through a note, a search or any other
box, it says **This record has changed** at the foot of the page and waits — a
page that reloaded itself mid-sentence would be worse than one that is out of
date. Clicking **Reload** loads it, and so does simply clicking away from
whatever you were in the middle of.

The gallery is not given this: there is no one record for it to be watching.

### Duplicating

The copy button on an item page creates a second record of the same thing
immediately, with a new tag: same maker, model, specs, condition, and so on, but
none of the things that belong to the particular object — no photographs, no
history, no acquisition date, no serial number, and for a machine, none of its
parts.

If you would rather edit before saving, the new-part form takes a `from`
parameter — the "start from this one" route — which fills the form in and saves
nothing until you submit it.

---

## 5. Adding a computer

**+ Computer** in the header. Field by field:

| Field | What goes in it |
|---|---|
| **Catalogue model** | If the catalogue knows this machine — a home computer, a console, a branded PC — pick it here first — it fills in half of what follows. See [section 6](#6-machines-the-catalogue-names). |
| **Name** | A display name. Overrides maker + model on the page and in lists. Leave blank and the machine is called "Compaq Deskpro 386". |
| **Manufacturer** | Or `Custom build`. |
| **Model** | |
| **Year** | |
| **Serial number** | The number stamped on *this* machine. The one field that is not a fact about the model, and the one that tells two of the same machine apart. Searchable, so a machine can be found by the number on its own back. |
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
  expansion card, cpu, ram, display, peripheral.
- **Link existing part** — type an asset tag or a name.

Creating a part from here links it to the machine automatically and returns you
to the machine, so building out a PC is a straight run down the list.

---

## 6. Machines the catalogue names

The catalogue holds four hundred machines, from seventy-odd makers, and for each
model its standard memory sizes, board issues, case and keyboard styles, regions,
and chip sockets with the part numbers that turn up in them. It runs from the
1975 Altair to the PlayStation 3 — the far end moved for Sony's console line,
which is one family that kept going, rather than for the era in general.

**What is in it, and what is not.** Home computers and consoles, and the branded
PCs that were sold under a model name — an IBM
5170, a Compaq Deskpro 386, an Amstrad PC1640. The line is not "home machine or
PC"; it is whether the thing was sold as a model somebody wrote down. A whitebox
clone was not, and is not in here and never will be: it is described by the parts
in it, which is all there is to say about it.

A branded PC gets both descriptions, and they do not compete. The catalogue
identity says *which machine this is* — the planar type, the BIOS date, the badge
on the front. The parts tagged into it say *what is fitted in it today*. Nothing
about how PC parts are recorded changes; the catalogue is one more thing the
machine can answer.

**The whole list is at [/machines](#the-list-of-what-it-knows)** — see below.

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

### The list of what it knows

`/machines` is the catalogue read rather than picked from: every model it names,
by maker, with the year and the CPU, on one page. It is **public** — there is
nothing of the register on it, since it is a list of what was made rather than of
what is here — and it has no search box, because a list you can search with your
browser's own find is worth more than a list with a filter on it.

Where the register holds something filed as a model, the row says so and the
count leads to it. Machines and bare boards both, since a motherboard files
against a model the same way a whole machine does.

A **▸** after a model's name opens a paragraph on what it is: what the machine
did that its neighbours did not, and what a collector would look for. Folded
away rather than laid out, because four hundred paragraphs at once would be a
different page for a different job — but the browser's own find still reaches
into the folds and opens the one it lands in. The same paragraph is printed in
full at the top of an item's own page, in muted ink, because it is reference
about the model rather than a fact about the object in front of you.

**Only where the item has no summary of its own.** The two are different kinds of
statement and a page never shows both: whatever you have written about this
particular object wins, and the model's paragraph is what fills the gap until you
write one. Machines and catalogue-filed boards behave identically.

The folds are plain `<details>` elements and need no JavaScript. They briefly
did need a CSS `:has()` rule, which worked in Chrome and in current Safari and
not in older Safari, where the marker flipped and revealed nothing — so the
paragraph now lives inside the element that hides it, which has worked
everywhere for a decade.

Two other shapes of the same list: `catalogue.txt` in the repository, and
[`/api/machines`](#18-the-rest-api) for anything that would rather read JSON —
public for the same reason the page is.

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

### A board on its own

A bare motherboard out of one of these machines is a real object with a tag of
its own, and it is exactly the thing the questions above were always about: the
board issue is the board's, and so are the chips in its sockets. So a **part of
type motherboard is offered the same pickers** — the model, the board revision,
and a box per chip socket — and the catalogue panel appears on its page just as
it does on a machine's.

That is how a spare on a shelf is filed as *Amiga 500, Rev 6A, these chips*
rather than as a sentence in the notes. Picking the model fills in the maker,
model and year here too.

A board is not asked the two questions a **case** answers — the keyboard style
and the region — because a board out of a rubber-key Spectrum is the same board
as one out of a moulded one, and a PAL machine's board is not a PAL board.

Everything else is shared, including what the register learns: a revision or a
chip typed into a custom box on a board is offered on the next machine of that
model, and the other way round. It is the same board either way, and which object
you read it off is exactly what does not matter about it.

No other kind of part gets this. A SIMM is not a model of machine, and the API
refuses one rather than quietly ignoring it.

### Detaching the board

The two sections above describe the same board twice over — once as an answer a
sealed machine gives about itself, once as an object on a shelf. **Detach the
board** is the moment one becomes the other.

The link is in the Machine panel on the machine's page, which is the panel whose
contents move. It offers itself on a machine the catalogue names that has no
motherboard linked to it yet, and it opens a page that says what will happen
before anything does.

Press it when the board is actually out. That is the whole rule: a part in the
register is a thing that leads a separate life — photographed, tagged, swappable,
sellable on its own — and until the board is out of the case, what it is belongs
to the description of the machine. Nothing detaches a board because the catalogue
says the machine has one.

What happens:

- **A new motherboard part**, filed under the same catalogue model. The machine is
  still a Spectrum and the board is a Spectrum board.
- **The board issue and the chips move onto it.** They were always facts about the
  board; the machine stops claiming to know which board is in it, because the board
  answers for itself now.
- **The style and the region stay behind.** A keyboard style and the market a
  machine was sold into are facts about the assembled computer in its box, and the
  box did not move.
- **The board is linked back into the machine** it came out of, so the machine's
  page shows it where its motherboard goes.
- **A line in both histories**, each naming the other's asset tag.
- The machine keeps its asset tag, its photographs and every line of its history.
  It is still the machine on the shelf; what changed is that one of the things it
  is made of is on the shelf beside it.

**The page asks for the board's photograph**, and this is the only place it asks.
A board is photographable while it is out on the bench and before it goes back in,
and that moment does not come round again — every object in the register is meant
to have one portrait, and this is the one chance to take this one's. It is not
compulsory: a separation that really happened should be recorded even with no
camera to hand.

It goes one way. There is no re-absorb that would fold the object back into a
description, because that would mean deleting a tagged, photographed thing.
**Refitting a board is ordinary linking** — unlink it, link it to this machine or
to another, exactly as with any part — and the board keeps its own answers through
all of it.

Two things it will refuse. A machine the catalogue does not name has no board
issue and no chips to move, so a **PC's board is entered as a part** in the
ordinary way (section 9). And a machine that **already has a board linked** has
one board: without that, the button would be one object per press rather than one
object per separation, which is inventing hardware rather than recording it.

A machine's memory rows stay with the machine. They count chips rather than
identify them, and they are half of how its installed RAM figure is worked out
(section 7).

### Finding a machine by a chip

Every part number recorded this way is searchable, because search reads every
text column. Type `8580R5` in the search box and you get the C64 it is fitted in
— or the loose board it is on.

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
- **`summary:` is optional and is prose, not specification.** Around 75 words on
  what makes the model worth holding — what it did that its neighbours did not.
  Leave it out rather than guess: an invented significance is worse than none,
  and the pages that show it fall back to the specs. It is deliberately kept out
  of the catalogue JSON the edit forms download, which the paragraphs would
  otherwise double in size for no reader.
- After correcting wording that machines are already filed under, run
  `python -m app.resync --write` to bring their rendered lines into step
  (section 21).

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
into line in one pass with `python -m app.resync --write` (section 21).

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
**Name** (optional; defaults to maker + model), **Year**, **Serial number**,
**Condition**, **Source**, **Acquired date**, **Reference URL**, **Summary**,
**Notes**, **Installed in** and **Mounted on**.

**Serial number** is the number marked on that particular one — the only field
that is never true of a second object, which is why the **duplicate** button
leaves it behind along with the photographs and the provenance. It is worth the
typing where nothing else tells two things apart: which of two identical SIMMs
came out of which machine, or whether the drive back from a repair is the drive
that went. It is searchable like every other field.

What differs by type is the specification section.

### Motherboard

A motherboard is also the one part that can be filed against the catalogue: a
**Catalogue** section at the top of the form asks which machine the board is out
of, its revision, and what is in its sockets. See [a board on its
own](#a-board-on-its-own). Leave it at *not a catalogue model* for a PC board,
which is what the fields below describe.

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

### Display

A monitor, a fitted panel, the tube out of an all-in-one. Everything here is
picked from a list rather than typed, the way a drive's fields are, with **custom**
and a box beside it for the hardware the list does not name.

- **Type** — CRT, LCD, Plasma, OLED, Electroluminescent, VFD, LED matrix, E-paper
- **Tube or panel** — how that technology is built: Shadow mask, Aperture grille
  (Trinitron), Aperture grille (Diamondtron), Aperture grille, Slot mask, TN, IPS,
  VA, DSTN, STN
- **Screen size** — the diagonal, as the thing was sold: 9" through 24", plus the
  small ones. Stored as a number, so "every 14-inch and under" is a query.
- **Aspect ratio** — 4:3, 5:4, 16:10, 16:9, 3:2
- **Resolution** — a panel's native one, or the most a tube will do. A multisync
  monitor that does a range says so in the custom box.
- **Refresh rate** — **tick every rate it will do**, 50 Hz through 120 Hz, with the
  box for a range. A screen that does 50 Hz for a television-rate mode and 85 Hz for
  its best VGA one does both, and the highest on its own is not the useful half:
  whether a machine putting out 50 Hz will be met is the question.
- **Sync rate** — **tick every line rate it will lock to**, 15 kHz through 80 kHz,
  with a box for a monitor that quotes a range instead. This is the field that says
  whether a machine can drive the screen at all rather than how well: a plain VGA
  monitor shows nothing at the 15 kHz of a television however good its tube is,
  where an Acorn AKF18 takes 15–38 kHz and so puts up a BBC mode and a VGA one
  both. Tick the rates a screen lists; type the range a multiscan claims.
- **Dot pitch** — 0.20 mm to 0.39 mm. Also stored as a number, so "anything finer
  than 0.28" is a comparison rather than a text search.
- **Interface** — **tick every socket it has**, not one of them. VGA (HD-15),
  DVI-D/I/A, HDMI, DisplayPort, the 9-pin TTL cables of an MDA/CGA/EGA monitor,
  13W3, BNC, SCART, S-Video, Composite, Component, RGB DIN, RF — plus a box for
  anything else, which joins the ticked ones.
- **Picture** — Colour, or which phosphor a monochrome screen has: Green, Amber,
  White, Paper white, Greyscale
- **Bezel** — the same two menus a drive gets, and the same colour chart. See
  [the bezel](#the-bezel).

Type and Tube are kept apart on purpose. A Trinitron is a CRT — it is a CRT with
an aperture grille where a cheaper tube has a shadow mask — so filing one under a
single field would take it out of the count of CRTs the moment you picked the
trade name. Kept apart, *every CRT* and *every aperture grille* are both
questions the collection can answer.

**Interface, refresh rate and sync rate are ticked rather than chosen** because a
screen genuinely answers all three more than once: a monitor of the DVI years has a
VGA socket beside it, a home-computer monitor takes composite as well as RGB, and a
tube that locks to 15 kHz and to 31 kHz does both and nothing between them. A single
choice would make you decide which of its sockets, or which of its rates, to leave
out.

An answer already on a record that is not in the list — one typed before the list
said otherwise — reopens on **custom** with the box filled in, so nothing is lost
by editing a screen somebody else wrote up.

The two numbers are stored as numbers — tenths of an inch and micrometres — and
read back in the units you would write, so `21"` reopens as `21"` and `0.28` reopens
as `0.28 mm`. The two rates are text, because each holds a set or a range rather
than one figure. See [where specifications are
stored](#where-specifications-are-stored).

### Cooling, Peripheral, Other

A free-text specs box, written as `Key: value | Key: value`.

### Changing a part's type

The **Type** menu at the top of the form rebuilds it with that type's fields —
what a part is asked depends on what it is, so the fields for the new type are not
on the page until the form is fetched again. Nothing is saved by doing it; the
record still says what it always did until you press **Save**. If you have typed
anything since opening the form, it asks first, because fetching the form again
means asking the server and the server cannot know what is in your boxes.

**What was already recorded comes with it.** A value the new type also asks about
is offered back through its own control — a monitor filed as *other* with
`Type: CRT` on it arrives at the Display form with CRT already chosen. A value the
new type has no question for is kept anyway, as an extra spec on the record, so
retyping a video card to a display does not lose the chip it was built round.

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
`network_spec`, `io_spec`, `storage_spec`, `display_spec` — with child tables for
the things that are naturally lists (slots, RAM slots, ports) and key/value rows
for anything free-form.

That is what makes "every board with a VLB slot" a query rather than a text
search, and what makes the [statistics page](#16-statistics) count things rather
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

This section is about an item's own photographs: the ones in the Photographs
panel, which answer *which one is this?* A photograph of something that happened
to it — a recap, a repair, damage found on arrival — belongs on the history entry
that says what happened, and is described in [section 14](#14-history).

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

**Rotate, crop and delete** are in the full-size view: two rotate buttons, a crop
tool, and a delete at the far end of the row. Rotating and cropping return you to
the same photograph still open, so a run of corrections is one gesture after
another; deleting cannot, so it asks first and puts you back on the item page.
The delete steps out of the row while you are cropping, where it would otherwise
be sitting next to **apply crop**.

**Fetch photo from reference** appears when the item has a reference URL. It
takes the lead image from a Wikipedia page, or the preview image any other site
advertises, downscales it and files it as a reference image. It bypasses nothing,
so a site behind bot protection simply returns nothing.

**Taken on the phone, seen on the desktop.** An item page open elsewhere notices a
photograph arriving and refreshes itself — see [when it changes while you are
looking at it](#when-it-changes-while-you-are-looking-at-it).

**Photographs and the count of what is photographed.** An item's own photographs
are its portrait; the ones on history entries are not, and `/stats` counts them
separately for that reason — see [section 16](#16-statistics).

**Watermarking.** Your own photographs are stamped with the site logo as they are
served, and so are the ones on history entries; reference images are not. Set `RHDB_WATERMARK=0` to serve everything
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

## 12. Projects

Everything so far has described what is owned. A project describes what is
intended: a repair, a build, a machine wanted and not yet found.

The two are different kinds of statement and are asked different questions. A
Spectrum has a board issue and a ULA; "recap the +2A" has a state, a list of jobs
and a pile of things on order. So a project is a record of its own, at
**projects** in the header, rather than more fields on a machine.

That page has two halves, and most of this section is about the first. The
**projects** are named pieces of work, and they are public. **Wanting work**
below them is a private queue of things you have flagged as needing something —
lighter, quicker, and described further down.

**A project need own nothing.** That is the point of it. The idea comes months
before the hardware — a plan to build a 486 exists long before there is a 486 to
point at — so a project can be written down on the evening it is had, and the
computers and parts attached to it as they turn up. A project with nothing in it
is the ordinary case at the start, not an unfinished one.

Only the name is asked for. It is the only thing a project can be found by: a
machine falls back to its manufacturer and model and then to its asset tag, and a
project has neither.

### The states

| Status | What it means |
|---|---|
| **planned** | Written down, not started. |
| **in progress** | Work has begun. |
| **stalled** | Waiting — on a part, on the weather, on the will. |
| **done** | Finished. |
| **abandoned** | Given up on. |

**stalled** earns its place because it is the true state of most projects most of
the time, and calling that "in progress" would make the in-progress list a lie and
the whole status useless. **abandoned** is kept apart from **done** for the same
reason: a project given up on is not a project finished, and folding the two
together would mean never being able to ask what was actually built.

The list page leads with what is in hand and dims what is over — which is not the
order the status menu offers, because a menu is read in the order a project lives
and a list is read to find out what to do next.

### Three dates

**Started** is when work began, which is not when the project was thought of.
**Wanted by** is a hope rather than a record. **Finished** is when it was done.

None of the three is worked out from another, and any can be blank while the
others are not — a project can be finished without ever having been recorded as
started, because the part turned up and it took an evening.

### What it is about

Add any computer or part in the register. A note beside each says why it is there —
*the patient*, *donor for the keyboard* — which is a fact about the pairing rather
than about either end of it, and so has nowhere else to live.

The same thing can be in two projects: a PSU can be wanted by both, and a machine
being restored can also be the machine a spare board is destined for.

It reads both ways. The project lists what it is about, and **each item's own page
gains a Projects panel** saying what it is spoken for — so you find out a board is
already promised while looking at the board, rather than having to find the project
that promised it. Nothing is drawn on an item that is in no project, which is most
of them.

Taking an item out, or deleting the project altogether, leaves the hardware alone.
Deleting the plan is not disposing of the machine.

### Tasks

A sentence and a tick, and deliberately nothing else. A task list that asks for a
priority, an estimate and an owner is a task list nobody writes anything in.

Outstanding jobs sort above finished ones, because the list is read to find out
what to do next and a long tail of ticked lines between you and it is the thing
that stops task lists being read at all. Ticking one dates it with today; putting
it back clears that date, since a job that is not done has no day it was done on.

### On order

What has been bought for the project, and whether it has turned up.

Each line records what it is, who from, when it was ordered, when it is due, and
what it cost. What is still coming sorts first, soonest first; a line with no
expected date sorts last among them, because it is not due sooner than one that is
due — it is simply not known.

**Nothing becomes a part by arriving.** When the Gotek turns up you add it to the
register the ordinary way and tick the order, which keeps an order a note about a
purchase rather than a half-made asset, and keeps the register a list of things
that exist.

#### What it cost

This is the one place in the whole register that records money.

Everything else here describes what a thing *is*. An order describes a
transaction, and what it cost is most of what there is to say about one. It is
stored as a whole number of pence, for the reason every other quantity in the
database is stored as an integer in a small fixed unit: it adds up and sorts
exactly, which a decimal of pounds does not.

The cost is for **the whole line as paid**, not a unit price — four SIMMs for
twelve pounds is a quantity of 4 and a cost of £12. That is the figure on the
receipt, and dividing it to store a unit price would invent a number nobody
quoted.

Leaving it blank means **not written down**, which is not the same as free. The
total under the table says so: it gives what has been spent and then how many
lines had no figure, because a total quietly counting unpriced lines as zero would
be smaller than the truth and would look exactly as authoritative.

**The costs are private.** Projects are public to read, like the rest of the site
— what is being built is worth reading about — but the cost column and the total
are drawn only for whoever is signed in. A visitor sees what was ordered, who from
and whether it arrived. The JSON API is behind the login in its entirety, so the
figures are not readable there either.

### Its history

A project keeps a history exactly as a computer or a part does, at the foot of its
page: the same note bar, the same photographs hung on entries, the same folding of
a run of identical actions into one line. See [section 14](#14-history) — there is
nothing different to learn.

That is not a coincidence of design so much as the whole of it. A project is given
an asset tag from the same pool the computers and parts draw from, and the history
is keyed by that tag rather than by any one table — so a project could keep a
history without a line of code being written for it.

The history is also written for you as you work: taking an item on, ticking a job,
ordering something and marking it in all leave a dated line. Membership is recorded
on both sides — the project says what it took on, and the machine says what it is
wanted for.

### Wanting work

Below the projects, on the same page, is the other and lighter half: a queue of
computers and parts flagged as needing something done to them.

**A flag and a note**, on the item itself — the same shape `disposed` and
`disposed_note` already have. It is for the thing you have just noticed: a board
that wants a recap, a drive that needs a belt, a machine that would run if it had
a power supply. Flag it in a second from the item's own page, while you are
standing at it, or from the box on the projects page by typing its asset tag —
which is the one you have just remembered rather than the one you are looking at.

Machines and parts sit in one queue, in register order. An afternoon at the bench
goes on whatever is next, and whether the next thing is a computer or the card out
of one is not how anybody chooses.

The note is an editable box wherever it is shown, because a plan is the thing most
often wrong — half of it is done, or the fault turned out to be something else —
and the list is where you are standing when you find that out. Taking something off
the queue takes its note with it: either the work was done, in which case it belongs
in that item's history written in the past tense, or it is not going to be, and a
plan nobody is following is not worth keeping.

A duplicate does not inherit the flag, for the reason it does not inherit the
serial or the disposal: a copy is a record of a second object that nobody has
looked at yet.

#### The queue is private, and the projects are not

This is the one place on the site where two things side by side are read by
different people, so it is worth being plain about which is which.

**A project is public.** It is a piece of work worth reading about, and its page,
its tasks and its orders are all readable by anybody — bar what each thing cost.

**The queue is not.** It is what is wrong with your things, in your own words, and
it is drawn only for a reader who is logged in. That privacy is kept in four
places, not one, because a thing is only private if it is private everywhere it is
written down:

- the routes that set and clear the flag are POSTs, so the login gate has them;
- the panel on an item's own page is inside that page's logged-in block;
- the queue on the projects page is inside one too;
- and the search leaves both columns out for anybody not logged in — the bar, the
  dropdown and the history all read the same set.

**Nothing about the flag is written to the history**, which is the one place the
register's usual habit is deliberately broken. Every other change worth knowing
about lands in the log, but an item's history is shown to whoever opens its page
and is the part of the register nothing rewrites — so a line reading *"flagged as
a future project — recap, one leg already green"* would put the plan on the public
page by the back door, and put it there for good.

The whole API is behind the login, so it carries both columns like any other pair.

### Two sizes of the same idea

The queue and the projects are not rivals, and neither replaces the other.

A flagged item is something **noticed** — one sentence, no ceremony, thirty
seconds. A project is a piece of work **committed to**: it has a name, a state, a
list of jobs and a shopping list against it. Most things stay in the queue for
ever, and that is fine; a few earn a project, and when one does, the queue says so
— each flagged item shows a chip for any project that has taken it on.

Start in the queue. Promote to a project when it turns out to be a piece of work
rather than a note.

### Finding one

Projects are searched by the same words everything else is. Typing in the header
box offers them in the suggestion list alongside the machines, and the match reaches
**the jobs and the things on order as well as the project's own words** — so typing
*Gotek* finds the project with one in the post.

A whole-page search from the header lands on the gallery, which stays a gallery:
projects are not cards there, because that grid is a wall of photographs of things
owned and a plan is not one of those. Instead the line above the results says how
many projects matched and links to them. The projects page has a search box of its
own for sifting without leaving it.

## 13. Labels and QR codes

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
to, see [command-line tools](#20-command-line-tools).

---

## 14. History

Every item has a dated history, and it fills itself in. Creating, editing,
photographing, linking, unlinking, disposing and restoring all write a line
saying what changed.

Detaching a board writes on both sides of the one event: the machine's history
says which tag its board became, and the board's history opens by saying which
machine it came out of, because that is its birth rather than a creation out of
nothing.

**You can add a note** from the box at the top of the History panel — `tested`,
`cleaned`, `recapped`, `bought a replacement PSU for it`. Notes are marked as
notes; everything else is an automatic change record. Photographs go in from the
same box, and neither half needs the other: words on their own, photographs on
their own, or both together.

### Photographs on an entry

**A photograph is an entry in its own right.** Choose one with the **photos**
button in the note box and press **add note** with the box empty: the log gets a
line of its own, marked *photo*, with its own time on it and the pictures in a row
across it. A photograph of the board with the capacitor missing is a thing said
about the board, and it used to need a sentence typing beside it before the
register would keep it at all.

**Or with words, in the one gesture.** Type the note and choose the photographs
together and they stay one entry: the board before the recap with what you did to
it written beside it. There is no caption box, because the entry's own message is
the caption — writing one would be writing the sentence twice.

**An entry already written takes one too**, from the small camera button at the
right of its line — the swap the register logged last week, photographed when the
lid next came off. That upload goes the moment the photograph is picked, the way
the gallery's do. Nothing is written into the history about it, because an entry
gaining or losing a photograph is an edit to the record rather than something that
happened to the machine.

**These are not the item's photographs.** They are not in the gallery, one is
never the item's default picture, they are not counted among the collection's
photographs, and an item whose whole history is photographed still counts as
never photographed on the statistics page. A picture of a repair is not a picture
of the machine. They are kept apart on disk for the same reason, so nothing can
mistake one for the other. Click one to open the original full size, as with any
other photograph here; the big view's toolbar — rotate, crop, delete — is not
offered, because those act on a picture *of* something rather than on a picture of
a moment. The way one of these goes is with the line it belongs to: there is one
trash button a line, at the right, and on a photograph entry that button is the
photographs.

**Deleting an entry.** Each line has a trash button when you are logged in. A
history is written by the register rather than by hand, so it collects lines nobody
wants — a correction made twice, a photograph added and taken off again. Deleting
one takes any photographs hung on it as well, and a folded line takes the whole run
it stands for: a line reading *×10* that removed one of them and came back saying
nine would not be doing what it says.

Nothing is written to the history about the deletion. That is the same rule an
entry gaining or losing a photograph follows — editing the record is not something
that happened to the machine, and a history that logged its own editing would grow
a line for every line it lost.

**A run of the same thing done in one sitting reads as one line.** Ten
photographs deleted one after another is "deleted 10 photographs", not ten
consecutive identical entries. An entry carrying photographs is never folded this
way, in or out: folding rewrites several entries as one sentence, and the
photographs would end up under a line that is not the one they were taken for.

**A visitor sees the date; whoever can edit also sees the time of day.** The
gallery's recency sort keys are trimmed to match, so an anonymous visitor and a
logged-in one see the same ordering rules applied to the precision each of them
is shown.

History is searchable, which is often the point of writing it. Searching
`recapped` finds everything you have recapped.

---

## 15. Disposing, restoring and deleting

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
deleted from disk, the history, and the photographs hung on the history, which
are counted with the rest because they are files and they go too — and asks you
to **paste the item's own URL** into a box. Nothing about that asks the database a question it does not
already know the answer to; the point is that deleting the wrong thing takes a
deliberate act, so a delete cannot be a stray click on a page you landed on by
accident.

Whatever pointed at the deleted item is unlinked first, and keeps a line in its
own history saying why it is suddenly standing alone.

A machine's **disposed** parts can be deleted along with it by ticking a box. Any
part still in the collection is kept whatever the box says.

---

## 16. Statistics

`/stats` is the collection by numbers, and it is public.

- **A headline** — how many things, how many machines, how many parts, how many
  photographs.
- **Portrait coverage** — how many things still here have no photograph of
  themselves, and a link to exactly which ones. This is the one figure on the page
  that is a job rather than a curiosity, so it is always shown rather than being
  dealt into the shuffle below it; see [below](#what-counts-as-a-portrait).
- **Eight things about it** — a pool of a hundred-odd figures nobody strictly
  needs (most and least reliable maker, the longest wait between a thing being
  made and arriving here, what every floppy would hold if each had a disk in it,
  which boards fit nothing but the case they came out of, how many parts nobody
  has written a word about, how many slots would still be empty if every card
  here were plugged in at once), from which the page draws eight at random on
  each visit. The pool is built in themed groups — the boards, the cards, the drives,
  the machines, how old it all is, where it came from, the register itself, and
  what state it is in — but they are shuffled together, and the page does not know
  or care which group a tile came from. It used to hold the coverage figure too;
  that one was promoted out, because a work queue that appears on some visits and
  not others is no use as a work queue, and a figure both fixed and shuffled would
  come up twice on one page. A figure only joins the pool when it has something to
  say, so a young register offers fewer rather than offering blanks, and no two
  tiles in one draw show the same number. Reload to shuffle.
- **Ranked charts** — makers by parts held, what the parts are, expansion buses,
  ports, condition, and makers by how much of their hardware still works.

**Almost every number is a link** to the items it counted, shown in the same grid
as the gallery. That is the point of the page: a figure you cannot get behind is a
figure you cannot check. The handful that are not links are the ones about the
register rather than about the hardware — how many entries have been written, how
many of those were written by hand — because an entry in a history is not an item
the gallery can show, and a link to everything would be a link that lied about
what it counted.

### About the reliability chart

"Reliability" there means one thing: **the share of a maker's parts recorded as
Working.** Not "Restored" — a part that had to be restored is evidence of the
opposite. And only parts still in the register, since a disposed one may have
been sold in perfect working order. A maker needs five parts to qualify;
"Unknown" and "Generic" are not makers. The caption on the page says so, because
a league table whose entry conditions are hidden is an opinion with a bar chart.

### What counts as a portrait

A portrait is a photograph of the object itself, in the object's own folder, named
for its tag — what the item page and the gallery card show. **A photograph on a
history entry is not a portrait.** Those live in a folder of their own, filed under
the entry rather than under the thing, and they answer a different question: an
object with six pictures of its recap and nothing else is still an object nobody
has photographed in the sense this figure means. See [section 10](#10-photographs)
for the difference and [section 14](#14-history) for the history side of it.

The figure and the list behind it are the same question asked once. Both read the
files on disk, which is what the item page draws; the "default photo" recorded
against an item is a note of which file was chosen, not the answer to whether there
is one. Both count only what is still here, so a disposed item is not on the queue
— its record can keep its picture, but nobody can go and take a new one.

### Everything counts what it says it counts

Figures are counted live, from typed columns rather than by reading numbers back
out of text — so a figure on the page is the same figure the database sorts on.
Where a figure adds up quantities rather than counting assets (slots, chips,
drives), the note under the heading says whose they are.

### Traffic

`/traffic`, behind the login, is a GoAccess report built from the proxy's access
logs and rebuilt every five minutes. It covers the last six weeks or so: the
proxy keeps fifteen rolled-over logs behind the live one, and the report is built
from all of them.

---

## 17. Logging in

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

Both doors keep your place. Logging in returns you to the page you were asking
for — which matters most to a phone that has arrived by scanning a label and would
otherwise be handed the gallery and told to find the thing in its hands again — and
logging out leaves you on the page you were reading rather than at the front door.
A search in the address counts as part of where you were. The exception is a page
the login was what let you see: logging out of an edit form leaves you on the item
it was editing, and out of a new form or a delete confirmation, which have no item
behind them, on the gallery.

Editing controls simply do not appear when you are not logged in.

---

## 18. The REST API

Interactive documentation and a console are at `/docs` (login required). The
schema is at `/openapi.json`.

| Method | Path | |
|---|---|---|
| `GET`, `POST` | `/api/computers`, `/api/parts` | list, or create — the server assigns the asset tag |
| `GET`, `PATCH`, `DELETE` | `/api/computers/{id}`, `/api/parts/{id}` | fetch, partial update, delete |
| `GET` | `/api/items/{id}/log` | an item's history, with any photographs on each entry |
| `GET` | `/api/machines` | the catalogue of machines known as models — home computers, consoles, documented branded PCs — and the variations each was built in. Public, like [/machines](#the-list-of-what-it-knows), because none of it is about this register |
| `GET` | `/api/files` | the files kept beside the register |
| `GET`, `POST` | `/api/projects` | list, or start one. `?open=true` for the ones neither finished nor abandoned, `?status=stalled` for one state |
| `GET`, `PATCH`, `DELETE` | `/api/projects/{id}` | fetch (with its items, tasks and orders), partial update, delete |
| `POST`, `DELETE` | `/api/projects/{id}/items`, `/api/projects/{id}/items/{asset_id}` | put a computer or part in a project, or take it out |
| `POST` | `/api/projects/{id}/tasks` | add a job |
| `PATCH`, `DELETE` | `/api/projects/{id}/tasks/{task_id}` | tick, reword or drop one |
| `POST` | `/api/projects/{id}/orders` | record something bought |
| `PATCH`, `DELETE` | `/api/projects/{id}/orders/{order_id}` | mark it in, change it, or cancel it |

`GET /api/parts?computer_id=RH-4K7Q` and `?type=sound` filter the list.

`PATCH` changes only the fields you send.

A catalogue identity is the one nested shape, because it is not a string. Its
`machine` object takes `model_key`, `issue`, `style`, `region` and `chips` (a
`{role: variant}` map). Omitting it leaves the existing identity alone; sending
`null` forgets it. A model key or a chip socket the catalogue does not have is
refused rather than stored.

A part takes one too, and only a motherboard may: it asks for `model_key`,
`issue` and `chips`, and refuses `style` and `region` — those are facts about a
whole machine in a case. Both read back with `variant`, the rendered line, which
is written from the rows and ignored if you send it.

Authenticate with HTTP Basic:

```sh
curl -u user:pass https://db.example.com/api/parts?type=video
```

---

## 19. The tool server

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
- `list_projects` (filter by `status`, or `open=true` for what is still going),
  `get_project`, `create_project`, `update_project`, `delete_project`
- `add_project_item`, `remove_project_item` — what a project is about
- `add_project_task`, `update_project_task` (tick it), `delete_project_task`
- `add_project_order`, `mark_project_order_delivered`, `delete_project_order` —
  `cost_p` is pence as a whole number, and is the cost of the whole line as paid

It stores nothing of its own. Every call is an HTTP request to the API, so the
tool server, the GUI and the command-line tools all work against the same
database and obey the same rules. `create_*` assigns the next asset tag;
`update_*` changes only the fields you pass.

---

## 20. Command-line tools

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


### Photographs, and how big they are served

You upload a photograph at whatever size your phone took it — several megabytes,
three to five thousand pixels across — and that is what is kept. It is never
resized, cropped or thrown away in the name of space.

What is *served* is a copy no bigger than the place it is going. A gallery card
gets a 400-pixel copy (800 on a retina screen), an item page's main photograph
1200. Those copies are made the first time they are asked for and kept beside the
originals, and rebuilt whenever the photograph behind them changes. Opening a
photograph full size — clicking it, or the lightbox — always gives you the
original, because reading the markings on a chip is what a 24-megapixel photograph
of a board is *for*.

To make the copies up front rather than making the next visitor wait for them
(worth doing after a deploy, and after any bulk import):

```sh
docker compose exec api python -m app.thumbs
```

The copies live in a dot-directory under `images/` and are excluded from backups,
since they can always be made again from the originals.

### adopt_machines.py

Goes through the machines that have **no catalogue model** and proposes one for
each, from what is typed in their manufacturer and model boxes. It writes nothing
until you pick a match by number.

```sh
python tools/adopt_machines.py             # go through them, asking
python tools/adopt_machines.py --list      # the report only; writes nothing
python tools/adopt_machines.py RH-4K7Q     # just this one
```

Confirming writes **one field**: the model key. Not the manufacturer, not the
model, not the year, not the CPU — the machine in front of you is the authority on
those and the catalogue is a starting point. Where the two disagree, the
disagreement is printed and the record is left exactly as it is: two IBM 5170s in
this register are dated 1985 and 1988, the catalogue says the AT came out in
1984, and all three are true of something.

A machine the catalogue does not know is left uncatalogued, which is a correct
state and not a failure. Disposed machines and bare boards are left out — a board
is filed by reading it, not by matching a name.

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

## 21. Housekeeping

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
