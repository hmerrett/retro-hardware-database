#!/usr/bin/env bash
# Build the site, commit everything, and push — in one go.
#
# With no argument: build, commit with an auto message, then push.
#   ./publish.sh
# With an argument: build, commit with that message, then push.
#   ./publish.sh "Add Amiga 1200"
#
# GitHub Actions then rebuilds and redeploys the live site.
set -euo pipefail

# Always run from the repo root (the folder this script lives in).
cd "$(dirname "$0")"

# Use the project virtualenv if it's there, otherwise system python.
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

echo "==> Optimising images"
"$PY" scripts/process_images.py

echo "==> Building site"
"$PY" scripts/build_site.py

echo "==> Staging changes"
git add -A

if git diff --cached --quiet; then
  echo "No new changes to commit."
else
  MSG="${*:-Update catalogue ($(date '+%Y-%m-%d %H:%M'))}"
  echo "==> Committing: $MSG"
  git commit -m "$MSG"
fi

# Always push, so any earlier unpushed commits go up too (no-op if up to date).
echo "==> Pushing"
git push

echo "==> Done. GitHub Actions will rebuild and redeploy the site shortly."
