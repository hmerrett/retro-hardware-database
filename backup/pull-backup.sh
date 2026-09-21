#!/bin/sh
# Pull db.2600.me's data to this machine and keep a deduplicated history of it.
#
# Runs wherever you want the off-site copy to live -- a home server, a NAS -- and
# reaches out to the server over SSH. Nothing needs to be open inbound at home,
# and the server needs no knowledge of this at all.
#
# Three things are collected:
#   * the database, dumped straight out of the db container to stdout, so no
#     temporary file is written on the server and its disk cannot fill up
#   * the photo volume, rsynced, so only what changed crosses the wire
#   * the file volume -- the drivers, manuals and receipts kept beside the
#     register -- rsynced the same way
#
# Both land in a staging directory that mirrors the server, and restic snapshots
# that. The staging copy is what makes the transfers cheap; the snapshots are
# what give you last night *and* last month.
set -eu

: "${RHDB_HOST:?set RHDB_HOST, e.g. root@db.2600.me}"
RHDB_DIR="${RHDB_DIR:-/root/retro-hardware-database}"
RHDB_IMAGES="${RHDB_IMAGES:-/var/lib/docker/volumes/retro-hardware-database_images/_data}"
RHDB_FILES="${RHDB_FILES:-/var/lib/docker/volumes/retro-hardware-database_files/_data}"
STAGE="${STAGE:-/stage}"
BACKUP_AT="${BACKUP_AT:-03:30}"
INCLUDE_ENV="${INCLUDE_ENV:-1}"
# VERBOSE=1 additionally lists every file rsync moved and every file restic stored.
# Useful once; noisy nightly, since there are several hundred of them.
VERBOSE="${VERBOSE:-0}"

KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-5}"
KEEP_MONTHLY="${KEEP_MONTHLY:-12}"
KEEP_YEARLY="${KEEP_YEARLY:-3}"

# ConnectTimeout matters: without it an unreachable server leaves the run hanging
# on a TCP timeout, and the scheduler behind it never gets to try again.
SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"

say() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Indented, so the detail under a step reads as belonging to it.
detail() {
    sed 's/^/             /'
}

since() {
    echo "$(( $(date +%s) - $1 ))s"
}

# The password and database name stay on the server: the remote shell expands
# them, so they are never an argument here and never reach this machine.
remote_dump() {
    # shellcheck disable=SC2029
    $SSH "$RHDB_HOST" 'cd '"$RHDB_DIR"' && set -a && . ./.env && set +a && '\
'docker compose exec -T db mariadb-dump -u root -p"$DB_ROOT_PASSWORD" '\
'--single-transaction --quick --databases "$DB_NAME"'
}

