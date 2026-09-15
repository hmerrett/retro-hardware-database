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

## Secrets

`.env` holds the DB and login credentials and is **git-ignored** — it lives only
on the server and is never committed. If you add a new setting, update `.env` on
the box by hand; a fresh clone needs its own `.env` (see the keys referenced in
`docker-compose.yml`: `DB_*`, `RHDB_AUTH_USER`, `RHDB_AUTH_PASSWORD`,
`RHDB_BASE_URL`).

## Special case: changing the site icon

Everything the brand appears on is generated from `api/app/static/app-icon.png`:
the favicons and app icons (square, transparent), `logo-256.png` for the header
and `logo-512.png` for the photo watermark (the logo's own proportions), and
`og-image.png`, the card a shared link previews as. After replacing that master,
regenerate the set before rebuilding:

```sh
docker run --rm -v "$PWD/api/app/static:/static" -v "$PWD/tools:/tools" \
  retro-hardware-database-api python /tools/make_icons.py
./deploy.sh
```

The master should be a transparent PNG; the script crops it to its artwork,
squares it for the icon slots, and keeps the alpha channel everywhere except
`apple-touch-icon.png` (iOS composites transparency on black, so that one is
flattened on white). Anywhere with Pillow, `RHDB_STATIC=api/app/static python3
tools/make_icons.py` does the same without Docker.

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

Traffic stats are at `https://$RHDB_DOMAIN/stats` (login required).

## Rolling back

```sh
git log --oneline -n 10           # find the last good commit
git checkout <sha>                # or: git revert <bad-sha>
docker compose up -d --build
```

The database is not rolled back automatically; if a bad migration shipped, use
`docker compose exec api alembic downgrade -1`.
