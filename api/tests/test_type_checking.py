"""mypy's settings say what they claim to, and the ways round them stay shut.

CI runs mypy itself; what it cannot see is whether the arrangement around it is
still the one that was agreed. Every module is strict, and there is no list of
modules excused from it (backend-standards) -- there was one while the code was
being typed, and the quiet way for strict to stop meaning anything is for that
list to come back one module at a time. And mypy will accept
``# type: ignore[code]`` from anybody: that it names its error is configured, that
it says why is not something a type checker can ask.
"""

import re
import tomllib
from pathlib import Path

API = Path(__file__).resolve().parent.parent
APP = API / "app"
MYPY = tomllib.loads((API / "pyproject.toml").read_text())["tool"]["mypy"]


def test_mypy_is_strict_with_the_ways_round_it_closed():
    assert MYPY["strict"] is True
    assert MYPY["warn_unused_ignores"] is True
    assert MYPY["disallow_any_explicit"] is True
    assert "ignore-without-code" in MYPY["enable_error_code"]


def test_no_module_is_excused_from_strict():
    """One override stands, and what it relaxes is not a strictness flag: pydantic's
    own constructor takes ``**data: Any``, and mypy reports every model for it."""
    relaxed = {
        name: {k: v for k, v in override.items() if k != "module"}
        for override in MYPY.get("overrides", [])
        for name in override["module"]
    }
    assert relaxed == {"app.schemas": {"disallow_any_explicit": False}}


def test_a_typed_module_may_not_call_into_an_untyped_one():
    """``untyped_calls_exclude`` was how a typed module was allowed to call one that
    was not there yet. Nothing is not there yet."""
    assert not MYPY.get("untyped_calls_exclude")


def test_a_type_ignore_says_why_on_the_line_above_it():
    unexplained = []
    for path in sorted(APP.rglob("*.py")):
        lines = path.read_text().splitlines()
        for n, line in enumerate(lines):
            if not re.search(r"#\s*type:\s*ignore", line):
                continue
            above = lines[n - 1].strip() if n else ""
            if not above.startswith("#"):
                unexplained.append(f"{path.relative_to(API)}:{n + 1}")
    assert unexplained == []
