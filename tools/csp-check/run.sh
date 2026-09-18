#!/usr/bin/env bash
# Prove the Content-Security-Policy in a browser. ADR-0021.
#
# Brings a throwaway stack up on 127.0.0.1:18080, seeds it with enough of a
# register that the item pages render, drives Chromium over the lot with a
# violation listener attached, and takes the stack down again.
#
# Everything it makes is its own: its own Compose project, its own volumes, its
# own port. It cannot touch an install's data -- but the project name is passed
# explicitly on every command rather than left to the environment, because
# COMPOSE_PROJECT_NAME is exactly the sort of thing that is set somewhere you
# forgot and a stack brought up under the wrong name is not a mistake you notice
# until afterwards.
set -euo pipefail

PROJECT=rhdbcspcheck
# `localhost`, not `127.0.0.1`. The Caddyfile's site address is
# http://localhost:18080, and Caddy matches a site on the Host header: a request
# for 127.0.0.1 matches no site and Caddy answers it itself, 200 with an empty
# body. That is indistinguishable from a working site to anything that only looks
# at the status code -- which is how it was found.
BASE=http://localhost:18080
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENVFILE="$(mktemp)"
trap 'rm -f "$ENVFILE"' EXIT

cat >"$ENVFILE" <<ENV
DB_PASSWORD=csp-check-throwaway
DB_ROOT_PASSWORD=csp-check-throwaway
RHDB_DOMAIN=http://localhost:18080
RHDB_BASE_URL=http://localhost:18080
RHDB_ACME_EMAIL=nobody@example.test
# Open, so the crawl sees the forms and the owner-only pages. This stack is on the
# loopback for two minutes; there is nothing here to protect (ADR-0019).
RHDB_OPEN=1
ENV

compose() {
  docker compose -p "$PROJECT" --env-file "$ENVFILE" \
    -f "$ROOT/docker-compose.yml" -f "$HERE/compose.csp.yml" "$@"
}

# Say what is about to happen before it happens: the one failure this script
# could cause is running against the wrong project, and it is cheap to show.
echo "project: $(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"

cleanup() {
  echo "--- taking the stack down"
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$ENVFILE"
}
trap cleanup EXIT

echo "--- building and starting"
compose up -d --build caddy

echo "--- waiting for the site"
# Waiting for a page with something on it, not for a status code. An empty 200 is
# what a Host mismatch looks like, and a readiness check that accepts one reports
# a healthy site that serves nothing.
ready() { [ "$(curl -sS -o /dev/null -w '%{size_download}' "$BASE/" 2>/dev/null || echo 0)" -gt 500 ]; }
for _ in $(seq 1 90); do ready && break; sleep 2; done
ready || { echo "the site never served a page"; compose logs --tail 40 api caddy; exit 1; }

echo "--- seeding a machine and a part"
# Not `curl -f`: on a 4xx it would exit with the body thrown away, and the body is
# the only thing that says which field the API did not like.
post() {
  local path=$1 body=$2 out status
  out=$(curl -sS -w '\n%{http_code}' -X POST "$BASE$path" \
        -H 'content-type: application/json' -d "$body")
  status=${out##*$'\n'}
  out=${out%$'\n'*}
  if [ "$status" != "200" ]; then
    echo "POST $path answered $status: $out" >&2
    return 1
  fi
  printf '%s' "$out"
}

machine=$(post /api/computers '{"manufacturer":"Amstrad","model":"PC1512"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["asset_id"])')
post /api/parts "{\"type\":\"video\",\"manufacturer\":\"Trident\",\"model\":\"TVGA8900\",\"computer_id\":\"$machine\"}" >/dev/null
echo "    seeded $machine"

echo "--- crawling"
# Sharing Caddy's network namespace, so `localhost:18080` inside the browser is
# the same address the Caddyfile's site block answers to. Reaching it as
# `caddy:18080` would send a Host header that matches no site and get a 404 from
# Caddy itself, which would look like a broken crawl rather than a wrong address.
#
# The image ships the browsers (/ms-playwright) but not the npm package that
# drives them, so that goes in at run time -- with the download skipped, because
# the browsers it would fetch are already in the image. The version matches the
# image tag: the package and the browser build are released together and a
# mismatch is reported as a missing executable.
#
# The script is copied to sit beside the install rather than run from the mount,
# because an ES module resolves a bare import by walking up from its own
# directory, and /crawl has no node_modules above it.
docker run --rm \
  --network "container:${PROJECT}-caddy-1" \
  -v "$HERE:/crawl:ro" \
  -e CSP_BASE=http://localhost:18080 \
  -e "CSP_ITEM=/computers/$machine" \
  -e PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
  mcr.microsoft.com/playwright:v1.56.0-noble \
  sh -c 'cp /crawl/crawl.mjs /tmp/ && cd /tmp && npm install --no-save --no-audit --no-fund --loglevel=error playwright@1.56.0 && node /tmp/crawl.mjs'
