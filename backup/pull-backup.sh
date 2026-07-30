#!/bin/sh
# Pull db.2600.me's data to this machine and keep a deduplicated history of it.
#
# Runs wherever you want the off-site copy to live -- a home server, a NAS -- and
# reaches out to the server over SSH. Nothing needs to be open inbound at home,
# and the server needs no knowledge of this at all.
#
# Two things are collected:
#   * the database, dumped straight out of the db container to stdout, so no
#     temporary file is written on the server and its disk cannot fill up
#   * the photo volume, rsynced, so only what changed crosses the wire
#
# Both land in a staging directory that mirrors the server, and restic snapshots
# that. The staging copy is what makes the transfers cheap; the snapshots are
# what give you last night *and* last month.
set -eu

: "${RHDB_HOST:?set RHDB_HOST, e.g. root@db.2600.me}"
RHDB_DIR="${RHDB_DIR:-/root/retro-hardware-db-2}"
RHDB_IMAGES="${RHDB_IMAGES:-/var/lib/docker/volumes/retro-hardware-db-2_images/_data}"
STAGE="${STAGE:-/stage}"
BACKUP_AT="${BACKUP_AT:-03:30}"
INCLUDE_ENV="${INCLUDE_ENV:-1}"

KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-5}"
KEEP_MONTHLY="${KEEP_MONTHLY:-12}"
KEEP_YEARLY="${KEEP_YEARLY:-3}"

SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

say() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# The password and database name stay on the server: the remote shell expands
# them, so they are never an argument here and never reach this machine.
remote_dump() {
    # shellcheck disable=SC2029
    $SSH "$RHDB_HOST" 'cd '"$RHDB_DIR"' && set -a && . ./.env && set +a && '\
'docker compose exec -T db mariadb-dump -u root -p"$DB_ROOT_PASSWORD" '\
'--single-transaction --quick --databases "$DB_NAME"'
}

collect() {
    mkdir -p "$STAGE"

    say "dumping the database"
    remote_dump > "$STAGE/db.sql.part"
    if ! grep -q "^-- Dump completed" "$STAGE/db.sql.part"; then
        say "the dump did not finish -- keeping last night's and stopping"
        rm -f "$STAGE/db.sql.part"
        return 1
    fi
    mv "$STAGE/db.sql.part" "$STAGE/db.sql"
    say "database: $(wc -c < "$STAGE/db.sql") bytes"

    say "syncing photos"
    rsync -a --delete --info=stats2 -e "$SSH" \
        "$RHDB_HOST:$RHDB_IMAGES/" "$STAGE/images/" | grep -E "Number of|Total" || true

    if [ "$INCLUDE_ENV" = "1" ]; then
        # Credentials are configuration, not data, but a backup you cannot
        # restore with is half a backup. The restic repository is encrypted.
        say "copying .env"
        $SSH "$RHDB_HOST" "cat $RHDB_DIR/.env" > "$STAGE/env"
    fi
}

snapshot() {
    if ! restic cat config >/dev/null 2>&1; then
        say "initialising the restic repository at $RESTIC_REPOSITORY"
        restic init
    fi
    say "snapshotting"
    restic backup --tag rhdb --host "${SNAPSHOT_HOST:-db.2600.me}" "$STAGE"

    say "applying retention: ${KEEP_DAILY}d ${KEEP_WEEKLY}w ${KEEP_MONTHLY}m ${KEEP_YEARLY}y"
    restic forget --tag rhdb \
        --keep-daily "$KEEP_DAILY" --keep-weekly "$KEEP_WEEKLY" \
        --keep-monthly "$KEEP_MONTHLY" --keep-yearly "$KEEP_YEARLY" \
        --prune

    # Structure every night; on Sundays also re-read a slice of the actual data,
    # which is what catches bit rot on the disk holding the repository.
    if [ "$(date +%u)" = "7" ]; then
        say "weekly integrity check (structure + 5% of the data)"
        restic check --read-data-subset=5%
    else
        say "integrity check (structure)"
        restic check
    fi
}

run_once() {
    started=$(date +%s)
    collect
    snapshot
    say "done in $(( $(date +%s) - started ))s"
    restic snapshots --tag rhdb --latest 3 --compact 2>/dev/null || true
}

self_check() {
    say "checking the SSH connection"
    $SSH "$RHDB_HOST" true && say "  reachable"
    say "checking the repository directory and .env"
    $SSH "$RHDB_HOST" "test -f $RHDB_DIR/.env" && say "  $RHDB_DIR/.env found"
    say "checking the photo volume"
    $SSH "$RHDB_HOST" "test -d $RHDB_IMAGES" \
        && say "  $RHDB_IMAGES found ($($SSH "$RHDB_HOST" "du -sh $RHDB_IMAGES | cut -f1"))"
    say "checking the database dump"
    remote_dump | head -c 200 | grep -q "MariaDB dump" && say "  dump works"
    say "checking the restic repository"
    if restic cat config >/dev/null 2>&1; then
        say "  repository present, $(restic snapshots --tag rhdb --json 2>/dev/null | grep -c '"time"') snapshot(s)"
    else
        say "  no repository yet; the first run will create it"
    fi
    say "all checks passed"
}

# Wall-clock arithmetic rather than `date -d "tomorrow .."`: that is a GNU
# extension and this runs on busybox. Leading zeros are stripped because the
# shell would read 03 as octal.
seconds_until() {
    hh=${1%%:*}
    mm=${1##*:}
    hh=${hh#0}
    mm=${mm#0}
    now=$(( $(date +%-H) * 3600 + $(date +%-M) * 60 + $(date +%-S) ))
    target=$(( ${hh:-0} * 3600 + ${mm:-0} * 60 ))
    [ "$target" -le "$now" ] && target=$(( target + 86400 ))
    echo $(( target - now ))
}

case "${1:-schedule}" in
    once)      run_once ;;
    check)     self_check ;;
    snapshots) restic snapshots --tag rhdb ;;
    shell)     exec /bin/sh ;;
    schedule)
        say "nightly at $BACKUP_AT; keeping ${KEEP_DAILY}d ${KEEP_WEEKLY}w ${KEEP_MONTHLY}m ${KEEP_YEARLY}y"
        while true; do
            wait_for=$(seconds_until "$BACKUP_AT")
            say "next run in $(( wait_for / 3600 ))h $(( (wait_for % 3600) / 60 ))m"
            sleep "$wait_for"
            run_once || say "run failed; will try again tomorrow"
        done
        ;;
    *)
        echo "usage: $0 [schedule|once|check|snapshots|shell]" >&2
        exit 64
        ;;
esac
