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
the banner, the browser's tab, the foot of every page and the preview a shared
link unfolds into — whether photographs are watermarked, and which theme the site
opens in. *Local server options*: whether to block search engines. The ⋯ menu's
theme button is unchanged, and still overrules the default for the browser it is
pressed in.

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
