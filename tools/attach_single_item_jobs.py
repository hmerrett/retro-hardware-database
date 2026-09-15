"""Attach a project's jobs to its one thing, where it has only one.

`project_task.asset_id` arrived with ADR-0016, so an item's Work panel lists the
jobs written against that item. Every job written before it names nothing, which
leaves the panel empty on every thing in the register -- correct, and useless.

Where a project is about exactly one thing, a job on it that names nothing is
about that thing: there is nothing else it could be about. This attaches those.
Projects about two or more things are left alone, because "which of these is
'strip and clean' about?" is a question only the owner can answer, and guessing
would put the job on the wrong machine's page where it reads as fact.

Here rather than in a migration, for the reason publish_projects.py is. Moving a
column's contents is mechanical and belongs in the migration history; this is a
judgement about what somebody meant, and on another collection it might be wrong --
an owner may have left jobs unattached on purpose. ADR-0002 keeps that shape out of
the shared history, so it is a script somebody runs on the database they own.

Jobs already naming something are never touched, so running it twice is safe and
it will not overwrite a choice made by hand.

Dry run by default; --write to do it. Through the API rather than the database, so
the register does its own bookkeeping -- attaching writes a line into the project's
history saying what the job is about.

    python3 tools/attach_single_item_jobs.py            # say what it would do
    python3 tools/attach_single_item_jobs.py --write    # do it
    python3 tools/attach_single_item_jobs.py --write --only RH-MGSZ

On the server, with the stack up, or from the repo root with RHDB_API pointing at
it. Reverse any of them by setting the job back to "the project" on its own page.
"""
import argparse
import sys

# rhdb is imported where it is used rather than here, unlike the other scripts in
# this directory. It pulls in `requests`, which lives in tools/requirements.txt and
# not in the API's -- and `pick` below, the only part of this worth testing, needs
# no HTTP client to run. Importing it at the top would mean the rule could only be
# tested from an environment built to talk to the API.


def pick(details):
    """[(project, item_id, [task, ...])] out of whole project records: the ones
    about exactly one thing that have jobs naming nothing.

    Taking records rather than fetching them so the rule can be tested on its own.
    It is the only part of this script that decides anything, and deciding wrongly
    puts a job on the wrong machine's page where it reads as fact."""
    out = []
    for full in details:
        items = full.get("items") or []
        if len(items) != 1:
            continue
        loose = [t for t in (full.get("tasks") or []) if not t.get("asset_id")]
        if loose:
            out.append((full, items[0]["asset_id"], loose))
    return out


def candidates(only=()):
    import rhdb
    ids = [p["asset_id"] for p in rhdb._request("GET", "/api/projects")
           if not only or p["asset_id"] in only]
    return pick(rhdb._request("GET", f"/api/projects/{i}") for i in ids)


def main(argv=None):
    import rhdb
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true",
                        help="actually attach (default: say what would change)")
    parser.add_argument("--only", nargs="*", metavar="RH-XXXX", default=[],
                        help="only these projects, by asset id")
    rhdb.add_api_arg(parser)
    args = parser.parse_args(argv)
    rhdb.apply_api_arg(args)

    rows = candidates({a.strip().upper() for a in args.only})
    if not rows:
        print("Nothing to attach: no single-item project has a job naming nothing.")
        return 0
    n = 0
    for project, item_id, tasks in rows:
        print(f"  {project['asset_id']}  {project.get('name', '')}  -> {item_id}")
        for t in tasks:
            print(f"      {t['text'][:70]}")
            n += 1
    if not args.write:
        print(f"\n{n} job(s) on {len(rows)} project(s) would be attached. "
              "Re-run with --write.")
        return 0
    for project, item_id, tasks in rows:
        for t in tasks:
            rhdb._request("PATCH",
                          f"/api/projects/{project['asset_id']}/tasks/{t['id']}",
                          json={"asset_id": item_id})
    print(f"\nAttached {n} job(s) on {len(rows)} project(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
