# Installing the Retro Hardware Database on your own server

This is the guide for running your own copy, with your own collection in it, on
your own hostname. It assumes you can use a shell and a text editor; it does not
assume you know Docker, FastAPI or MariaDB.

If you just want to poke at it on your laptop, skip to
[Trying it locally](#trying-it-locally) at the end.

---

## 1. What you need

- **A machine to run it on.** Any Linux box will do. The smallest cloud instances
  are fine — a collection of a few hundred items with photographs is a couple of
  hundred megabytes. 1 GB of RAM is enough; 2 GB is comfortable.
- **Docker and the Compose plugin.** Everything runs in containers, so nothing
  else needs installing: no Python, no database, no web server.
- **A domain name** you can add a DNS record to, if you want it on the internet
  with HTTPS. Not needed for a machine on your own network.
- **Ports 80 and 443** reachable from the internet, for the same reason.

Install Docker if it is not already there:

```sh
curl -fsSL https://get.docker.com | sh
```

On a cloud image you are usually a non-root user, and the installer leaves the
Docker socket owned by root. Add yourself to the `docker` group, or every command
below fails with `permission denied ... /var/run/docker.sock`:

```sh
sudo usermod -aG docker $USER
```

Then **log out and back in** — group membership is granted at login, so the
session you ran that in still does not have it.

Check it works:

```sh
docker ps
```

An empty table is the right answer. Check `docker ps`, not `docker compose
version`: the version is printed by the command-line tool alone and succeeds
whether or not you can reach the daemon, so it tells you nothing about the step
that actually matters.

## 2. Get the code

```sh
git clone https://github.com/hmerrett/retro-hardware-database.git
cd retro-hardware-database
```

Any directory will do.

Your hostname, your credentials and your logo all live outside the repo — in
`.env`, in `caddy/conf.d/` and in `branding/`, none of which are in git — so
pulling an update never fights with them, and you do not need a fork of your own
to keep them.

## 3. Configure it

All the configuration is in one file, `.env`, which is deliberately **not** in
git — it holds your passwords and lives only on your server.

```sh
cp .env.example .env
```

Now edit `.env`. Every setting, and what it does:

| Setting | What it is |
|---|---|
| `DB_NAME` | The database name. `retro` is fine; you never type it again. |
| `DB_USER` | The database user the app connects as. `retro` is fine. |
| `DB_PASSWORD` | That user's password. **Change it.** |
| `DB_ROOT_PASSWORD` | The database's root password, used by the backup script. **Change it.** |
| `RHDB_AUTH_USER` | The username you log in to the site with. |
| `RHDB_AUTH_PASSWORD` | Its password. **Set both, or the site is world-editable.** |
| `RHDB_SECRET_KEY` | Signs your browser login cookie. Generate one with `openssl rand -hex 32`. |
| `RHDB_DOMAIN` | The name this site answers to, e.g. `db.example.com`. Caddy serves it and gets its certificate. |
| `RHDB_ACME_EMAIL` | Where Let's Encrypt writes about those certificates. |
| `RHDB_BASE_URL` | The public URL of your site. Defaults to `https://$RHDB_DOMAIN`; set it only if they differ. |
| `RHDB_WATERMARK` | `1` to stamp your own photos with your site logo as they are served, `0` to serve them untouched. The logo is whatever is in `branding/`, or the shipped placeholder. |

Two of these matter more than they look:

- **`RHDB_BASE_URL` is what the QR codes on your printed labels encode.** Get it
  right *before* you print any labels, or every label points at the wrong site.
  It is also what link previews and the sitemap use.
- **`RHDB_AUTH_USER` / `RHDB_AUTH_PASSWORD` are the whole login.** There is one
  account, not a user table. Leaving both blank runs the site with no
  authentication at all, which is only sensible on a laptop. Anyone reaching the
  site could then edit and delete records.

There is no separate database setup step. The database container creates the
database and the user from these values the first time it starts, and the app
brings the schema up to date with Alembic before it serves anything — on a new
install that means running every migration from empty.

## 4. Set your hostname

Nothing to edit: `caddy/Caddyfile` serves whatever `.env` says, so the two lines
you already set are the whole of it.

```sh
RHDB_DOMAIN=db.example.com          # the name this site answers to
RHDB_ACME_EMAIL=you@example.com     # Let's Encrypt writes here about certificates
```

Caddy gets a certificate for that name and renews it, and the app takes
`https://$RHDB_DOMAIN` as its public address unless `RHDB_BASE_URL` says otherwise
— which is what the QR codes on your printed labels encode, so it is worth getting
right before you print any.

If you want other names as well — a bare domain redirecting to the www, or the
address the collection used to live at — put a block in `caddy/conf.d/*.caddy`,
which is imported and is not in git. See `caddy/conf.d/README.md` for the shape of
one.

Then point DNS at the box: an **A record** for `db.example.com` at your server's
IPv4 address (and an AAAA record if it has IPv6). Caddy fetches its certificate
over HTTP from wherever the name resolves, so this has to be in place, and
propagated, before the certificate can be issued.

Open the firewall for ports 80 and 443. On a cloud provider that usually means a
security group or firewall rule in their console as well as on the box itself.

## 5. Start it

```sh
docker compose up -d --build
```

The first run pulls the base images, builds the app, starts MariaDB, and creates
the schema. Give it a minute, then:

```sh
docker compose ps                    # everything should say "running"
docker compose logs -f api           # the app's own log
curl -I https://db.example.com/      # should return 200
```

If HTTPS is not working yet, `docker compose logs caddy` says why. The usual
answers are that DNS has not propagated (`NXDOMAIN`), that the name still points
somewhere else (`Connection refused` at an address that is not yours), or that
port 80 is blocked. Fix the cause and then force a retry:

```sh
docker compose up -d --force-recreate caddy
```

Do not do that in a loop while you wait — Let's Encrypt rate-limits failed
validations, and Caddy's own backoff exists to stay under that limit.

## 6. Log in and put something in it

Open your site. You will see an empty gallery. Click **log in** in the header and
use the `RHDB_AUTH_USER` / `RHDB_AUTH_PASSWORD` you set.

Two buttons appear in the header once you are logged in: **+ Computer** and
**+ Part**. The [manual](MANUAL.md) walks through both forms field by field, but
the short version is:

1. **Add a machine first.** If it is a home computer or a console, pick it from
   the machine menu at the top of the form — that fills in the manufacturer,
   model, year, CPU and case for you, and puts the right board issues, styles,
   regions and chip sockets on screen. If it is a PC, leave that menu alone and
   describe it in the boxes.
2. **Then add what is fitted in it.** The machine's page has an "Add" row —
   motherboard, storage, video, sound, network, I/O, CPU, RAM, display,
   peripheral. Each part gets its own asset tag and its own page.
3. **Photograph it from your phone.** Every item page ends in a QR code of its
   own URL while you are logged in. Scan it with your phone, log in there once,
   and the photo buttons on that page shoot straight from the camera.
4. **Print a label.** The printer icons at the top of an item page give you a
   full-size and a small label PDF. Or use the command-line tool (below) if you
   have a label printer attached to a different machine.

Asset tags are allocated for you: `RH-` followed by four characters, avoiding
I, L and O so nothing is ambiguous when you read a label back.

### Importing a collection you already have

There is no bulk import command. If you are coming from a spreadsheet, the
practical route is the REST API — `POST /api/computers` and `POST /api/parts`
create records, the server assigns the asset tag, and the interactive console at
`/docs` shows you the exact shape of each request. A short script that walks your
spreadsheet and posts a row at a time is usually an hour's work, and gives you a
chance to normalise the data as it goes.

## 7. Back it up

Your data lives in Docker named volumes, not in the image, so rebuilding and
upgrading never touch it. But volumes live on one disk on one machine, so:

```sh
tools/backup.sh
```

writes three timestamped files into `./backups`:

- `db-<stamp>.sql.gz` — the whole database
- `images-<stamp>.tgz` — the uploaded photographs
- `files-<stamp>.tgz` — the drivers, manuals and receipts kept beside the register

Set `RHDB_BACKUP_DIR` to write them somewhere else. **Copy them off the host** —
a backup on the same disk as the thing it backs up is not a backup. A nightly
cron entry and an `rsync` or `rclone` to somewhere else is enough:

```cron
17 3 * * * cd /root/retro-hardware-database && ./tools/backup.sh >> /var/log/rhdb-backup.log 2>&1
```

Keep a copy of `.env` too. It is configuration rather than data, so the backup
script does not include it, but restoring without it means restoring with
different passwords than the dump expects.

To restore one, with the stack running:

```sh
tools/restore.sh <stamp>
```

`<stamp>` is the part of the file names after `db-`. It checks the three files are
whole before touching anything, asks before it replaces the database, and then
checks what landed: every table's row count and the schema version against the
dump, every photograph and file at the size it was archived at, and the site
answering. The steps it runs are in the header of `tools/backup.sh` if you would
rather do them by hand.

**Try it once before you need it.** A backup nobody has restored is a hope. A
second stack beside the real one costs nothing and touches nothing:

```sh
docker compose -p restore-test up -d api
COMPOSE_PROJECT_NAME=restore-test tools/restore.sh <stamp>
docker compose -p restore-test down -v
```

The test stack wants port 8000, which the real one holds, so stop the real `api`
first (`docker compose stop api`) and start it again afterwards, or use a compose
override that publishes the test stack's app on another port.

## 8. Keeping it up to date

```sh
git pull --ff-only
docker compose up -d --build
docker image prune -f
```

`./deploy.sh` does exactly those three things and then tails the app log.

Schema changes ship with the code: the app container runs `alembic upgrade head`
before it starts, so a `docker compose up -d --build` is the whole upgrade. There
is no separate migration step to remember.

Two things do **not** update that way:

- **`caddy/Caddyfile`.** It is mounted into the container as a single file, so
  Compose sees nothing changed and leaves Caddy running the old config without
  saying so. Use `docker compose up -d --force-recreate caddy`, then check it
  took with `docker compose exec caddy cat /etc/caddy/Caddyfile`.
- **`.env`.** It is read when a container is created. After editing it, run
  `docker compose up -d` to recreate the containers that use it.

To roll back a bad release:

```sh
git log --oneline -n 10
git checkout <last good sha>
docker compose up -d --build
```

The database is not rolled back with it. If a migration was the problem,
`docker compose exec api alembic downgrade -1`.

## 9. Making it yours

### The logo and icons

What ships is a placeholder — a beige machine with a bare prompt on its screen,
which says "retro hardware" and nothing about whose collection this is. Your own
artwork goes in the **`branding/`** directory, which is not in git: a file there is
served in place of the one that ships under the same name, so an update never
overwrites your logo and your logo never shows up in a pull request.

Everything branded comes from one master image. Drop yours in as
`branding/app-icon.png` (transparent PNG, roughly square), then build the set:

```sh
docker run --rm -v "$PWD/branding:/static" -v "$PWD/tools:/tools" \
  retro-hardware-database-api python /tools/make_icons.py
docker compose up -d --force-recreate api
```

That writes the favicons, the app icons, the header logo, the photo watermark and
the card a shared link previews as — all into `branding/`. Replace any of them by
hand instead if you would rather; `branding/README.md` says what each one is.
(Anywhere with Pillow installed, `RHDB_STATIC=branding python3
tools/make_icons.py` does the same without Docker.)

The restart is the only step that matters: the version stamps are hashes of the
artwork, read once at start-up. Nothing needs cache-clearing beyond that — the
marker in the page head follows the icon's hash, and the watermark cache directory
is named partly after the mark's, so photographs already served are re-marked
rather than keeping the old logo.

### The machine catalogue

The list of home machines and consoles — families, models, board issues, styles,
regions, chip sockets and the part numbers seen in them — is one YAML file,
`api/app/machines.yaml`, with the instructions for editing it written at the top
of the file. It needs no programming: copy the model above the one you want, and
correct the values.

The shipped catalogue is a little over three hundred machines from seventy-odd
makers in Britain, Europe, America and Japan. If your collection is Eastern Bloc clones, Australian
or Brazilian machines, or anything else it does not cover, that is the file to
add them to. A mistake in it stops the API from starting rather than being
half-loaded, and the error names the family, the model and the field — so if the
container will not come up after an edit, read the log:

```sh
docker compose logs api | tail -20
```

Only the slugs are stored against a machine; every name, year, CPU and list is
read from the catalogue on every page load. So correcting an entry there corrects
every machine already filed under it. After a substantial edit, bring the cached
rendering of existing machines back into line:

```sh
docker compose exec api python -m app.resync
```

It prints what it would change before changing anything.

You do not have to edit the file to record something it does not list, though.
Every variation is offered as a set of choices with a "custom" box beside it, and
anything typed into one is offered as a choice on the next machine of that model.
The catalogue is a head start, not a fence.

### Labels

The label layout, sizes and printer names live in `tools/config.yml`. The
defaults are a 6×4 inch full label and a 19×51 mm small one, sized for DYMO
LabelWriters. See [the manual](MANUAL.md#labels) for the details.

## 10. Optional extras

### The command-line tools

`tools/` holds scripts that talk to the REST API over the network, so they can
run on whichever machine has the hardware attached — the one with the label
printer, or the one with the floppy drive.

```sh
cd tools
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export RHDB_API=https://db.example.com
export RHDB_AUTH_USER=... RHDB_AUTH_PASSWORD=...
.venv/bin/python make_labels.py --auto RH-4K7Q
```

- `make_labels.py` — label PDFs with a QR code each, optionally sent straight to
  a CUPS printer.
- `import_report.py` — reads an HWiNFO or MSD report from a boot disk and
  proposes updates to the machine, its motherboard and its drives. It writes
  nothing without confirmation.

### The tool server

The `mcp` service exposes the REST API as a set of tools over the Model Context
Protocol, on port 8001. It stores nothing itself — every call is an HTTP request
to the same API the GUI uses. If you have no use for it, remove the `mcp` block
from `docker-compose.yml`; nothing else depends on it.

### Traffic statistics

The `goaccess` service turns Caddy's access logs into an HTML report every five
minutes, which the app serves at `/traffic` behind the login. It reads the
rolled-over logs as well as the live one, so the report covers however much
history `roll_keep` above is holding on to -- raise it for a longer view, at a
little more disk and a little more work per rebuild. Remove the service from
`docker-compose.yml` if you would rather not keep access logs at all.

---

## Trying it locally

Without a domain, without HTTPS, without any of the above:

```sh
cp .env.example .env
docker compose up --build
```

To work on the code, layer the development override on top. The source is mounted
into the container and the app reloads when a file is saved, so a change shows
without a rebuild:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The site is at <http://localhost:8000> and the API console at
<http://localhost:8000/docs>. Leaving `RHDB_AUTH_USER` and `RHDB_AUTH_PASSWORD`
blank in `.env` runs it with no login at all, which is the quickest way to have a
look around.

There is no SQLite path. Alembic owns the schema and its migrations are written
for MariaDB, so the app no longer builds its own tables from the models
(ADR-0008) — pointed at a SQLite file it starts and then answers every page with
an error about a table that is not there. The suite refuses a SQLite
`DATABASE_URL` outright for the same reason.

To run the app outside a container against the database in one, publish the
database's port in a compose override and point `DATABASE_URL` at it:

```sh
cd api
pip install -r requirements.txt
DATABASE_URL=mysql+pymysql://retro:<your DB_PASSWORD>@127.0.0.1:3306/retro \
  uvicorn app.main:app --reload
```

---

## When something is wrong

| Symptom | Where to look |
|---|---|
| The site does not answer at all | `docker compose ps` — is `caddy` running? Is port 443 open in your provider's firewall as well as the box's? |
| HTTPS fails, HTTP works | `docker compose logs caddy` — almost always DNS, or port 80 blocked. |
| A 500 from the app | `docker compose logs api` — the traceback is at the end. |
| The app will not start, database errors | `docker compose logs db`. On a first run the app waits for the database's health check; give it a minute. |
| Logged in but no edit buttons | The cookie is signed with `RHDB_SECRET_KEY`. If you changed it, log in again. |
| Labels point at the wrong site | `RHDB_BASE_URL` in `.env`, and `base_url` in `tools/config.yml` for the command-line tool. Both, if you use both. |
| Photographs vanished after a rebuild | They should not have — they are in the `images` volume. Check `docker volume ls` for a stale project name if you renamed the directory. |

A shell inside the app container, for anything else:

```sh
docker compose exec api sh
```
