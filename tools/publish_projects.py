"""Publish the projects that are still private, one database at a time.

Projects raised from the work box used to start private, on the argument that a
line typed at a bench in five seconds has not been considered for publication.
They start public now (ADR-0004), which leaves the ones already written behind the
tick with nothing about them saying they were meant to be.

Here rather than in a migration, and deliberately so. "Make every private project
public" is a true thing to want on *this* collection and a data breach on somebody
else's: a shared migration that ran it would publish, on every installation that
pulled the update, whatever its owner had decided nobody else should read. That is
exactly the shape ADR-0002 keeps out of the migration history -- a one-off
correction to the rows of one database -- so it is a script somebody runs on
purpose, on the database they own.

Dry run by default; --write to do it. It goes through the API rather than the
database so the register does its own bookkeeping: publishing writes the "wanted
for <name>" line into the history of every item the project is about, which is the
half of publishing that a bare UPDATE would skip.

    python3 tools/publish_projects.py                 # say what it would do
    python3 tools/publish_projects.py --write         # do it
    python3 tools/publish_projects.py --write --only RH-01HT RH-C1HF

On the server, with the stack up:

    docker compose exec api python /app/../tools/publish_projects.py --write

or from the repo root with RHDB_API pointing at it. Reverse it on any project by
ticking `private` again on its own form.
"""

import argparse
import sys

import rhdb


def private_projects():
    return [p for p in rhdb._request("GET", "/api/projects") if p.get("private")]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--write", action="store_true", help="actually publish (default: say what would change)"
    )
    parser.add_argument(
        "--only", nargs="*", metavar="RH-XXXX", default=[], help="only these projects, by asset id"
    )
    rhdb.add_api_arg(parser)
    args = parser.parse_args(argv)
    rhdb.apply_api_arg(args)

    wanted = {a.strip().upper() for a in args.only}
    rows = [p for p in private_projects() if not wanted or p["asset_id"] in wanted]
    if not rows:
        print("Nothing private to publish.")
        return 0
    for p in rows:
        print(f"  {p['asset_id']}  {p['name']}")
    if not args.write:
        print(f"\n{len(rows)} project(s) would be published. Re-run with --write.")
        return 0
    for p in rows:
        rhdb._request("PATCH", f"/api/projects/{p['asset_id']}", json={"private": False})
    print(f"\nPublished {len(rows)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
