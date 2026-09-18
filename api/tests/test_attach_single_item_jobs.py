"""tools/attach_single_item_jobs.py picks the right jobs to attach.

The script writes to somebody's collection, and the one thing it decides -- which
jobs belong to which thing -- is the thing that would be wrong on their machine's
page for ever if it guessed. So the rule is tested on its own, the way migration
0037's is; the fetching around it is two API calls and nothing to prove.
"""

import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"


def _pick():
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "attach_single_item_jobs", TOOLS / "attach_single_item_jobs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.pick


def project(pid="RH-P1", items=("RH-A",), tasks=()):
    return {
        "asset_id": pid,
        "name": pid,
        "items": [{"asset_id": i} for i in items],
        "tasks": [{"id": n, "text": t, "asset_id": a} for n, (t, a) in enumerate(tasks, start=1)],
    }


def test_a_single_item_projects_loose_jobs_are_picked():
    got = _pick()([project(tasks=[("recap", None), ("new belt", None)])])
    assert len(got) == 1
    _p, item, tasks = got[0]
    assert item == "RH-A" and [t["text"] for t in tasks] == ["recap", "new belt"]


def test_a_project_about_two_things_is_left_alone():
    """Which of them is 'strip and clean' about? Only the owner knows, and a guess
    lands on the wrong machine's page reading as fact."""
    assert _pick()([project(items=("RH-A", "RH-B"), tasks=[("recap", None)])]) == []


def test_a_job_that_already_names_something_is_left_alone():
    """So a choice made by hand survives, and a second run changes nothing."""
    assert _pick()([project(tasks=[("recap", "RH-A")])]) == []


def test_a_project_with_no_items_is_left_alone():
    """A project need own nothing -- the idea comes before the hardware."""
    assert _pick()([project(items=(), tasks=[("order the caps", None)])]) == []


def test_a_project_with_no_loose_jobs_is_left_alone():
    assert _pick()([project(tasks=[])]) == []


def test_only_the_loose_ones_are_taken_from_a_mixed_project():
    got = _pick()([project(tasks=[("recap", "RH-A"), ("new belt", None)])])
    assert [t["text"] for t in got[0][2]] == ["new belt"]
