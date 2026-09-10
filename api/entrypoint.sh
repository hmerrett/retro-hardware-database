#!/bin/sh
# Bring the schema to head, then start the app.
set -e

alembic upgrade head
# --forwarded-allow-ips: trust the proxy's X-Forwarded-Proto, so the app knows a
# request arrived over HTTPS. Without it uvicorn trusts 127.0.0.1 alone, Caddy
# reaches us from a container address on the compose network, and every absolute
# redirect the app builds -- the trailing-slash redirect that /items/<id>/ takes,
# which is exactly what a printed QR label encodes -- comes back as http://. It
# still arrives, because Caddy bounces it up again, but the scan makes a cleartext
# hop first. "*" is the whole of what can reach this port: the app is published on
# 127.0.0.1 only and Caddy is the sole route to it.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips="*"
