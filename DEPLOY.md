# Deploying

The runbook for a server you have already installed on (see
[INSTALL.md](INSTALL.md) for the first time). The site runs on a single box under
docker-compose, which holds a normal git checkout of this repo, so deploying is:
get the new code onto the box, then rebuild the containers.

Everything about *your* box -- its name, its passwords, its logo, any extra names
Caddy answers -- is in `.env`, `caddy/conf.d/` and `branding/`, none of which are in
git. So the commands below are the same wherever it is installed, and where one
needs your domain it takes it from `.env` (`$RHDB_DOMAIN`).

## The normal flow

1. **Make changes anywhere** — edit locally or in a remote session and push to
   GitHub (`git push`), or edit on the box directly. All changes end up on the
   `main` branch on GitHub.

2. **On the server**, from the repo root (`/root/retro-hardware-database`):

   ```sh
   ./deploy.sh
   ```

   That pulls `main`, rebuilds, restarts, and tails the api log. It is safe to
   run repeatedly.

To get onto the box:

```sh
ssh root@<your-server>   # the box, by name or by IP
cd /root/retro-hardware-database
```

## What deploy.sh does (and the manual equivalent)

```sh
git pull --ff-only               # fetch the latest code
docker compose up -d --build     # rebuild changed images, recreate containers
docker image prune -f            # tidy up old layers
```

- Only images whose inputs changed are rebuilt; unchanged services are left
  running. To rebuild just the app: `docker compose up -d --build api`.
- **Migrations run automatically**: the api container's entrypoint runs
  `alembic upgrade head` on start, so a schema change ships with the code with
  no extra step.
- **Config-only changes** to `docker-compose.yml` need `docker compose up -d` to
  take effect; add `--build` if app code changed.
- **`caddy/Caddyfile` needs more than that.** It is bind-mounted into the
  container, so nothing Compose compares has changed and `docker compose up -d`
  -- and therefore `deploy.sh` -- leaves Caddy running on the old config without
  a word. `docker compose exec caddy caddy reload` does not save you either: the
  mount is of a single file, by inode, and an editor that writes-and-renames
  leaves the container holding the file as it was, so the reload reports
  `config is unchanged` and means it. Recreate the container:

  ```
  docker compose up -d --force-recreate caddy
  ```

  Then check it took, rather than trusting that it did:
  `docker compose exec caddy cat /etc/caddy/Caddyfile`.

## Extra names

Any name besides `$RHDB_DOMAIN` -- a bare domain redirecting to the www, the
address the collection used to live at -- is a block in `caddy/conf.d/*.caddy`,
which Caddy imports and git ignores. `caddy/conf.d/README.md` has the shape of one.
A redirect there should carry `{uri}` so a path survives the trip and an old link
lands where it was going rather than on the front page.

Each name needs its own certificate, and getting one needs its A record pointing at
this host: the ACME challenge is fetched over HTTP from wherever the name resolves,
so until it resolves here the answer comes from somewhere else or from nowhere.
Caddy retries in the background and backs off as it goes, so after the DNS lands the
quickest way to have it try again at once is to recreate the container:

```sh
docker compose up -d --force-recreate caddy
docker compose logs caddy --tail=40 | grep -i "$RHDB_DOMAIN"
```

The log says which problem it is: `Connection refused` at another address means the
name still points at the old host, and `NXDOMAIN` means there is no record yet.
Do not recreate it in a loop while waiting -- Let's Encrypt rate-limits failed
validations per name per hour, and the backoff exists to stay under that.

## Data is safe across deploys

These live in Docker named volumes, not in the image, so rebuilds never touch
them:

- `dbdata` — the MariaDB database
- `images` — uploaded photos (and their `.ref` reference markers)
- `files` — drivers, manuals and disk images uploaded beside the register
- `caddy_data` — TLS certificates
- `goaccess_report`, `caddy_logs` — traffic stats and access logs

Their full names carry the **Compose project name** in front —
`retro-hardware-database_dbdata` and so on. That name is pinned at the top of
`docker-compose.yml` rather than left to Compose, which would otherwise take it
from whatever the checkout directory is called. It is pinned because the
alternative is that renaming or moving the checkout silently moves the data:
Compose invents a new project, makes a fresh set of empty volumes, and the site
comes up blank with everything still sitting in volumes nothing points at.

### Moving an installation to the pinned name

An installation created before the name was pinned has its volumes under the old
project name. **Do this before bringing the stack up on the new name**, or the
first `docker compose up` creates empty ones. Nothing here deletes anything: the
old volumes are left alone, so it can be abandoned at any point.

