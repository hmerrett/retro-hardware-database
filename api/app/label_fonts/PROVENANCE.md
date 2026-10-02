# The faces a label can be set in

`label_font.ttf` beside this directory is Audiowide, which every label was set in
before there was a choice. These are the other answer to **Settings → Labels →
Type**: the interface face of the look the site wears (MANUAL §13, "The type on a
label"), which is IBM Plex Sans or IBM Plex Mono.

They are here as TrueType because the PDF renderer reads nothing else. The site
already serves the same faces as WOFF2 for the browser (static/fonts/); these are
the same fonts in the format reportlab and Pillow open.

| | |
|---|---|
| Faces | IBM Plex Sans and IBM Plex Mono, Regular and SemiBold |
| Licence | SIL Open Font License 1.1 -- see `OFL.txt` |
| Source | `https://registry.npmjs.org/@ibm/plex-sans/-/plex-sans-1.1.0.tgz` and `https://registry.npmjs.org/@ibm/plex-mono/-/plex-mono-2.5.0.tgz`, files `package/fonts/complete/woff/IBMPlex{Sans,Mono}-{Regular,SemiBold}.woff`; each tarball checked against the sha512 the registry publishes |
| Conversion | WOFF 1 to TrueType with fontTools 4.60.1: `TTFont(src); flavor = None; save(dst)`. WOFF 1 is the font's own tables, zlib-compressed; nothing is redrawn or subset |

| File | sha256 of the WOFF it came from | sha256 of the file |
|---|---|---|
| `IBMPlexSans-Regular.ttf` | `b731cf56514a4bd711ab2f9acf641f9311707f4386772eb306d25c2b29b73b1a` | `34e0eb31973abf1a909a28b0736ae2d84e1914177effbb319dd8794f52450865` |
| `IBMPlexSans-SemiBold.ttf` | `fff45f420f0d026b4a39f99b3bfc47dfc06561c598c8db825cfce5fd706bda7a` | `7468fe4b891e3c469bd9a83048184dc86552175eb143f4ebe299496ae5e0d227` |
| `IBMPlexMono-Regular.ttf` | `3a0d6e1587e8dc784be5a75e1c55b1a5533919b04072a29c750bb29cfe4a4b74` | `278f98c30db9c71a7dc6fba065064cab4f31c9b1c3cf91bac40727d438b19a8f` |
| `IBMPlexMono-SemiBold.ttf` | `7fb3daa74f03d2c9f4e092b9f1b8f2cdb301eafeba0d0af375d856d44dce3327` | `41f671881c7aab7c965d612f286a1c98ea4b00cf30834e2044426b95f960b6dd` |
