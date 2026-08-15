# Deploying db.2600.me

The site runs on a single cloud box under docker-compose. The server holds a
normal git checkout of this repo, so deploying is: get the new code onto the
box, then rebuild the containers.

## The normal flow

1. **Make changes anywhere** — edit locally or in a remote session and push to
   GitHub (`git push`), or edit on the box directly. All changes end up on the
   `main` branch on GitHub.

2. **On the server**, from the repo root (`/root/retro-hardware-db-2`):

   ```sh
   ./deploy.sh
   ```

   That pulls `main`, rebuilds, restarts, and tails the api log. It is safe to
   run repeatedly.

To get onto the box:

```sh
ssh root@db.2600.me      # or: ssh root@<server-ip>
cd /root/retro-hardware-db-2
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

## The bare domain

`2600.me` and `www.2600.me` are not sites of their own: Caddy answers both with a
301 to `https://db.2600.me{uri}`, so a path survives the trip and an old link lands
where it was going rather than on the front page.

Each name needs its own certificate, and getting one needs its A record pointing at
this host: the ACME challenge is fetched over HTTP from wherever the name resolves,
so until it resolves here the answer comes from somewhere else or from nowhere.
Caddy retries in the background and backs off as it goes, so after the DNS lands the
quickest way to have it try again at once is to recreate the container:

```sh
docker compose up -d --force-recreate caddy
docker compose logs caddy --tail=40 | grep -i 2600.me
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
  retro-hardware-db-2-api python /tools/make_icons.py
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

## Checking on it

```sh
docker compose ps                 # container status
docker compose logs -f api        # follow app logs
docker compose logs -f caddy      # TLS / proxy logs
curl -I https://db.2600.me/       # should return 200
```

Traffic stats are at <https://db.2600.me/stats> (login required).

## Rolling back

```sh
git log --oneline -n 10           # find the last good commit
git checkout <sha>                # or: git revert <bad-sha>
docker compose up -d --build
```

The database is not rolled back automatically; if a bad migration shipped, use
`docker compose exec api alembic downgrade -1`.
