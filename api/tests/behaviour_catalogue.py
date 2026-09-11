"""Render the test suite as a document describing what the software does.

Not a test. The helper behind `test_architecture.py`, and the thing that writes
`docs/behaviour.md`.

A description of behaviour written by reading the code is a photograph: it agrees
with the code by construction, and then it rots quietly, because nothing runs it.
A description drawn from the test suite cannot rot, because every line of it is
executed on every push. That is the whole reason the catalogue is generated from
here rather than written by hand -- and the reason a test name is expected to read
like a sentence (testing-standards).
"""
import ast
import re
from pathlib import Path

TESTS = Path(__file__).parent
DOCUMENT = TESTS.parents[1] / "docs" / "behaviour.md"

# The suite's own scaffolding describes nothing about the register.
SKIP = {"conftest.py", "behaviour_catalogue.py"}

HEADER = """# What the software does

Every heading below is a test file; every line under it is a test the suite runs.
This document is **generated** from `api/tests/` -- it is not written by hand and
must not be edited. A test named for the behaviour it describes becomes a
readable line here, which is the practical reason the naming rule exists.

It describes the software as its tests hold it. It is therefore honest about what
is checked and silent about what is not: a behaviour no test covers does not
appear, however important it is. For the shape of the system rather than its
behaviours, see `architecture.md`.

Regenerate with:

    RHDB_UPDATE_BEHAVIOUR=1 pytest api/tests/test_architecture.py

"""


def sentence(name: str) -> str:
    """`test_a_part_keeps_its_history` -> `a part keeps its history`."""
    return name.removeprefix("test_").replace("_", " ").strip()


def group_name(classname: str) -> str:
    """`TestARegisterAsset` -> `A register asset`.

    Test classes are grouped by subject, and the subject is the heading a reader
    wants; run together as written it is one word and reads as none. Split on the
    case changes, keeping an acronym whole.
    """
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ",
                   classname.removeprefix("Test")).split()
    kept = [w if w.isupper() else w.lower() for w in words]
    return " ".join(kept)[:1].upper() + " ".join(kept)[1:]


def title(filename: str) -> str:
    """`test_project_orders.py` -> `Project orders`."""
    stem = filename.removeprefix("test_").removesuffix(".py").replace("_", " ")
    return stem[:1].upper() + stem[1:]


def summary(node: ast.AST) -> str:
    """The first sentence of a docstring, as one line, or nothing.

    Only the first: the rest is usually the argument for why the behaviour is
    what it is, which belongs beside the test rather than in a catalogue.
    """
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    first = re.split(r"(?<=[.!?])\s", " ".join(doc.split()), maxsplit=1)[0]
    return first.strip()


def entries(source: str) -> list[tuple[str, str, str]]:
    """Every test in one file, as (group, sentence, summary)."""
    found = []
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            group = group_name(node.name)
            for inner in node.body:
                if _is_test(inner):
                    found.append((group, sentence(inner.name), summary(inner)))
        elif _is_test(node):
            found.append(("", sentence(node.name), summary(node)))
    return found


def _is_test(node: ast.AST) -> bool:
    return (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_"))


def render() -> str:
    out = [HEADER]
    total = 0
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name in SKIP:
            continue
        found = entries(path.read_text(encoding="utf-8"))
        if not found:
            continue
        total += len(found)
        out.append(f"\n## {title(path.name)}\n")
        out.append(f"*{path.name} — {len(found)} behaviours*\n")
        group_now = None
        for group, line, note in found:
            if group != group_now:
                group_now = group
                if group:
                    out.append(f"\n**{group}**\n")
            out.append(f"- {line}" + (f"  \n  {note}" if note else ""))
        out.append("")
    out.insert(1, f"\n*{total} behaviours, from {len(list(TESTS.glob('test_*.py'))) - 1} files.*\n")
    return "\n".join(out).rstrip() + "\n"
