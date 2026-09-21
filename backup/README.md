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
| the photos | `rsync` from the docker volume, minus `.wm` | ~195 MB that barely changes, so only new files cross the wire. `.wm` is the watermark cache, regenerated on demand and a third of the volume; the `.ref` sidecars are kept, being recorded state |
| the files | `rsync` from the docker volume | the drivers, manuals, receipts and ROM dumps uploaded beside the register. Nothing is excluded: unlike the photos there is no regenerable cache in here, and every file exists nowhere else |
| `.env` | `cat` over SSH, optional | a backup you cannot restore *with* is half a backup; the repository is encrypted |

## Where the backup lives

`RHDB_DIR`, `RHDB_IMAGES` and `RHDB_FILES` are paths **on the server**;
`BACKUP_DIR` is the one on this machine. Two directories are created under it:

```
$BACKUP_DIR/repo    the restic repository -- this is the backup
$BACKUP_DIR/stage   a mirror of the server, so each night transfers only changes
```

A NAS path works directly (`/mnt/nas/backup/rhdb`, a Synology shared folder, an
NFS or SMB mount). Two options if you want them apart:

- `STAGE_DIR` puts the working mirror on local disk while the repository stays on
  the NAS. Faster, and it halves what the NAS holds -- the mirror is rebuildable,
  so losing it costs one slow night and no history.
- `RESTIC_REPOSITORY=sftp:admin@nas:/volume1/backup/rhdb` skips the mount and lets
  restic talk to the NAS itself. Useful if the NAS is awkward to mount, or you
  would rather not hand a mount write access to a whole directory tree.

Photos are synced with `-rlt` rather than `-a`, deliberately: their contents and
timestamps matter, their ownership does not, and an SMB mount cannot store
ownership at all -- with `-a`, rsync fails there.

## Setting it up

Needs Docker **with the Compose plugin** — `docker compose version` should print a
version. If `docker` lists no `compose` command, the plugin is missing:

```sh
apt install docker-compose-plugin     # Docker's own apt repository
apt install docker-compose-v2         # Debian/Ubuntu's packaging of the same thing
```

Everything below also works without Compose, if you would rather not install it:

```sh
docker build -t rhdb-backup .
set -a; . ./.env; set +a
docker run --rm \
  -e RHDB_HOST -e RHDB_DIR -e RHDB_IMAGES -e RHDB_FILES -e BACKUP_AT -e TZ -e INCLUDE_ENV \
  -e KEEP_DAILY -e KEEP_WEEKLY -e KEEP_MONTHLY -e KEEP_YEARLY \
  -e RESTIC_REPOSITORY=/repo -e RESTIC_PASSWORD_FILE=/run/secrets/restic-password \
  -e STAGE=/stage \
  -v "$BACKUP_DIR/repo:/repo" \
  -v "${STAGE_DIR:-$BACKUP_DIR/stage}:/stage" \
  -v "$PWD/secrets/id_ed25519:/root/.ssh/id_ed25519:ro" \
  -v "$PWD/secrets/restic-password:/run/secrets/restic-password:ro" \
  rhdb-backup check
```

Swap `check` for `once` to run a backup, or drop `--rm` for `-d --restart
unless-stopped` with no argument to leave it running nightly.

On the machine that will hold the backup:

```sh
git clone git@github.com:hmerrett/retro-hardware-database.git
cd retro-hardware-database/backup
cp .env.example .env          # then edit it: RHDB_HOST and BACKUP_DIR at least

ssh-keygen -t ed25519 -N "" -f secrets/id_ed25519
openssl rand -base64 32 > secrets/restic-password
chmod 600 secrets/restic-password
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

A run reports what it actually moved, so the log is worth something when a night
looks wrong:

```
[03:30:01] dumping the database from root@db.2600.me
             size      174143 bytes (last night 174012)
             tables    19
             schema    0013_normalise_cpu
             rows      computers 15, parts 282, history 327
[03:30:03] syncing photos from /var/lib/.../_data
             Number of regular files transferred: 2
             Total transferred file size: 1,204,338 bytes
             on disk   194M in 625 files
[03:30:12] snapshotting into /repo
             using parent snapshot ea7ebed6
             Added to the repository: 1.171 MiB (1.093 MiB stored)
[03:30:14] applying retention: 7d 5w 12m 3y
[03:30:15] integrity check (structure)
             no errors were found
[03:30:16] the backup now holds
             8 snapshots
             Total Size:  251.4 MiB
             space     412G free of 3.6T at /repo
[03:30:16] done in 15s
```

The row counts are read out of the dump itself, so a night where the database
came back short is visible rather than merely smaller. `VERBOSE=1` adds every
file rsync moved and every blob restic stored -- worth it once, noisy nightly.

## Retention

Defaults, set in `.env`:

```
KEEP_DAILY=7      a week of nights
KEEP_WEEKLY=5     five Sundays
KEEP_MONTHLY=12   a year of months
KEEP_YEARLY=3     three years
```

That is 27 snapshots at the far end. Because restic stores each unique chunk once,
the cost is roughly *the photo and file volumes, plus whatever has changed since*
-- growing with the collection rather than with the number of snapshots. A night where nothing changed adds nothing at all.

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

You get `stage/db.sql`, `stage/images/`, `stage/files/` and `stage/env`.

To load the database onto a server, from the repo root there:

```sh
docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db mariadb -uroot < db.sql
docker compose exec -T api tar -xf - -C /app < <(tar -cf - -C restored/stage images)
docker compose exec -T api tar -xf - -C /app < <(tar -cf - -C restored/stage files)
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

The files volume joined the backup on 2026-09-21 and was verified the same way:
`check` found 30M on the server that nothing had been collecting, the first run
moved all 12 files (31,397,392 bytes), and restoring that snapshot handed back a
`stage/files/` identical file for file to what was collected.
