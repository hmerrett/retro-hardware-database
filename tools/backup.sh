#!/usr/bin/env bash
#
# Local backup of the Retro Hardware Database.
#
# Writes two timestamped files into ./backups (override with RHDB_BACKUP_DIR):
#   db-<stamp>.sql.gz      the whole MariaDB database (computers + parts)
#   images-<stamp>.tgz     the uploaded photos
#
# Restore (into a running stack):
#   gunzip -c backups/db-<stamp>.sql.gz \
#     | docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db mariadb -uroot
#   docker compose exec -T api tar -xzf - -C /app < backups/images-<stamp>.tgz
#
# The dump carries its own CREATE DATABASE + USE, so it always lands on the live
# database whatever you name on the command line. To inspect a snapshot beside
# the live data, strip those two lines and load it into a scratch database:
#   gunzip -c backups/db-<stamp>.sql.gz | grep -vE '^(CREATE DATABASE|USE )' \
#     | docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db mariadb -uroot scratch
#
# Note: .env (DB + login passwords) is config, not data -- keep a copy of it too
# if you want to restore with the same credentials.
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

DEST="${RHDB_BACKUP_DIR:-backups}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
DB="${DB_NAME:-retro}"

echo "==> Dumping database ($DB)"
docker compose exec -T -e MYSQL_PWD="${DB_ROOT_PASSWORD:-}" db \
    mariadb-dump -uroot --single-transaction --databases "$DB" \
    | gzip > "$DEST/db-$STAMP.sql.gz"

echo "==> Archiving photos"
# The dot-directories under images/ are derived caches -- the watermarked copies
# and the resized ones -- and are rebuilt from the originals on demand. Backing
# them up would roughly double the archive to save nothing.
docker compose exec -T api tar -czf - -C /app --exclude="images/.*" images \
  > "$DEST/images-$STAMP.tgz"

echo "==> Done:"
ls -lh "$DEST/db-$STAMP.sql.gz" "$DEST/images-$STAMP.tgz" | awk '{print "    " $9 "  (" $5 ")"}'
