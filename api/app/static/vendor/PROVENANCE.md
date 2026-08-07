# Vendored third-party code

Everything else in this project's front end is inline in the templates. This
directory is the exception, and exists so that what is here can be audited without
reading 250KB of someone else's bundle.

Served from our own origin, never a CDN: a script tag pointing at someone else's
host would let them change what runs on this site, and would tell them who is
looking at it.

## jsqr-1.4.0.js

Decodes a QR code from camera frames, for the scan button on the gallery's search
bar. Loaded on demand when that button is first pressed, not on page load — it is
the largest single asset on the site and most visits never need it.

| | |
|---|---|
| Package | [`jsqr`](https://www.npmjs.com/package/jsqr) 1.4.0 (upstream: [cozmo/jsQR](https://github.com/cozmo/jsQR)) |
| Licence | Apache-2.0 — see `jsqr-1.4.0.LICENSE` |
| Source | `https://registry.npmjs.org/jsqr/-/jsqr-1.4.0.tgz`, file `package/dist/jsQR.js` |
| Tarball sha512 | `dxLob7q65Xg2DvstYkRpkYtmKm2sPJ9oFhrhmudT1dZvNFFTlroai3AWSpLey/w5vMcLBXRgOJsbXpdN9HzU/A==` (as published by the registry) |
| File sha256 | `bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859` |

Unmodified from the published package. It is the unminified build; the package
ships no minified one, and there is no build step here to make one.

Checked before it went in: it is a webpack UMD bundle that does arithmetic on pixel
data, with no `XMLHttpRequest`, `fetch`, `WebSocket`, `eval`, `new Function`,
`innerHTML`, `document.write` or storage access anywhere in it.

### Re-fetching or upgrading

```sh
curl -sSL -o jsqr.tgz https://registry.npmjs.org/jsqr/-/jsqr-<version>.tgz
# Check the sha512 against what the registry publishes for that version:
#   curl -s https://registry.npmjs.org/jsqr | python3 -c \
#     'import json,sys; print(json.load(sys.stdin)["versions"]["<version>"]["dist"]["integrity"])'
tar xzf jsqr.tgz package/dist/jsQR.js package/LICENSE
```

Then update the version in the filename, the table above, and the `JSQR_SRC`
constant in `templates/index.html`.
