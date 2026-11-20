"""A survey's report, read (MANUAL §23, "What a report says"; ADR-0043).

A survey program writes a report for a person to read, and ends it with a section for
the register: a line `[RHDB]`, then one `KEY=VALUE` to a line. This reads that section
and nothing else, so a program may say what it likes above it, and a key the register
does not know is carried and ignored. A file may hold several reports one after
another -- a program that adds each run to the end of the same file writes exactly
that -- and each is a survey of its own.

Nothing here touches the database: what a report says is settled before anything is
looked up, and a machine's question before its tests is read the same way.
"""

import re
from dataclasses import dataclass

SECTION = "[RHDB]"

# A key as the reports write them: capitals, digits and underscores, starting with a
# letter. A line that is not one ends the section, which is how the next report's own
# words, a blank line or the end of the file closes it.
_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


class Unreadable(ValueError):
    """A report the register cannot read, and why, in words for the agent to leave
    beside it."""


@dataclass(frozen=True)
class Report:
    """One report: its text as the program wrote it, and its keys as written."""

    text: str
    keys: dict[str, str]


def decode(raw: bytes) -> str:
    """A report's bytes as text. Most are DOS text in code page 437, which is what a
    file that is not UTF-8 is read as everywhere else in the register."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp437")


def _section(lines: list[str], start: int) -> tuple[dict[str, str], int]:
    """The keys of the section whose `[RHDB]` line is `start`, and the line after it."""
    keys: dict[str, str] = {}
    at = start + 1
    while at < len(lines):
        found = _LINE.match(lines[at].strip())
        if found is None:
            break
        keys[found.group(1)] = found.group(2).strip()
        at += 1
    return keys, at


def read(text: str) -> list[Report]:
    """Every report in a file, in order. Raises Unreadable for a file with no
    `[RHDB]` section, or one whose section says nothing."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[Report] = []
    begun = at = 0
    while at < len(lines):
        if lines[at].strip().upper() != SECTION:
            at += 1
            continue
        keys, after = _section(lines, at)
        if not keys:
            raise Unreadable("Its [RHDB] section has nothing in it.")
        body = "\n".join(lines[begun:after]).strip("\n")
        out.append(Report(text=body + "\n", keys=keys))
        begun = at = after
    if not out:
        raise Unreadable("It has no [RHDB] section.")
    return out


def question(text: str) -> dict[str, str]:
    """A machine's question before its tests: the lines a report would hold about
    what it has found so far, with or without the `[RHDB]` line above them."""
    keys: dict[str, str] = {}
    for line in text.replace("\r", "\n").split("\n"):
        found = _LINE.match(line.strip())
        if found is not None:
            keys[found.group(1)] = found.group(2).strip()
    return keys