# Rows in one table, counted from the dump. mariadb-dump writes one INSERT per
# table with the tuples on their own lines after VALUES, so the tuples are the
# lines starting with "(" until the statement's semicolon. A table with no rows
# has no INSERT at all, which counts as zero.
_dump_rows() {
    awk -v t="\`$1\`" '
        $0 ~ "^INSERT INTO " t " VALUES" { inblock = 1; next }
        inblock && /^\(/ { n++ }
        inblock && /;[[:space:]]*$/ { inblock = 0 }
        END { print n + 0 }
    ' "$STAGE/db.sql"
}

collect() {
    mkdir -p "$STAGE"

    say "dumping the database from $RHDB_HOST"
    t=$(date +%s)
    remote_dump > "$STAGE/db.sql.part"
    if ! grep -q "^-- Dump completed" "$STAGE/db.sql.part"; then
        say "the dump did not finish -- keeping last night's and stopping"
        rm -f "$STAGE/db.sql.part"
        return 1
    fi
    was=0
    [ -f "$STAGE/db.sql" ] && was=$(wc -c < "$STAGE/db.sql")
    mv "$STAGE/db.sql.part" "$STAGE/db.sql"
    now=$(wc -c < "$STAGE/db.sql")
    {
        echo "size      $now bytes (last night $was)"
        echo "tables    $(grep -c '^CREATE TABLE' "$STAGE/db.sql")"
        echo "schema    $(grep -A2 'INSERT INTO `alembic_version`' "$STAGE/db.sql" \
                          | grep -o "'[0-9_a-z]*'" | head -1 | tr -d "'")"
        echo "rows      computers $(_dump_rows computers), parts $(_dump_rows parts), \
history $(_dump_rows log_entry)"
        echo "took      $(since "$t")"
    } | detail

    # -rlt rather than -a: photos need their contents and timestamps, not their
    # ownership, and a NAS mounted over SMB cannot store ownership at all -- with
    # -a rsync fails there. Timestamps matter because both rsync and restic use
    # them to decide what has changed.
    # .wm holds watermarked copies the app regenerates on demand -- a third of the
    # volume, and all of it rewritten whenever the watermark size changes. The .ref
    # sidecars beside the photos are not excluded: those are recorded state, saying
    # which photos are someone else's picture of the model rather than ours.
    say "syncing photos from $RHDB_IMAGES"
    t=$(date +%s)
    [ "$VERBOSE" = "1" ] && rsync_v="-v" || rsync_v=""
    # shellcheck disable=SC2086
    if ! rsync_out=$(rsync -rlt $rsync_v --delete --exclude ".wm/" --info=stats2 \
            -e "$SSH" "$RHDB_HOST:$RHDB_IMAGES/" "$STAGE/images/" 2>&1); then
        say "photo sync failed:"
        echo "$rsync_out" | tail -5 | detail
        return 1
    fi
    echo "$rsync_out" \
        | grep -E "^(Number of|Total|Literal|Matched|sent|total size)" | detail
    {
        echo "on disk   $(du -sh "$STAGE/images" | cut -f1) in \
$(find "$STAGE/images" -type f | wc -l | tr -d ' ') files"
        echo "took      $(since "$t")"
    } | detail

    # The files kept beside the register -- drivers, manuals, receipts, ROM dumps.
    # Same flags as the photos and for the same reasons. Nothing is excluded: the
    # images volume carries a regenerable watermark cache, this one holds uploads
    # alone, and every one of them exists nowhere else.
    say "syncing files from $RHDB_FILES"
    t=$(date +%s)
    # shellcheck disable=SC2086
    if ! rsync_out=$(rsync -rlt $rsync_v --delete --info=stats2 \
            -e "$SSH" "$RHDB_HOST:$RHDB_FILES/" "$STAGE/files/" 2>&1); then
        say "file sync failed:"
        echo "$rsync_out" | tail -5 | detail
        return 1
    fi
    echo "$rsync_out" \
        | grep -E "^(Number of|Total|Literal|Matched|sent|total size)" | detail
    {
        echo "on disk   $(du -sh "$STAGE/files" | cut -f1) in \
$(find "$STAGE/files" -type f | wc -l | tr -d ' ') files"
        echo "took      $(since "$t")"
    } | detail

    if [ "$INCLUDE_ENV" = "1" ]; then
        # Credentials are configuration, not data, but a backup you cannot
        # restore with is half a backup. The restic repository is encrypted.
        say "copying .env"
        $SSH "$RHDB_HOST" "cat $RHDB_DIR/.env" > "$STAGE/env"
        echo "keys      $(grep -c '^[A-Z]' "$STAGE/env") settings" | detail
    fi
}

snapshot() {
    if ! restic cat config >/dev/null 2>&1; then
        say "initialising the restic repository at $RESTIC_REPOSITORY"
        restic init | detail
    fi
    say "snapshotting into $RESTIC_REPOSITORY"
    t=$(date +%s)
    [ "$VERBOSE" = "1" ] && restic_v="--verbose" || restic_v=""
    # shellcheck disable=SC2086
    restic backup $restic_v --tag rhdb --host "${SNAPSHOT_HOST:-db.2600.me}" "$STAGE" \
        | detail
    echo "took      $(since "$t")" | detail

    say "applying retention: ${KEEP_DAILY}d ${KEEP_WEEKLY}w ${KEEP_MONTHLY}m ${KEEP_YEARLY}y"
    restic forget --tag rhdb \
        --keep-daily "$KEEP_DAILY" --keep-weekly "$KEEP_WEEKLY" \
        --keep-monthly "$KEEP_MONTHLY" --keep-yearly "$KEEP_YEARLY" \
        --prune | grep -vE "^(keep [0-9]|remove [0-9]|snapshots for|-----|ID  )" | detail

    # Structure every night; on Sundays also re-read a slice of the actual data,
    # which is what catches bit rot on the disk holding the repository.
    if [ "$(date +%u)" = "7" ]; then
        say "weekly integrity check (structure + 5% of the data)"
        restic check --read-data-subset=5% | detail
    else
        say "integrity check (structure)"
        restic check | detail
    fi
}


summarise() {
    say "the backup now holds"
    restic snapshots --tag rhdb --compact 2>/dev/null | detail
    restic stats --tag rhdb --mode raw-data 2>/dev/null \
        | grep -E "Total|File" | detail
    # Only meaningful for a repository on a filesystem; sftp and s3 have no df.
    case "$RESTIC_REPOSITORY" in
        /*) df -h "$RESTIC_REPOSITORY" \
                | awk -v r="$RESTIC_REPOSITORY" \
                      'NR==2 {print "space     " $4 " free of " $2 " at " r}' | detail ;;
    esac
}

run_once() {
    started=$(date +%s)
    say "starting a backup of $RHDB_HOST"
    collect
    snapshot
    summarise
    say "done in $(since "$started")"
}

# Each check stops the run, because `cmd && say "ok"` does not: a failure on the
# left of && does not trip `set -e`, so this used to report every SSH probe
# failing and then say "all checks passed" with exit 0.
fail() {
    say "  FAILED: $1"
    exit 1
}

self_check() {
    say "checking the SSH connection to $RHDB_HOST"
    $SSH "$RHDB_HOST" true 2>&1 || fail "cannot reach it. Is the public key in that \
host's ~/.ssh/authorized_keys, and is RHDB_HOST right?"
    say "  reachable"

    say "checking the repository directory"
    $SSH "$RHDB_HOST" "test -f $RHDB_DIR/.env" \
        || fail "no $RHDB_DIR/.env on the server. Set RHDB_DIR to where the repo is."
    say "  $RHDB_DIR/.env found"

    say "checking the photo volume"
    $SSH "$RHDB_HOST" "test -d $RHDB_IMAGES" \
        || fail "no $RHDB_IMAGES on the server. Check RHDB_IMAGES, or the volume name."
    size=$($SSH "$RHDB_HOST" "du -sh $RHDB_IMAGES | cut -f1")
    say "  $RHDB_IMAGES found ($size)"

    say "checking the files volume"
    $SSH "$RHDB_HOST" "test -d $RHDB_FILES" \
        || fail "no $RHDB_FILES on the server. Check RHDB_FILES, or the volume name."
    size=$($SSH "$RHDB_HOST" "du -sh $RHDB_FILES | cut -f1")
    say "  $RHDB_FILES found ($size)"

    say "checking the database dump"
    remote_dump 2>/dev/null | head -c 200 | grep -q "MariaDB dump" \
        || fail "the dump produced nothing usable. Can that user run docker compose \
in $RHDB_DIR?"
    say "  dump works"

    say "checking where the backup will be written"
    touch "$STAGE/.writable" 2>/dev/null \
        || fail "$STAGE is not writable. Check the mount, and that the NAS share is up."
    rm -f "$STAGE/.writable"
    say "  $STAGE is writable"

    say "checking the restic repository"
    if restic cat config >/dev/null 2>&1; then
        say "  repository present at $RESTIC_REPOSITORY"
    else
        say "  none at $RESTIC_REPOSITORY yet; the first run will create it"
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
