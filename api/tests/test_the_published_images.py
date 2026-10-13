"""The images a release publishes, and the compose file that names them (ADR-0041).

An installation pulls the app and the tool server rather than building them, which
on a small ARM board was the slowest part of setting up. Three things make that
work, and these hold them: the compose file names the images a release publishes,
under the release this checkout is; the workflow publishes both images for both
architectures under that release's number and nothing that floats; and the tool
server is built from a lockfile, so one tag is one image.
"""

import re
import tomllib
from pathlib import Path

import yaml

from app import __version__

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = "ghcr.io/hmerrett/retro-hardware-database"
RELEASE_TAG = re.compile(rf"{re.escape(REGISTRY)}/(api|mcp):\$\{{RHDB_VERSION:-(.+)\}}")


def _services():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]


def _workflow():
    return yaml.safe_load((ROOT / ".github" / "workflows" / "publish.yml").read_text())


def _triggers():
    # YAML 1.1 reads a bare `on` as true, and PyYAML speaks YAML 1.1.
    workflow = _workflow()
    return workflow.get("on") or workflow[True]


def _step(job, action):
    steps = _workflow()["jobs"][job]["steps"]
    return next(s for s in steps if s.get("uses", "").startswith(action + "@"))


class TestComposeNamesThePublishedImages:
    """`docker compose pull` fetches what the compose file names, so it names what a
    release publishes."""

    def test_each_service_built_here_names_the_image_a_release_publishes(self):
        """api-init runs the app's image before the app starts, so the two name one
        image and one pull serves both."""
        services = _services()
        for service, image in (("api", "api"), ("api-init", "api"), ("mcp", "mcp")):
            m = RELEASE_TAG.fullmatch(services[service]["image"])
            assert m, f"{service} names {services[service].get('image')}"
            assert m.group(1) == image

    def test_unless_told_otherwise_the_tag_is_the_release_this_checkout_is(self):
        """So a checkout of a release's tag pulls that release's images. When the
        version moves, this is what fails until the compose file moves with it."""
        for service in ("api", "api-init", "mcp"):
            m = RELEASE_TAG.fullmatch(_services()[service]["image"])
            assert m and m.group(2) == __version__

    def test_an_installation_that_builds_rather_than_pulls_still_can(self):
        """deploy.sh builds from the checkout, under the same names, so to
        `docker compose up` a build and a pull are the same image."""
        services = _services()
        assert services["api"]["build"]["context"] == "./api"
        assert services["api-init"]["build"] == services["api"]["build"]
        assert services["mcp"]["build"] == "./mcp"

    def test_a_new_env_leaves_the_release_to_the_checkout(self):
        """A number copied into .env would stay behind when the checkout moved on, and
        the next pull would fetch the old release's images for the new code."""
        example = (ROOT / ".env.example").read_text()
        assert re.search(r"^RHDB_VERSION=$", example, re.M)


class TestAReleasePublishesThem:
    """Pushing a tag `vX.Y.Z` publishes both images, for both architectures, under
    that release's number."""

    def test_a_release_tag_starts_it(self):
        assert _triggers()["push"] == {"tags": ["v*"]}

    def test_both_images_are_built_for_both_architectures(self):
        build = _workflow()["jobs"]["build"]
        assert build["strategy"]["matrix"]["image"] == ["api", "mcp"]
        assert build["strategy"]["matrix"]["arch"] == ["amd64", "arm64"]
        made = _step("build", "docker/build-push-action")["with"]
        assert made["context"] == "./${{ matrix.image }}"
        assert made["platforms"] == "linux/${{ matrix.arch }}"

    def test_each_architecture_is_built_on_its_own(self):
        """Not one runner pretending to be the other: under emulation, the arm64 half
        of a build takes far longer than the amd64 half."""
        build = _workflow()["jobs"]["build"]
        runners = {i["arch"]: i["runner"] for i in build["strategy"]["matrix"]["include"]}
        assert "arm" in runners["arm64"] and "arm" not in runners["amd64"]
        assert build["runs-on"] == "${{ matrix.runner }}"
        assert "setup-qemu-action" not in (ROOT / ".github/workflows/publish.yml").read_text()

    def test_the_tags_are_the_release_and_nothing_that_floats(self):
        """0.2.0 and 0.2, and never latest: like every other image in the compose
        file, it changes when an installation says so."""
        meta = _step("publish", "docker/metadata-action")["with"]
        assert meta["flavor"] == "latest=false"
        assert meta["tags"].split() == [
            "type=semver,pattern={{version}}",
            "type=semver,pattern={{major}}.{{minor}}",
        ]

    def test_a_tag_that_is_not_the_release_the_code_names_publishes_nothing(self):
        """The Settings page names the release from __version__, so an image published
        under another number would tell its administrator the wrong version."""
        steps = _workflow()["jobs"]["build"]["steps"]
        check = next(i for i, s in enumerate(steps) if "api/app/__init__.py" in s.get("run", ""))
        build = next(
            i
            for i, s in enumerate(steps)
            if s.get("uses", "").startswith("docker/build-push-action@")
        )
        assert check < build
        assert "exit 1" in steps[check]["run"]

    def test_a_pull_request_builds_them_and_pushes_nothing(self):
        """A lockfile or a Dockerfile meets arm64 in review, not on release day."""
        assert "pull_request" in _triggers()
        jobs = _workflow()["jobs"]
        assert jobs["build"]["env"]["RELEASE"] == "${{ startsWith(github.ref, 'refs/tags/v') }}"
        made = _step("build", "docker/build-push-action")["with"]
        assert made["outputs"].endswith(",push=${{ env.RELEASE }}")
        assert jobs["publish"]["if"] == "startsWith(github.ref, 'refs/tags/v')"

    def test_every_action_is_pinned_to_a_commit(self):
        """This workflow can publish under the project's name, and a tag can be moved
        under it. A commit cannot."""
        used = [
            step["uses"]
            for job in _workflow()["jobs"].values()
            for step in job["steps"]
            if "uses" in step
        ]
        assert used
        assert [u for u in used if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u)] == []


class TestTheToolServerIsBuiltFromItsLockfile:
    """Its dependencies floated, so two builds of one tag could hold different code.
    Now they are locked as the app's are (backend-standards)."""

    MCP = ROOT / "mcp"

    def test_its_dependencies_are_pinned(self):
        project = tomllib.loads((self.MCP / "pyproject.toml").read_text())["project"]
        assert project["dependencies"]
        assert [d for d in project["dependencies"] if "==" not in d] == []

    def test_the_tree_behind_them_is_locked(self):
        assert (self.MCP / "uv.lock").is_file()
        assert not (self.MCP / "requirements.txt").exists()

    def test_its_image_installs_the_lock_and_nothing_else(self):
        dockerfile = (self.MCP / "Dockerfile").read_text()
        assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
        assert "pip install" not in dockerfile

    def test_dependabot_keeps_it_current_as_it_does_the_apps(self):
        updates = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())["updates"]
        for ecosystem in ("uv", "docker"):
            watched = [
                d
                for u in updates
                if u["package-ecosystem"] == ecosystem
                for d in u.get("directories", [u.get("directory")])
            ]
            assert "/api" in watched and "/mcp" in watched, ecosystem
