#!/usr/bin/env bash
#
# Restore a backup written by tools/backup.sh into the running stack, then check
# that what landed is what the backup held.
#
#   tools/restore.sh <stamp>            e.g. tools/restore.sh 20260911-031700
#
# Reads db-<stamp>.sql.gz, images-<stamp>.tgz and files-<stamp>.tgz from ./backups
# (override with RHDB_BACKUP_DIR), the three files one backup run writes.
#
# The database is REPLACED, not merged: the dump carries its own CREATE DATABASE
# and USE, and drops each table before recreating it. Photographs and files are
# extracted over what is there, so anything in the volumes that the backup does
# not hold is left alone. The cleanest restore is into a freshly started stack --
# a new server, or `docker compose -p restore-test up -d api` beside the real one
# to prove a backup is sound without touching anything.
#
# It asks before replacing the database. RHDB_RESTORE_YES=1 skips the question,
# for a script that has already made the decision.
#
# A backup nobody has restored is a hope rather than a backup. The checks at the
# end are the point of this script as much as the restore is: every table's row
# count against the dump, the schema version against the dump, every archived
# photograph and file present at the size it was archived at, and the app
# answering once it is all back.
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

STAMP="${1:-}"
if [ -z "$STAMP" ]; then
    echo "usage: tools/restore.sh <stamp>   (the part of the file names after db-)" >&2
    exit 2
fi
SRC="${RHDB_BACKUP_DIR:-backups}"
DUMP="$SRC/db-$STAMP.sql.gz"
IMAGES="$SRC/images-$STAMP.tgz"
FILES="$SRC/files-$STAMP.tgz"
DB="${DB_NAME:-retro}"

fail() { echo "!! $*" >&2; exit 1; }

# --- before touching anything: is the backup whole? ------------------------
# A truncated archive found halfway through a restore leaves the stack with the
# new database and the old photographs. Found here, it leaves the stack as it was.
echo "==> Checking the backup is whole"
for f in "$DUMP" "$IMAGES" "$FILES"; do
    [ -f "$f" ] || fail "missing: $f"
done
gzip -t "$DUMP" || fail "the database dump is damaged: $DUMP"
tar -tzf "$IMAGES" >/dev/null || fail "the photograph archive is damaged: $IMAGES"
tar -tzf "$FILES" >/dev/null || fail "the file archive is damaged: $FILES"

running="$(docker compose ps --status running --services)"
for svc in db api; do
    grep -qx "$svc" <<<"$running" || fail "the $svc service is not running; start the stack first"
done

if [ "${RHDB_RESTORE_YES:-}" != "1" ]; then
    echo "This replaces the '$DB' database in project '$(docker compose config --format json \
        | python3 -c 'import sys, json; print(json.load(sys.stdin)["name"])')' with the one in"
    echo "$DUMP."
    read -r -p "Type 'restore' to go ahead: " answer
    [ "$answer" = "restore" ] || fail "nothing changed"
fi

# --- the restore -------------------------------------------------------------
echo "==> Loading the database"
gunzip -c "$DUMP" \
    | docker compose exec -T -e MYSQL_PWD="${DB_ROOT_PASSWORD:-}" db mariadb -uroot

echo "==> Extracting photographs"
docker compose exec -T api tar -xzf - -C /app < "$IMAGES"

echo "==> Extracting files"
docker compose exec -T api tar -xzf - -C /app < "$FILES"

# --- the checks --------------------------------------------------------------
problems=0
problem() { echo "!! $*"; problems=$((problems + 1)); }

echo "==> Checking the database against the dump"
# Rows per table, counted from the dump. mariadb-dump writes each table's rows as
# one INSERT with every tuple on a line of its own starting "(", which is also
# how backup/pull-backup.sh counts them. A table with no rows has no INSERT.
dump_counts="$(gunzip -c "$DUMP" | awk '
    /^CREATE TABLE `/ { split($0, a, "`"); t = a[2]; n[t] += 0 }
    /^INSERT INTO `/ { split($0, a, "`"); t = a[2]; inblock = 1; next }
    inblock && /^\(/ { n[t]++ }
    inblock && /;[[:space:]]*$/ { inblock = 0 }
    END { for (t in n) print t, n[t] }' | sort)"
[ -n "$dump_counts" ] || problem "found no tables in the dump"

# </dev/null matters: `docker compose exec` reads standard input, and inside the
# loop below that is the list of tables still to check. Without it the first
# check swallows the rest, and the restore reports one table checked and calls
# that a pass.
sql() {
    docker compose exec -T -e MYSQL_PWD="${DB_ROOT_PASSWORD:-}" db \
        mariadb -uroot -N -B "$DB" -e "$1" </dev/null
}
checked=0
while read -r table want; do
    checked=$((checked + 1))
    got="$(sql "SELECT COUNT(*) FROM \`$table\`")" || { problem "$table: not in the database"; continue; }
    if [ "$got" = "$want" ]; then
        printf '    %-28s %6s rows\n' "$table" "$got"
    else
        problem "$table: $got rows in the database, $want in the dump"
    fi
done <<<"$dump_counts"
tables="$(wc -l <<<"$dump_counts" | tr -d ' ')"
[ "$checked" = "$tables" ] || problem "checked $checked of the $tables tables in the dump"

want_version="$(gunzip -c "$DUMP" | awk '/^INSERT INTO `alembic_version`/ { getline; print; exit }' \
    | tr -d "();'")"
got_version="$(sql "SELECT version_num FROM alembic_version")"
if [ "$got_version" = "$want_version" ]; then
    echo "    schema version $got_version"
else
    problem "schema version is $got_version, the dump is at $want_version"
fi

echo "==> Checking photographs and files against their archives"
# Every regular file in each archive, by path and size, has to be in the volume at
# that size. Extra files in the volume are not a failure: they were there before.
# Listed through Python's tarfile rather than `tar -tv`, whose columns split a file
# name at its first space -- and "PC1512 manual.pdf" is exactly the kind of name
# the file store holds.
archived_files() {
    python3 -c 'import sys, tarfile
for m in tarfile.open(sys.argv[1]):
    if m.isfile():
        print(m.name, m.size)' "$1"
}
for archive in "$IMAGES" "$FILES"; do
    missing="$(comm -23 \
        <(archived_files "$archive" | sort) \
        <(docker compose exec -T api sh -c \
            'cd /app && find images files -type f -printf "%p %s\n" 2>/dev/null' </dev/null | sort))"
    archived="$(archived_files "$archive" | wc -l | tr -d ' ')"
    if [ -n "$missing" ]; then
        problem "$(basename "$archive"): $(wc -l <<<"$missing" | tr -d ' ') of $archived not restored as archived, e.g.:"
        head -3 <<<"$missing" | sed 's/^/       /'
    else
        echo "    $(basename "$archive"): all $archived present at their archived size"
    fi
done

echo "==> Checking the app answers"
status="$(docker compose exec -T api python -c \
    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/').status)" \
    2>/dev/null || true)"
[ "$status" = "200" ] && echo "    the home page answers 200" \
    || problem "the home page did not answer 200 (got '${status:-nothing}')"

if [ "$problems" -gt 0 ]; then
    echo "==> Restored, with $problems problem(s) above. Do not trust this backup as it stands."
    exit 1
fi
echo "==> Restored and checked: $STAMP"
