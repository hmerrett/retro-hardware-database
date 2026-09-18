#!/usr/bin/env python3
"""Propose a catalogue model for each machine that has not got one, and file the
ones you agree with.

Most of the register was typed before the catalogue existed: a manufacturer and a
model in two free-text boxes, which is how a person writes down what is on the
badge. The catalogue knows a lot of those machines as models, and filing one
against its model is what makes the register able to ask about board issues and
chips. This introduces the two, one machine at a time.

    python tools/adopt_machines.py             # go through them, asking
    python tools/adopt_machines.py --list      # the report only; writes nothing
    python tools/adopt_machines.py RH-0001     # just this one

WHAT IT WRITES, AND WHAT IT WILL NOT. Confirming a match writes one thing: the
model key. Not the manufacturer, not the model, not the year, not the CPU -- the
machine in front of you is the authority on those and the catalogue is a starting
point, so where the two disagree the disagreement is printed and the record is
left exactly as it is. Two IBM 5170s in this register are dated 1985 and 1988;
the catalogue says the AT came out in 1984, and all three are true.

It never guesses. Nothing is filed without somebody typing the number of the
match, and a machine the catalogue does not know is left uncatalogued -- which is
a correct state and not a failure. A whitebox clone has nothing to be filed as.

Disposed machines are left out: cataloguing a record of something that has gone
is work nobody needs. Boards are left out too -- a motherboard can carry a model
key (that is what the catalogue's board side is for), but a board is filed by
reading it, not by matching a name typed on a shelf.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import machines  # noqa: E402

# rhdb is imported inside main() rather than here. Everything above it -- the
# sieve, the proposal, the wording of a line -- is a question about dictionaries
# and the catalogue, and is tested as such; only actually talking to the register
# needs the HTTP stack, and a report you cannot reason about without a server
# running is a report nobody checks.

# How many candidates a machine is offered. Three is enough for the case this is
# really for -- an Amstrad PC1640 sitting between the PC1512 and the PPC640 -- and
# few enough that reading them is quicker than reading the machine's own badge.
SHOWN = 3


def unfiled(computers, only=None):
    """The machines this report is about: still here, no catalogue model, and the
    one asked for if one was."""
    out = []
    for c in computers:
        if c.get("disposed"):
            continue
        if (c.get("machine") or {}).get("model_key"):
            continue
        if only and c["asset_id"].upper() != only.upper():
            continue
        out.append(c)
    return out


def report(computer):
    """One machine's line in the report: what is typed, and what the catalogue
    thinks it might be."""
    found = machines.suggest(computer.get("manufacturer", ""), computer.get("model", ""), SHOWN)
    return [
        {
            "key": key,
            "score": score,
            "exact": exact,
            "name": machines.full_name(key),
            "year": machines.model(key)["year"],
            "differs": machines.disagreements(key, computer),
        }
        for key, score, exact in found
    ]


def describe(computer):
    """The typed record, as the fields the catalogue has an opinion about."""
    bits = [
        f"{k}={computer[k]}" for k in ("manufacturer", "model", "year", "cpu") if computer.get(k)
    ]
    return ", ".join(bits) or "(nothing typed)"


def show(computer, name, found):
    print(f"\n=== {computer['asset_id']}  {name} ===")
    print(f"  typed: {describe(computer)}")
    if not found:
        print("  the catalogue knows nothing like it — leave it uncatalogued")
        return
    for n, m in enumerate(found, 1):
        mark = "the same name" if m["exact"] else f"{round(100 * m['score'])}% alike"
        print(f"  {n}) {m['name']} ({m['year']})  [{m['key']}]  — {mark}")
        for field, mine, theirs in m["differs"]:
            print(
                f"       {field}: the record says {mine!r},"
                f" the catalogue says {theirs!r} — the record stands"
            )


def ask(found):
    """Which match to file, or None. Anything that is not one of the numbers is a
    no, because the wrong answer to this question is filing something."""
    try:
        answer = input(f"  file as which? (1-{len(found)}, blank to skip): ").strip()
    except EOFError:
        return None
    if answer.isdigit() and 1 <= int(answer) <= len(found):
        return found[int(answer) - 1]
    return None


def main(argv=None):
    from rhdb import add_api_arg, apply_api_arg, display_name, load_computers, update_computer

    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    add_api_arg(ap)
    ap.add_argument(
        "only",
        nargs="?",
        default=None,
        help="just this asset id (default: every uncatalogued machine)",
    )
    ap.add_argument(
        "--list", action="store_true", dest="listing", help="print the report and write nothing"
    )
    args = ap.parse_args(argv)
    apply_api_arg(args)

    computers = load_computers()
    todo = unfiled(computers, args.only)
    if not todo:
        print(
            "Every machine still here is filed against a catalogue model."
            if not args.only
            else f"No uncatalogued machine {args.only}."
        )
        return 0

    filed = offered = 0
    for computer in todo:
        found = report(computer)
        show(computer, display_name(computer), found)
        if not found:
            continue
        offered += 1
        if args.listing:
            continue
        chosen = ask(found)
        if not chosen:
            print("  left uncatalogued.")
            continue
        # The one field this writes. `machine` is the nested shape the API takes
        # for a catalogue identity, and naming only model_key in it leaves the
        # board issue, the style, the region and the chips alone -- which for a
        # machine nobody has opened is exactly right: unanswered, not answered no.
        update_computer(computer["asset_id"], {"machine": {"model_key": chosen["key"]}})
        print(f"  filed as {chosen['name']}.")
        filed += 1

    print(
        f"\n{len(todo)} machine(s) with no catalogue model, {offered} with"
        f" something to offer, {filed} filed."
    )
    if args.listing and offered:
        print("Nothing was written — run it without --list to go through them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
