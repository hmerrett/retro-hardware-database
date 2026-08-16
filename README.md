# Retro Hardware Database

A catalogue for a collection of old computers and the parts they are built from.

Every machine, card, drive and chip gets an asset tag (`RH-4K7Q`), a page of its
own, photographs, and a dated history of everything that has happened to it. You
print a small label with a QR code, stick it on the thing, and scanning that code
opens its page.

The live instance is <https://db.2600.me>. Browsing is public; editing needs a
login.

## What it is for

Two kinds of object, catalogued in two different ways, because they are two
different kinds of object:

- **A PC is described by what is fitted in it.** A 486 tower is a motherboard, a
  video card, a sound card, a hard disk and so on — each one tagged, photographed
  and recorded in its own right, and linked to the machine it lives in. Pull the
  card out and put it on a shelf, and its record follows it.
- **A home computer or a console is described by which version of itself it is.**
  A ZX Spectrum is a sealed machine, and what identifies one is its board issue,
  its case, the region it was sold in and the part numbers in its chip sockets —
  not a pile of tagged components. Nobody shelves a ULA on its own.

The database does both. It knows about three hundred home machines and consoles
— Britain, Europe, America and Japan, from the Altair to the Neo Geo — and the
documented variations each was built in, so filing a machine against one of them
fills in what is already known and asks only about what varies. The catalogue is a
single YAML file with instructions at the top of it, so adding the machines your
collection has needs a text editor and nothing else.

## What you get

- **A gallery** of every item, as photo cards you can sort, filter and search.
- **A page per item** with its details, its specs, its photographs, the files
  kept beside it and its full history.
- **Search** that reads every field of every item *and* its history, from a box
  in the banner that works on every page.
- **Photographs** uploaded from a phone (scan the item's QR code, take the
  picture), with rotate, crop and a chosen default image.
- **Printable labels** as PDFs, in a full size and a small one, each carrying a
  QR code back to the item.
- **Files** kept beside the register — a driver disk, a manual, a ROM dump —
  tagged with the hardware they are for, so every matching item offers them.
- **A history** of every change, plus free-text notes, dated.
- **Disposal** that keeps the record when the thing itself is gone, and a
  separate, deliberate delete for records that should never have existed.
- **Statistics** at `/stats`: totals, ranked charts, and a rotating pool of
  figures nobody needs.
- **A JSON REST API** and a **command-line toolkit**, so labels can be printed
  from the machine with the label printer attached and reports can be imported
  from boot disks.

## Running it

It is a Docker Compose stack — a web app, a MariaDB database, a reverse proxy
that gets its own HTTPS certificate, and two helpers. To try it on your own
machine:

```sh
cp .env.example .env      # then edit the passwords in it
docker compose up --build
```

The site is then at <http://localhost:8000>.

To run it properly, on your own server, with your own collection in it, see
**[INSTALL.md](INSTALL.md)**.

## Learning it

**[MANUAL.md](MANUAL.md)** is the full manual: what every field means, how each
feature works, the REST API, and the command-line tools.

**[DEPLOY.md](DEPLOY.md)** is the runbook for the db.2600.me box specifically —
how to ship a change to the live site.

## How it is built

```
docker compose
├── caddy     reverse proxy, automatic HTTPS      (ports 80 and 443)
├── db        MariaDB 11                          (volume: dbdata)
├── api       FastAPI + uvicorn                   (127.0.0.1:8000)
│             the web GUI, the JSON API and the photos
├── mcp       tool server over the REST API       (127.0.0.1:8001)
└── goaccess  traffic report, rebuilt every minute
```

Only Caddy is exposed to the internet. Everything else listens on localhost and
is reached through it.

The app is Python: FastAPI, SQLAlchemy, Alembic for migrations, and Jinja
templates rendered on the server. The pages use a little plain JavaScript and no
framework. Specifications are stored in typed columns rather than as free text,
so "every board with a VLB slot" is a question the database can answer.

## Development

```sh
python3 -m venv .venv-test
.venv-test/bin/pip install -r api/requirements.txt -r api/requirements-dev.txt
.venv-test/bin/pytest
.venv-test/bin/ruff check .
```

The tests run the whole app against a throwaway SQLite database. Both the tests
and the linter run in CI on every push and pull request.

To run the app directly, without Docker:

```sh
cd api && pip install -r requirements.txt
DATABASE_URL=sqlite:///dev.db uvicorn app.main:app --reload
```

## Licence and credits

The label display font is Audiowide (SIL Open Font License; see
`tools/assets/fonts/OFL.txt`).
