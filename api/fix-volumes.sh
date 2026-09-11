#!/bin/sh
# Give the photograph and file volumes to the user the app runs as.
#
# Run as root, once per `docker compose up`, by the api-init service, before the
# app starts. A fresh install never needs it: its volumes are created owned by
# appuser (see the Dockerfile). An install from before the app stopped running as
# root has volumes that root owns, and the app would lose the ability to save an
# upload the moment it upgraded -- quietly, as a failed save rather than a failed
# start. So this looks first and changes nothing unless something is wrong, which
# also puts right anything restored into a volume as root.
set -e

for dir in /app/images /app/files; do
    if [ -n "$(find "$dir" \( ! -user appuser -o ! -group appuser \) -print -quit)" ]; then
        echo "==> $dir holds files the app cannot write; giving them to appuser"
        chown -R appuser:appuser "$dir"
    fi
done
