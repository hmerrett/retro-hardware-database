# Changelog

What changed, newest first, written for somebody who runs this rather than
somebody reading the diff. A line goes in when an installation would notice it: a
new feature, a change to how something already works, a fix, or a step an upgrade
has to take by hand. Work with no outward face — a router extraction, a lockfile,
a test — stays in the git history, which is where it is useful.

Versions are [semantic](https://semver.org), and the version has one home,
`api/app/__init__.py`. Upgrading is `./deploy.sh`: migrations run as the app
starts, so a schema change needs no step of its own. Anything that does need a
hand is written under the release that needs it.

## Unreleased

**A location's label follows its list.** What's on it now decides a location's label
as it does a machine's. Tag is its tag, Name its name, and Where it's kept the path
of the locations it is inside. On a full label, Specifications are its kind and
notes. Nothing ticked prints the code alone, and the word up the end prints only
when ticked.

**Upgrading:** a location's label used to print its name largest, its path above
and its tag below, whatever the list said. With the starting ticks it now prints its
tag largest, then its name, and no path. To keep the old look, set up a label for
locations with Name first, then Where it's kept, then Tag.

**A crowded label makes room before it leaves anything off.** When the ticked
details need more lines than a small label has room for, its type comes down until
they fit, as far as the 51×19 mm tape's own size. Only past that are the last ones
left off. Under each label's picture in Settings → Labels, a line now names
anything still left off: *No room for Serial number, and only part of
Specifications*. Labels with room to spare print exactly as before.

**Words no longer run into a label's barcode.** On a small label carrying a
barcode, the tail of a p or a g in the line just over the bars reached into them.
The words now keep clear of the bars, which can cost a crowded label a little type
size or its last line.

**Two more DYMO LabelWriter labels.** A label's Stock, and a print agent's, can
now be the 89×36 mm large address labels (99012) or the 70×54 mm multipurpose labels
(99015), named `dymo-99012` and `dymo-99015`. Both are laid out as small labels.

**Each label is pictured as it is set up.** Beside each label's settings on
Settings → Labels is a picture of it as it prints. It is redrawn as the settings
change, before they are saved: tick a detail, move one, change the code, the stock
or the face, and the picture shows what that does. It is drawn for an example
rather than anything in the collection. A menu under it makes the example a
machine, a part, a project or a location, and the picture is on the stock the
label goes to.

**Each of the two labels is set up for its own job.** Settings → Labels has a
group for each label: its name, which is what its print button says; its code,
now including **None** for a label of words alone; where it goes; the stock its
PDF is drawn on; what is printed on it and in what order; and its face. The full
label can go to a print agent or a Niimbot as the small one could, and *This
browser* chooses for each. The stock decides a label's shape: on a 6×4 sheet it is
laid out as a full label, and on anything smaller as a small one, whichever label
it is. An installation that changes nothing prints exactly the labels it always
has, with one exception: a part, project or location sent to a print agent loaded
with 6×4 sheets now gets the full layout rather than the small one enlarged. The
print queue's API takes an optional `label`, `small` or `full`.

**Upgrading** carries your label settings across: the codes and the face you had
go to both labels, and where the small label went goes to the first. Nothing else
needs doing.

**The Label panel shows the label.** Above an item's two print buttons is a
picture of the small label as it will print, on every machine, part, project and
location. It is drawn for the printer the small button sends to: the 51×19 mm
tape for a PDF, the size the Bluetooth printer is loaded with, or a print agent's
own stock, and a browser that has chosen a printer of its own sees that one's. It
is the label the printer is sent, dot for dot, so a name cut short to fit is seen
on the screen rather than on the sticker.

**A signed-in browser no longer meets an occasional server error.** When a browser
was last seen is written at most every five minutes, by whichever request finds it
out of date. After a quiet spell, requests that arrive together — an item page
checking whether its record has changed asks as its tab comes back into view and
again as the window takes focus — each found it out of date, and on MariaDB 11.8
all but the first to write it were refused and failed with a server error. Writing
the time is bookkeeping, and the first request has done it, so the refusal is now
let go and the request carries on signed in. Any other database error is still an
error.

**The database is pinned to MariaDB 11.8.** `docker-compose.yml` asked for
`mariadb:11`, which is whichever 11 is newest. That became 11.8, which refuses a
write to a record that another request has changed since this one began reading
it, and that refusal is what the error above was. It stays on: when two requests
change one record at the same moment, the second failing is better than its
quietly undoing the first. A newer engine is now taken by changing the tag in
`docker-compose.yml`, once you have read what it changes.

**Upgrading** recreates the database container on the pinned image. Before you
deploy, `docker compose exec db mariadb --version` says which you have. On 11.8
already, nothing else changes. On an older 11, this release moves the database to
11.8: take a backup first (`tools/backup.sh`), and once it is up, bring MariaDB's
own tables up to the new version, once. The register's data needs nothing.

```sh
docker compose exec -e MYSQL_PWD="$DB_ROOT_PASSWORD" db mariadb-upgrade -uroot
```

**A machine is a place things are in, as a box is.** Where everything is, is now
one tree: a part is fitted in a machine, mounted on another part, or kept in a
location — never two at once — and moving anything moves what is inside it. Fitting
a card and taking it out are moves, recorded like any other, so a card's history
says which machines it has been in. A drive on a controller card counts as in the
machine everywhere: its page, the gallery, the search and the figures.

- **Deleting** a machine or a part deletes everything inside it, all the way down,
  and the confirmation page lists it all. Deleting a location deletes nothing in
  it: what was there is left nowhere. A deleted thing's tag is never issued again.
- **Disposing of** a part disposes of what is mounted on it, as a machine always
  has. Nothing can be put inside something disposed of.
- **Visible**, a tick beside each item's Location, decides whether a visitor is
  told where that one is kept. **Show locations** now decides how a new item's tick
  starts, and still whether visitors can open location pages. The upgrade ticks
  every item as the switch is set today, so nothing a visitor sees changes.
- **The audit is simpler.** Scan a location or a machine, then everything in it,
  and press **next** before the next place. Scanning a box onto a shelf moves it, so
  the moving-boxes switch has gone, and so has holding a thing until a location is
  scanned. Scanning parts into a machine fits them.

**Upgrading** settles anything the register held two answers for. A part that was
fitted in a machine and also given a location of its own stays in the machine, and
its history says the location was dropped. A part still in the collection inside a
machine that has been disposed of is disposed of with it, on the same date and for
the same reason, so restoring the machine brings it back. See [Where it is
kept](MANUAL.md#where-it-is-kept) and [Audit](MANUAL.md#audit).

**A part can no longer be mounted on itself.** The API, and the **mount** menu on
a card sitting on a loose drive, would mount a part on itself or on something
mounted on it, and the two pages then each said the other was what it was on. That
is refused now wherever it is asked for, with the reason, and the menu leaves such
parts out. See [Two tables](MANUAL.md#two-tables).

**Read a README without saving it.** A Markdown file and a plain text file have a
**View** button, as a PDF does: `.md`, `.txt`, `.nfo`, `.diz`, `READ.ME`,
`README.1ST`, the `.bat`, `.ini` and `.cfg` files a machine is set up with, and
`CONFIG.SYS`. It opens the file as a page of the register, in the look you have
chosen, light or dark: Markdown's headings, lists, tables and code set the way the
site sets its own, and a plain text file exactly as it was typed, its DOS box
drawing and accents included. Nothing in a file runs or is fetched: HTML in it is
shown as text, and a picture as its description. See [Reading a text
file](MANUAL.md#reading-a-text-file).

**Scan is in the side rail.** With the rail showing, **Scan** sits under the
sections, as it sits among the buttons in a phone's bar, and the banner beside the
rail holds the search box alone. A tablet, a narrower window and the *Top* layout
keep it beside the search box. It now appears only where the browser lists a
camera, so a desktop with none is no longer offered a button that could only say
so. See [Scanning a label](MANUAL.md#scanning-a-label).

**Locations are records, with labels you can scan.** Where a thing is kept is now a
location -- a building, a room, a rack, a shelf, a box, a bag -- with an asset tag
of its own, a page, photographs, notes on how to find it, and a label. Locations sit
inside other locations, and moving a box moves everything in it. The Location box on
a machine or a part offers every location by its path, and a new name makes one.
**Upgrading converts what you typed:** every different spelling becomes a location
of its own at the top level, so give them their places afterwards -- on each
location's page, or by scanning -- and put two spellings of one crate together with
**merge into**. *Remember old locations* has gone: a location stays when it is
emptied, so there is nothing left to remember. See [section 14](MANUAL.md#14-storage).

**Audit.** **☰ → Audit** is a screen for a phone and a handheld barcode
scanner, or the phone's camera: it asks which, then says in large type what to do
next -- *Scan a location*, then *Scan things into Shelf 2* -- and every scan moves
things there and then: found, moved in, or refused, said in words, colour and a
beep. There is no box to type into; a scan goes as soon as a whole tag is in, with
or without Enter. A round ends with a report of what was found, what moved in, what
was not scanned and what was not recognised. Any USB, Bluetooth or OTG scanner
works, as a keyboard.

**Barcodes.** **Settings → Labels → Codes** puts a QR code, a Code 128 barcode
holding the tag alone, or both on every label, and **Type** can set a label's words
in the site's own face. The bars are a whole number of the printer's dots in the
PDF as well as the picture, never narrower than a quarter of a millimetre, with
nothing printed under them; on the 51×19 mm tape they run the label's width, and a
label set to both carries the barcode alone there. Every move is now in the
history, with who made it and how.

**The side rail adds what + New does.** **Project** and **Location** are one press
each there now, under **Computer** and **Part**.

**Locations is a section**, beside Browse and Projects: every location on one page,
each under the one it is inside, with its kind, its tag and how much it holds. It is
where the spellings the upgrade made into locations are found, to be put in their
places. A visitor is offered it only while **Show locations** is on. With six
sections, the banner folds them into **☰** below 1000px rather than 900px.

**The footer has gone.** The collection's name is in the banner, a phone's
included, and at the top of the side rail; the API docs are on **⋯ → Account**,
beside your tokens.

**The logo is read out once.** A screen reader heard the collection's name twice
at the logo — once for the picture and once for the words beside it — and hears
it once now, in the banner and on the rail.

**Accounts: administrators and viewers.** The login is no longer one username and
password in `.env`. Accounts live in the database, each an **administrator** or a
**viewer** — somebody who reads everything a visitor is not shown (unpublished
files, private projects, locations, the for-sale list, what an order cost) and
changes nothing. Accounts and API tokens are managed with
`docker compose exec api python -m app.accounts`. A new installation opens on
**Set up**, which wants a code the app writes to its log.

**Accounts are managed in the browser.** **Settings → Accounts** lists everybody
who may sign in, adds people, and changes a role, a password or whether an account
is switched on. **Account**, in the menu, is where anybody signed in — a viewer
too — changes their own password, signs out their other browsers and makes their
own API tokens. The command line still does all of it.

**A site can be closed to visitors.** **Visitors must log in**, in the settings,
shows anybody not signed in the login page and nothing else. It is off.

**API tokens.** The API takes `Authorization: Bearer rhdb_…`, a token per program
that acts as its account and can be revoked on its own. HTTP Basic with an
account's password still works.

*Upgrading:* nothing to do on the day. The first start makes an administrator
from `RHDB_AUTH_USER` and `RHDB_AUTH_PASSWORD`, so you sign in as before. Then make
the tool server a token (`python -m app.accounts token <you> "tool server"`), put
it in `.env` as `RHDB_API_TOKEN`, restart `mcp`, and delete the old pair along
with `RHDB_SECRET_KEY`, which signs nothing now. `RHDB_OPEN` is gone: an
installation that ran open opens on Set up, and the code is in
`docker compose logs api`.

**The Ports letters are back under the box.** An I/O card's and a sound card's
**Ports** box shows the letters it takes — I IDE, F Floppy, S Serial and the rest —
which went into a tooltip with the other hints and so vanished on a phone.

**A file is linked to the things it is for by their asset tags, and tags are
gone.** A file can be linked to as many machines, parts and projects as it needs,
and each shows the files linked to it. Uploading on a card offers the other cards
of the same model as one tick, and a card that arrives later is offered the files
its siblings have, but nothing is linked by a name any more: renaming a thing or
correcting its model moves no files. Every file has a page of its own, where its
note, its **Public** tick and its links are changed, and the lists are read-only
rows with a drawing of what each file is — a 3½″ floppy for a 1.44M disk image, a
chip for a ROM. The upgrade links each file that was attached to a model to every
item of that model, and keeps any tag that said more than the model's name in the
file's note. `/api/files` no longer returns `tags` or `models`, or takes `tag`.

**A PDF opens in the browser.** Its row and its page have a **view** button that
shows it in the browser's own viewer rather than saving it. Only a file that really
is a PDF is shown; everything else is still a download.

**New files can start public.** **New files are public** in the settings starts
the upload's **Public** tick ticked, for an installation that mostly files drivers
and manuals. It is off, and a private project's uploads start unticked either way.

**Quieter pages: shorter labels, explanations in tooltips.** The sentences that
sat under boxes on the item pages, the forms and the project pages -- what
disposing a machine does to its parts, where an uploaded file will be attached,
what the project menu will do -- are now the tooltip on the box they explain,
following the interface-text rule, and the labels are shorter ("new project"
for "a project of its own", "dispose" for "mark disposed", "add" for "note
it"). A machine's **Parts** panel has one **add part** button in place of one
per kind, since the form it opens asks the type first. The date column of an
item's history is only as wide as the date, which gives the entries back most
of a phone's width.

**The off-site backup now includes the uploaded files.** `backup/pull-backup.sh`
collected the database and the photographs but not the files volume, so the
drivers, manuals and receipts kept beside the register had no copy anywhere but
the server itself. It now rsyncs that volume the way it already did the photos,
`check` proves it is reachable, and a restore hands back `stage/files/` alongside
the rest. An installation running the puller picks this up by rebuilding it on
the machine that holds the backup: `cd backup && docker compose build && docker
compose up -d`.

**Every machine and every part can say where it is kept.** A free-text
**Location** box on both forms — `Loft, blue crate 3`, `Garage shelf B`, `on the
bench` — offering back the places you have already used, so one crate ends up
spelt one way. A part fitted in something need not be answered at all: left blank
it shows where that thing is kept, and follows it when it moves. A duplicate does
not carry a location across.

Two switches on the settings page go with it. **Show locations** is off, so a
visitor is not told where anything is kept — the row is not on their page and
their search does not match on it. **Remember old locations** is on, and keeps a
place on the pick list after the last thing in it has moved out; turning it off
deletes what has been remembered rather than hiding it, and turning it back on
starts again from what is in use.

**Labels can be printed on a printer that is not attached to the machine you are
holding.** Two things arrive together. A label is now also a picture of itself at
`label.png`, drawn at the size and resolution of a particular printer rather than
as a page to be scaled onto one — which is what a small thermal printer takes, and
what keeps a QR code's squares square. And the register keeps a print queue: send
a label to a named printer, and a small agent on the machine that printer is
plugged into picks it up within a few seconds and prints it.

The agent opens every connection, so nothing has to be forwarded to the machine in
the workshop and no port is opened on your home network — the register can be a
server on the internet while the printer is on a desk behind a router. Each agent
holds its own key, which opens that agent's queue and nothing else.

To use it: name your printers in `RHDB_PRINT_AGENTS` in `.env` (the format is in
`.env.example` and the manual), then run `tools/print_agent.py` on the machine the
printer is plugged into — Python 3 and CUPS, nothing to install.
`tools/print-agent.service` is a systemd unit for leaving it running. Nothing has
to be done by an installation that prints from the browser: with no agents named
there is no queue, and the existing buttons are unchanged.

**A settings page**, at ⋯ → Settings, behind the login. Four things to start
with, in two groups. *Appearance*: what this collection is called — which reaches
the banner, the browser's tab and the preview a shared link unfolds into — whether
photographs are watermarked, and which theme the site opens in. *Local server
options*: whether to block search engines. The ⋯ menu's theme button is
unchanged, and still overrules the default for the browser it is pressed in.

Nothing has to be done to get it: every setting has the value the software
already behaved as though it had, so an installation that opens the page and
changes nothing is the installation it was before. `RHDB_WATERMARK` goes on
working, and pins that one setting — the page shows the value, says which
variable holds it, and leaves it alone.

**`DATABASE_URL` is now required, rather than defaulting.** It used to fall back
to `mysql+pymysql://retro:retro@db:3306/retro` when unset. Under Docker Compose
nobody ever met that default — `DB_PASSWORD` is `${VAR:?message}`, so a missing
value stops the stack long before the app starts — but nothing outside Compose
has that guard. Started any other way, an unset variable did not fail: the app
quietly tried a guessable password on a host called `db`. It now refuses to start
and says how to set it.

**If you run the supplied `docker-compose.yml`, this changes nothing for you.**
If you run the app another way — Kubernetes, or by hand — and were relying on the
default, set `DATABASE_URL` explicitly before upgrading.

## 0.1.0 — 2026-09-18

The first release, and so not a list of changes: there is nothing before it to
have changed from. What it is, in one paragraph, is a self-hosted register for a
collection of old computers — every machine, card, drive and chip with an asset
tag, a page, photographs, files and a dated history; a QR label you print and
stick on the thing; browsing public and editing behind one login; a JSON API and
a command-line toolkit beside the web pages. [README.md](README.md) says what it
is for, [MANUAL.md](MANUAL.md) what every part of it does, and
[INSTALL.md](INSTALL.md) how to run your own.

[ROADMAP.md](ROADMAP.md) has what comes after it.

**Installing it for the first time:** follow [INSTALL.md](INSTALL.md) from the
top. Set `RHDB_BASE_URL` before printing any labels — it is what their QR codes
encode — and set `RHDB_AUTH_USER` and `RHDB_AUTH_PASSWORD`, or the site is
world-editable and says so on every page.
