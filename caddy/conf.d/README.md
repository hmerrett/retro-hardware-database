# Extra Caddy configuration for this installation

The `Caddyfile` beside this directory is the same for everybody: it serves
`{$RHDB_DOMAIN}` and proxies it to the app. Anything true of one deployment only
goes in a `*.caddy` file in here, and those are not in git — the same rule `.env`
follows, and for the same reason.

Caddy imports every `*.caddy` in this directory at the top level, so a file here
holds whole site blocks. What that is usually for:

```caddyfile
# A domain the register used to live at, or a bare domain in front of a www.
# {uri} rather than a bare host, so a path survives the trip and an old link lands
# on the thing it was pointing at rather than on the front page.
example.com, www.example.com {
	redir https://db.example.com{uri} permanent
}
```

Each extra name needs its own certificate, which needs its own A record pointing
at this host first: the challenge is fetched over HTTP from wherever the name
resolves to, so until it resolves here the answer comes from somewhere else or
from nowhere. Caddy retries in the background and says which it is in its log — a
refused connection means the name still points at the old host, NXDOMAIN means
there is no record yet. The main site is unaffected throughout: a certificate that
cannot be had for one name does not disturb another.

`empty.caddy` is here so the import glob always matches something. Leave it.

**Caddy does not reload these on its own.** After adding or changing a file:

```sh
docker compose up -d --force-recreate caddy
```
