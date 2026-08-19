#!/usr/bin/env python3
"""Write catalogue.txt: every machine the catalogue names, as plain text.

The catalogue itself is api/app/machines.yaml, which is the thing to edit and the
thing to read if you want the detail -- the board issues, the chip sockets, the
memory sizes. This is the other question, the one asked far more often: what is in
it? Makers and machines, nothing else, in a file you can open anywhere.

    python tools/catalogue_list.py            # rewrite catalogue.txt
    python tools/catalogue_list.py --check    # is it in step? (this is a test too)

Being generated, it can go stale the moment a machine is added, so a test asserts
it has not (test_machines.TestTheListOfWhatIsInIt). Add a machine, run this, commit
both.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "catalogue.txt"
sys.path.insert(0, str(ROOT / "api"))

WIDTH = 70


def render(families):
    """The whole file as one string."""
    models = sum(len(f["models"]) for f in families)
    makers = {f["manufacturer"] or f["name"] for f in families}
    years = [m["year"] for f in families for m in f["models"]]

    out = ["THE MACHINE CATALOGUE", "=" * WIDTH, ""]
    out.append(textwrap.fill(
        f"Every machine the register knows as a model -- home computers, consoles"
        f" and the branded PCs that were sold under a model name: {models}"
        f" machines from {len(makers)} makers, {min(years)} to {max(years)}. Filing"
        " a machine against one of these fills in what is already known about the"
        " model, and asks only what differs between two of the same -- the board"
        " issue, the case, the region, the chips in the sockets.", WIDTH))
    out.append("")
    out.append(textwrap.fill(
        "Listed alphabetically by maker, and alphabetically within each maker."
        " Where a machine was built by someone other than the maker it is filed"
        " under, that is given in brackets. The catalogue itself is"
        " api/app/machines.yaml; this list is generated from it by"
        " tools/catalogue_list.py.", WIDTH))
    out.append("")

    for family in families:
        maker = family["manufacturer"] or family["name"]
        # One maker with more than one family -- Apple's II line and its Macintosh,
        # Commodore's three -- says which of them this is.
        head = maker if family["name"] in (maker, maker + " ZX") \
            else f"{maker}  ({family['name']})"
        names = []
        for model in family["models"]:
            own = model.get("manufacturer")
            names.append(f"{model['model']} [{own}]" if own and own != maker
                         else model["model"])
        out += ["", f"{head}   -- {len(names)}", "-" * WIDTH,
                textwrap.fill(", ".join(names), WIDTH, initial_indent="  ",
                              subsequent_indent="  ")]
    out.append("")
    return "\n".join(out) + "\n"


def main(argv=None):
    from app import machines
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--check", action="store_true",
                      help="exit 1 if catalogue.txt is not what this would write")
    opts = args.parse_args(argv)

    wanted = render(machines.FAMILIES)
    if not opts.check:
        OUT.write_text(wanted, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    have = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if have == wanted:
        print(f"{OUT.relative_to(ROOT)} is in step with the catalogue")
        return 0
    print(f"{OUT.relative_to(ROOT)} is out of step -- run"
          " `python tools/catalogue_list.py`", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
