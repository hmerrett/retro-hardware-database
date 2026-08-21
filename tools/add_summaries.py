#!/usr/bin/env python3
"""Write `summary:` paragraphs into api/app/machines.yaml from a mapping.

The catalogue is hand-edited and heavily commented, so it is patched line by line
rather than loaded and dumped: round-tripping it through a YAML writer would
reflow four hundred models and throw away every comment in the file, which is
most of what makes it editable by a person.

    python3 tools/add_summaries.py summaries/acorn.py

The argument is a Python file defining SUMMARIES = {model_key: paragraph}. A key
already carrying a summary is left alone unless --replace is given, so a rerun
adds only what is new.
"""
import argparse
import pathlib
import re
import runpy
import sys
import textwrap

YAML = pathlib.Path(__file__).resolve().parent.parent / "api/app/machines.yaml"
WIDTH = 88          # the file's own comment width, so a summary reads like the rest


def fold(text, indent):
    """One paragraph as a YAML folded block, wrapped to the file's width."""
    body = " ".join(text.split())
    lines = textwrap.wrap(body, width=WIDTH - len(indent) - 2)
    return [f"{indent}summary: >-"] + [f"{indent}  {ln}" for ln in lines]


def apply(lines, summaries, replace=False):
    out, done, skipped, i = [], [], [], 0
    key_at = re.compile(r"^(\s*)- key: (\S+)\s*$")
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = key_at.match(line)
        if not m:
            i += 1
            continue
        dash_indent, key = m.group(1), m.group(2)
        field = dash_indent + "  "          # fields sit two in from the dash
        if key not in summaries:
            i += 1
            continue
        # The model's own block: up to the next line at or left of the dash.
        j = i + 1
        while j < len(lines) and (not lines[j].strip()
                                  or lines[j].startswith(field)):
            j += 1
        block = lines[i + 1:j]
        has = any(ln.startswith(field + "summary:") for ln in block)
        if has and not replace:
            skipped.append(key)
            i += 1
            continue
        if has:
            raise SystemExit(f"{key}: --replace on an existing summary is not"
                             " implemented; edit the YAML by hand")
        # After `model:`, which every model has: the name, then what it is.
        at = next((n for n, ln in enumerate(block)
                   if ln.startswith(field + "model:")), None)
        if at is None:
            raise SystemExit(f"{key}: no 'model:' line to write the summary after")
        out.extend(block[:at + 1])
        out.extend(fold(summaries[key], field))
        out.extend(block[at + 1:])
        done.append(key)
        i = j
    return out, done, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="a .py file defining SUMMARIES = {key: text}")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    summaries = runpy.run_path(args.source)["SUMMARIES"]
    lines = YAML.read_text(encoding="utf-8").split("\n")
    out, done, skipped = apply(lines, summaries, args.replace)

    missing = sorted(set(summaries) - set(done) - set(skipped))
    if missing:
        raise SystemExit(f"not in the catalogue: {', '.join(missing)}")
    print(f"{len(done)} written, {len(skipped)} already had one")
    if skipped:
        print("  already had one:", ", ".join(skipped))
    if not args.dry_run:
        YAML.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
