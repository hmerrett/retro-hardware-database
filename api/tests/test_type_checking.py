"""mypy's settings say what they claim to, and the ways round them stay shut.

CI runs mypy itself; what it cannot see is whether the arrangement around it is
still the one that was agreed. Strict is the default and the modules not yet
typed are a named list (backend-standards) -- so the list has to be made of
modules that exist, or it becomes a place to park a name for later. And mypy
will accept ``# type: ignore[code]`` from anybody: that it names its error is
configured, that it says why is not something a type checker can ask.
"""

import re
import tomllib
from pathlib import Path

API = Path(__file__).resolve().parent.parent
APP = API / "app"
MYPY = tomllib.loads((API / "pyproject.toml").read_text())["tool"]["mypy"]


def _not_yet_strict():
    """The modules the relaxing override names -- the one that switches
    ``disallow_untyped_defs`` off, which is what not being strict comes down to."""
    for override in MYPY.get("overrides", []):
        if override.get("disallow_untyped_defs") is False:
            return list(override["module"])
    return []


def test_mypy_is_strict_with_the_ways_round_it_closed():
    assert MYPY["strict"] is True
    assert MYPY["warn_unused_ignores"] is True
    assert MYPY["disallow_any_explicit"] is True
    assert "ignore-without-code" in MYPY["enable_error_code"]


def test_every_module_excused_from_strict_is_a_module_that_exists():
    for name in _not_yet_strict():
        path = API / Path(*name.split("."))
        assert path.with_suffix(".py").is_file(), f"{name} is excused from strict and is not there"


def test_no_package_is_excused_wholesale():
    """``app.routers.*`` would excuse every router written from now on."""
    assert not [name for name in _not_yet_strict() if "*" in name]


def test_calls_into_untyped_code_are_allowed_only_into_the_excused_modules():
    """The two lists are one list written twice, because mypy wants it twice. If
    they part, a typed module is either blocked by a callee that is excused or
    free to call something that is supposed to be checked."""
    assert sorted(MYPY.get("untyped_calls_exclude", [])) == sorted(_not_yet_strict())


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
