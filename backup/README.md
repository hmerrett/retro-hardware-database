# Off-site backup

Pulls the catalogue's data from the server to a machine you keep at home, nightly,
and holds a deduplicated history of it.

It runs **on the machine that stores the backup**, not on the server. It reaches
out over SSH, so nothing at home needs to be reachable from the internet, and the
server does not need to know this exists. The server also never writes a
temporary dump to its own disk, so it cannot fill up.

## What gets collected

| | how | why that way |
|---|---|---|
| the database | `mariadb-dump` inside the db container, streamed to stdout over SSH | ~170 KB, uncompressed so restic can deduplicate it night to night |
| the photos | `rsync` from the docker volume | 260 MB that barely changes, so only new files cross the wire |
| `.env` | `cat` over SSH, optional | a backup you cannot restore *with* is half a backup; the repository is encrypted |

## Setting it up

On the machine that will hold the backup:

```sh
git clone git@github.com:hmerrett/retro-hardware-db-2.git
cd retro-hardware-db-2/backup
cp .env.example .env          # then edit it: RHDB_HOST and BACKUP_DIR at least

mkdir -p secrets
ssh-keygen -t ed25519 -N "" -f secrets/id_ed25519
openssl rand -base64 32 > secrets/restic-password
ssh-copy-id -i secrets/id_ed25519 root@db.2600.me
```

Keep `secrets/restic-password` somewhere else as well — a password manager, a bit
of paper. **Without it the backup cannot be read**, and a copy that only lives on
the machine holding the backup protects you from nothing.

Then prove the setup before trusting it:

```sh
docker compose run --rm backup check
```

That checks the SSH connection, that the repo directory and `.env` are where it
expects, that the photo volume is readable, that the dump command works, and
whether a restic repository exists yet. When it passes:

```sh
docker compose up -d
```

It sleeps until `BACKUP_AT` each night. `docker compose logs -f backup` shows what
it did; `docker compose run --rm backup once` runs one immediately.

## Retention

Defaults, set in `.env`:

```
KEEP_DAILY=7      a week of nights
KEEP_WEEKLY=5     five Sundays
KEEP_MONTHLY=12   a year of months
KEEP_YEARLY=3     three years
```

That is 27 snapshots at the far end. Because restic stores each unique chunk once,
the cost is roughly *the photo volume, plus whatever has changed since* -- about
250 MB today, growing with the collection rather than with the number of
snapshots. A night where nothing changed adds nothing at all.

Every run also verifies the repository's structure. On Sundays it re-reads 5% of
the actual data, which is what catches a disk quietly rotting underneath it.

## Getting it back

List what you have:

```sh
docker compose run --rm backup snapshots
```

Restore the latest, or a particular snapshot, into `./restored`:

```sh
docker compose run --rm -v "$PWD/restored:/restored" backup shell
  restic restore latest --target /restored
  restic restore 8d10e220 --target /restored          # a specific one
  restic restore latest --target /restored --include /stage/db.sql   # just the database
```

You get `stage/db.sql`, `stage/images/` and `stage/env`.

To load the database onto a server, from the repo root there:

```sh
docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db mariadb -uroot < db.sql
docker compose exec -T api tar -xf - -C /app < <(tar -cf - -C restored/stage images)
```

The dump carries its own `CREATE DATABASE` and `USE`, so it always lands on the
database it came from whatever you name on the command line. To inspect a snapshot
*beside* live data instead, strip those two lines into a scratch database:

```sh
grep -vE '^(CREATE DATABASE|USE )' db.sql \
  | docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db mariadb -uroot scratch
```

Schema migrations need no separate step: the api container runs
`alembic upgrade head` when it starts, and the dump carries `alembic_version` so
it knows where it is.

## Tightening the SSH key

The key as set up above can do anything root can. To limit it to what the backup
actually needs, put a forced command in front of it in the server's
`~/.ssh/authorized_keys`, or give it its own user with `sudo` rules for the three
commands (`docker compose exec db mariadb-dump`, reading the images volume,
`cat .env`). Worth doing if the home machine is shared.

## What was verified when this was written

A full round trip against the live server: dump and photos collected, snapshotted,
pruned by the retention policy, restored, and compared. The restored `db.sql` was
byte-identical to what the server produced, all 624 photos matched the live volume
by checksum, and loading the restored dump into a scratch database gave the same
14 computers, 279 parts, 289 history entries and schema version as live.
