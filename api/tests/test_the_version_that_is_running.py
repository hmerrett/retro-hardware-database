"""Which version of the register this is (MANUAL §19, "The version that is running").

An installation that follows the code as it is written runs many builds under one
release number, so the number alone cannot say whether it is behind. The commit the
image was built from can, and it is only known if the build is told it: an image
has no repository inside it to ask.
"""

import re
from pathlib import Path

import pytest

from app import __version__, common
from conftest import as_viewer, log_out

ROOT = Path(__file__).resolve().parent.parent.parent


def version_line(html):
    m = re.search(r'<p class="hint" id="version">(.*?)</p>', html, re.S)
    return m.group(1).strip() if m else None


class TestTheServerTabSaysWhichVersion:
    def test_it_names_the_release_and_the_commit(self, client, monkeypatch):
        monkeypatch.setattr(common, "BUILD_COMMIT", "42dc15a")
        line = version_line(client.get("/settings/server").text)
        assert line == f"Version {__version__} · 42dc15a"

    def test_a_build_not_told_its_commit_names_the_release_alone(self, client, monkeypatch):
        """It has no way to find out, and a guess would be worse than nothing."""
        monkeypatch.setattr(common, "BUILD_COMMIT", "")
        assert version_line(client.get("/settings/server").text) == f"Version {__version__}"

    def test_it_is_on_the_server_tab_and_not_the_others(self, client):
        for tab in ("/settings", "/settings/labels"):
            assert version_line(client.get(tab).text) is None


class TestOnlyAnAdministratorSeesIt:
    """Telling strangers exactly which build is running tells them which fixes it
    does not have yet."""

    def test_a_visitor_does_not(self, client, monkeypatch):
        monkeypatch.setattr(common, "BUILD_COMMIT", "42dc15a")
        log_out(client)
        for page in ("/settings/server", "/", "/projects"):
            text = client.get(page).text
            assert version_line(text) is None
            assert "42dc15a" not in text

    def test_a_viewer_does_not(self, client, monkeypatch):
        monkeypatch.setattr(common, "BUILD_COMMIT", "42dc15a")
        as_viewer(client)
        for page in ("/settings/server", "/settings/account", "/"):
            text = client.get(page).text
            assert version_line(text) is None
            assert "42dc15a" not in text


class TestWhatCountsAsACommit:
    @pytest.mark.parametrize(
        "given, kept",
        [
            ("42dc15a", "42dc15a"),
            ("42dc15a5b8f3bd05f938532a399f489a6a1f4b2c", "42dc15a"),
            ("  42DC15A\n", "42dc15a"),
            ("", ""),
            ("main", ""),
            ("42dc15", ""),
            ("<b>42dc15a</b>", ""),
        ],
    )
    def test_a_commit_hash_is_shortened_and_anything_else_is_dropped(self, given, kept):
        """Seven characters is what git shows and what a reader compares by eye.
        Anything that is not a hash -- a branch name, a typo -- is not shown at all
        rather than shown as though it were one."""
        assert common.short_commit(given) == kept


class TestTheBuildIsToldItsCommit:
    """Each way the image is built hands it the commit, or the line has nothing to
    say beyond the release."""

    DOCKERFILE = (ROOT / "api" / "Dockerfile").read_text()

    def test_the_image_takes_it_as_a_build_argument_and_keeps_it(self):
        assert re.search(r"^ARG RHDB_COMMIT", self.DOCKERFILE, re.M)
        assert re.search(r"^ENV RHDB_COMMIT=\$\{?RHDB_COMMIT\}?$", self.DOCKERFILE, re.M)

    def test_it_comes_after_everything_it_would_invalidate(self):
        """An argument that changes on every build invalidates every layer after it,
        so it is the last thing the image is given: before it, the dependency tree
        and the code are cached as they always were."""
        lines = [ln for ln in self.DOCKERFILE.splitlines() if ln and not ln.startswith("#")]
        arg = next(i for i, ln in enumerate(lines) if ln.startswith("ARG RHDB_COMMIT"))
        assert not any(ln.startswith(("COPY", "RUN")) for ln in lines[arg:])

    def test_compose_passes_it_to_both_builds_of_the_api(self):
        """api-init builds the same image; told something different, it would be a
        second build of it."""
        import yaml

        services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
        for name in ("api", "api-init"):
            build = services[name]["build"]
            assert build["context"] == "./api"
            assert build["args"]["RHDB_COMMIT"] == "${RHDB_COMMIT:-}"

    def test_deploy_sh_tells_it(self):
        script = (ROOT / "deploy.sh").read_text()
        told = script.index("RHDB_COMMIT=")
        assert "git rev-parse" in script[told : script.index("\n", told)]
        assert told < script.index("docker compose up -d --build")

    def test_the_images_a_release_publishes_are_told_it(self):
        """An installation that pulls has no repository to ask either, so the image
        arrives knowing: the commit the release was tagged on (ADR-0041)."""
        import yaml

        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "publish.yml").read_text())
        build = next(
            step
            for step in workflow["jobs"]["build"]["steps"]
            if step.get("uses", "").startswith("docker/build-push-action@")
        )
        told = build["with"]["build-args"]
        assert "matrix.image == 'api'" in told
        assert "RHDB_COMMIT={0}" in told and "github.sha" in told
