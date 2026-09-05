# Your own branding

What ships under `api/app/static/` is a placeholder: a beige machine with a bare
prompt on its screen, which says "retro hardware" and nothing about whose
collection this is. Drop a file in **this directory** under the same name and it is
served instead — the app looks here first and falls through to what ships.

Nothing in here is in git (`.gitignore` keeps everything but this README out), and
that is the point: an installation's branding belongs to the installation.

## The one file worth replacing

```
branding/app-icon.png      your mark, square-ish, with transparency
```

Then build the rest from it, which is every size the pages ask for plus the photo
watermark and the social share card:

```sh
docker run --rm -v "$PWD/branding:/static" -v "$PWD/tools:/tools" \
    retro-hardware-db-2-api python /tools/make_icons.py
docker compose up -d --force-recreate api
```

That writes `favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`,
`apple-touch-icon.png`, `icon-192.png`, `icon-512.png`, `logo-256.png`,
`logo-512.png` and `og-image.png` into this directory, all cropped from your
artwork. Replace any of them by hand instead if you would rather.

## What each one is

| File | Where it shows |
|---|---|
| `logo-256.png` | the mark in the site header |
| `logo-512.png` | the watermark composited into the corner of your own photographs |
| `og-image.png` | the card a shared link draws in Slack, Discord, iMessage |
| `favicon.ico`, `favicon-*.png` | the browser tab |
| `apple-touch-icon.png` | an iOS home-screen shortcut (flattened on white) |
| `icon-192.png`, `icon-512.png` | the installable web-app icon |

## Restart after changing anything

The version stamps that let icons and watermarks be cached for a year are hashes
of the artwork, read once at start-up — so a change here is picked up on restart
(`docker compose up -d --force-recreate api`) and not before. Photographs already
served carry the old watermark until they are re-fetched; the watermark cache is
keyed by the artwork's hash, so it rebuilds itself rather than serving a mixture.
