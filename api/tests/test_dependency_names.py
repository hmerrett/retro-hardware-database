"""How the two pyproject files name what they depend on (backend-standards).

Dependabot finds a dependency by the name PyPI normalises it to, lower case with
single hyphens, and rewrites the line that pins it. A line that spells the name
any other way is one it cannot find: it settles on the newer version, rewrites
nothing, and records the update as failed. SQLAlchemy and PyMySQL failed that way
every week from the first run, while the lower-case names around them moved.
"""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _named(project):
    """Every requirement the project's pyproject names: its dependencies and each
    dependency group, but not a group's include of another group."""
    data = tomllib.loads((ROOT / project / "pyproject.toml").read_text())
    groups = data.get("dependency-groups", {}).values()
    return list(data["project"]["dependencies"]) + [
        r for group in groups for r in group if isinstance(r, str)
    ]


@pytest.mark.parametrize("project", ["api", "mcp"])
def test_every_dependency_is_named_as_pypi_normalises_it(project):
    """That is the name Dependabot looks for, and a line it cannot find is a pin it
    never moves."""
    named = _named(project)
    assert named
    names = [re.match(r"[A-Za-z0-9._-]+", r).group(0) for r in named]
    assert [n for n in names if n != re.sub(r"[-_.]+", "-", n).lower()] == []
