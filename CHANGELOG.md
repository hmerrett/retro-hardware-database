# Changelog

What changed, newest first, written for somebody who runs this rather than
somebody reading the diff. A line goes in when an installation would notice it: a
new feature, a change to how something already works, a fix, or a step an upgrade
has to take by hand. Work with no outward face — a router extraction, a lockfile,
a test — stays in the git history, which is where it is useful.

Versions are [semantic](https://semver.org), and the version has one home,
`api/app/__init__.py`. Upgrading is `./deploy.sh`: migrations run as the app
starts, so a schema change needs no step of its own. Anything that does need a
hand is written under the release that needs it.

## 0.1.0 — 2026-09-18

The first release, and so not a list of changes: there is nothing before it to
have changed from. What it is, in one paragraph, is a self-hosted register for a
collection of old computers — every machine, card, drive and chip with an asset
tag, a page, photographs, files and a dated history; a QR label you print and
stick on the thing; browsing public and editing behind one login; a JSON API and
a command-line toolkit beside the web pages. [README.md](README.md) says what it
is for, [MANUAL.md](MANUAL.md) what every part of it does, and
[INSTALL.md](INSTALL.md) how to run your own.

[ROADMAP.md](ROADMAP.md) has what comes after it.

**Installing it for the first time:** follow [INSTALL.md](INSTALL.md) from the
top. Set `RHDB_BASE_URL` before printing any labels — it is what their QR codes
encode — and set `RHDB_AUTH_USER` and `RHDB_AUTH_PASSWORD`, or the site is
world-editable and says so on every page.