```sh
cd /root/<old-directory>
./tools/backup.sh                     # the safety net, first
docker compose down                   # NOT -v: that would delete the volumes

OLD=<old-project-name>                # e.g. retro-hardware-db-2
NEW=retro-hardware-database
for v in dbdata images files caddy_data caddy_config caddy_logs goaccess_report; do
  docker volume create "${NEW}_$v"
  docker run --rm -v "${OLD}_$v":/from -v "${NEW}_$v":/to alpine \
    sh -c 'cd /from && cp -a . /to/'
done

cd .. && mv <old-directory> retro-hardware-database && cd retro-hardware-database
docker compose up -d
```

Copy rather than `tools/restore.sh`, even though the restore path is the tested
one: the backup covers the database, the photographs and the files, and **not**
`caddy_data`, `caddy_logs` or `goaccess_report` — so restoring alone would throw
away the TLS certificate, forcing a fresh Let's Encrypt issue, and wipe the
traffic history. A copy moves all seven exactly as they are.

Check the site answers, then the old volumes can go:

```sh
for v in dbdata images files caddy_data caddy_config caddy_logs goaccess_report; do
  docker volume rm "${OLD}_$v"
done
```

Leave that last step a few days. It is the only irreversible part.

## Secrets

`.env` holds the DB and login credentials and is **git-ignored** — it lives only
on the server and is never committed. If you add a new setting, update `.env` on
the box by hand; a fresh clone needs its own `.env`. `.env.example` is the list,
with what each key is for written beside it: `DB_*`, `RHDB_AUTH_USER`,
`RHDB_AUTH_PASSWORD`, `RHDB_SECRET_KEY` (the app refuses to start without it once
the credentials are set), `RHDB_OPEN`, `RHDB_DOMAIN`, `RHDB_ACME_EMAIL`,
`RHDB_BASE_URL`, `RHDB_WATERMARK` and `RHDB_PRINT_AGENTS`.

## Special case: changing the site icon

This installation's artwork lives in **`branding/`**, which is not in git and is
mounted read-only in front of the shipped files: a name that is not overridden
there falls through to the placeholder under `api/app/static`, so an update never
overwrites your logo and your logo never turns up in a pull request. Edit
`branding/`, never `api/app/static` — the latter is what ships to everybody.

Everything the brand appears on is generated from one master,
`branding/app-icon.png`: the favicons and app icons (square, transparent),
`logo-256.png` for the header and `logo-512.png` for the photo watermark (the
logo's own proportions), and `og-image.png`, the card a shared link previews as.
After replacing that master, regenerate the set before rebuilding:

```sh
docker run --rm -v "$PWD/branding:/static" -v "$PWD/tools:/tools" \
  retro-hardware-database-api python /tools/make_icons.py
./deploy.sh
```

The master should be a transparent PNG; the script crops it to its artwork,
squares it for the icon slots, and keeps the alpha channel everywhere except
`apple-touch-icon.png` (iOS composites transparency on black, so that one is
flattened on white). Anywhere with Pillow, `RHDB_STATIC=branding python3
tools/make_icons.py` does the same without Docker. `branding/README.md` says what
each file is.

Both caches key themselves on the artwork, so nothing has to be cleared by hand:
the `?v=` in the page head follows the favicon's hash, and the watermark cache
directory is named partly after the mark's, so already-served photos are
re-marked rather than keeping the old logo.

## After a deploy that touches photographs or units

Two things are derived rather than stored, and neither is required — the site
works without them and heals itself as it is used. Running them makes that
happen at once instead of making the next visitor pay for it.

**The resized photographs.** Cards and item pages are served copies of the
photographs at the size they are drawn, made on first request and kept. After a
deploy of a fresh image volume, or a bulk import, make them all up front:

```sh
docker compose exec api python -m app.thumbs
```

Four hundred photographs take a couple of minutes. Without it the first person to
open the gallery waits while every one of them is resized, and each resize
competes with the page they are waiting for.

Both photograph caches are named after what went into them, so a change to how a
copy is made simply misses the old directory instead of needing anyone to remember
to clear it. A deploy that bumps either one therefore leaves every copy to be made
again — which is exactly when the warm-up above is worth running rather than
leaving the first visitor to pay for it.

**The rendered caches** — a part's specs line, a machine's memory, a machine's
catalogue line. These only drift when the words behind them change: the machine
catalogue in `api/app/machines.yaml`, or how a figure is rendered.

```sh
docker compose exec api python -m app.resync           # report only
docker compose exec api python -m app.resync --write   # apply
```

## Checking on it

```sh
docker compose ps                 # container status
docker compose logs -f api        # follow app logs
docker compose logs -f caddy      # TLS / proxy logs
curl -I "https://$RHDB_DOMAIN/"   # should return 200
```

The traffic report is at `https://$RHDB_DOMAIN/traffic` (login required); the
collection's own statistics are at `/stats`, and those are public.

## Rolling back

```sh
git log --oneline -n 10           # find the last good commit
git checkout <sha>                # or: git revert <bad-sha>
docker compose up -d --build
```

The database is not rolled back automatically; if a bad migration shipped, use
`docker compose exec api alembic downgrade -1`.
