"""What the container is told to do when it starts.

These read a shipped file rather than call a function, as the catalogue.txt test
does. The entrypoint is not import-testable -- it is a line of shell that only
runs in a container -- and it is exactly the sort of thing that is edited once,
works on the author's box, and is never looked at again.
"""

from pathlib import Path

ENTRYPOINT = (Path(__file__).resolve().parent.parent / "entrypoint.sh").read_text()


class TestTheApiTrustsItsProxy:
    """Behind Caddy, the app has to be told that a request arrived over HTTPS.

    Uvicorn reads X-Forwarded-Proto only from an address it trusts, and trusts
    127.0.0.1 alone by default -- while Caddy reaches it from a container address
    on the compose network. Without this the app believes every request is plain
    HTTP and builds its absolute redirects to match: /items/<id>/, the URL a
    printed QR label carries, answered 307 to http://. It still arrived, because
    Caddy sent it back up to HTTPS, but the scan made a cleartext hop on the way.
    """

    def test_the_proxy_headers_are_read(self):
        assert "--proxy-headers" in ENTRYPOINT

    def test_they_are_read_from_the_proxy_rather_than_from_localhost(self):
        assert '--forwarded-allow-ips="*"' in ENTRYPOINT

    def test_the_schema_is_brought_up_before_the_app_serves(self):
        """The other half of the entrypoint, and the reason a deploy needs no
        migration step of its own."""
        lines = [
            ln.strip()
            for ln in ENTRYPOINT.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        upgrade = next(i for i, ln in enumerate(lines) if "alembic upgrade head" in ln)
        serve = next(i for i, ln in enumerate(lines) if "uvicorn" in ln)
        assert upgrade < serve


API = Path(__file__).resolve().parent.parent
ROOT = API.parent
DOCKERFILE = (API / "Dockerfile").read_text()
FIX_VOLUMES = (API / "fix-volumes.sh").read_text()


def _compose(name):
    import yaml

    return yaml.safe_load((ROOT / name).read_text())


def _instructions(text, keyword):
    """The arguments of every Dockerfile line starting with `keyword`, in order."""
    return [
        ln.split(None, 1)[1].strip()
        for ln in text.splitlines()
        if ln.strip().upper().startswith(keyword + " ")
    ]


class TestTheAppDoesNotRunAsRoot:
    """The process that answers the public internet runs as its own user.

    As root, anything that got code execution through the app -- a parser bug in
    an image library, say -- would own the container outright. As appuser it owns
    the photographs and the files, which the app has to be able to write anyway,
    and nothing else.
    """

    def test_the_image_ends_as_appuser(self):
        assert _instructions(DOCKERFILE, "USER")[-1] == "appuser"

    def test_the_app_owns_where_it_writes_and_not_its_own_code(self):
        """The data directories are chowned by name, never /app as a whole: code
        the app can rewrite is code a compromise can rewrite."""
        chowns = [ln for ln in DOCKERFILE.splitlines() if "chown" in ln]
        assert chowns and all("/app/images" in ln and "/app/files" in ln for ln in chowns)
        assert not any("-R" in ln and ln.rstrip().endswith(" /app") for ln in chowns)

    def test_an_older_install_gets_its_volumes_back_before_the_app_starts(self):
        """An install from before this has root-owned volumes. api-init puts them
        right, as root, and the app waits for it to finish -- or its first upload
        after upgrading would fail to save."""
        services = _compose("docker-compose.yml")["services"]
        init = services["api-init"]
        assert init["user"] == "root"
        assert init["command"] == ["./fix-volumes.sh"]
        assert (
            services["api"]["depends_on"]["api-init"]["condition"]
            == "service_completed_successfully"
        )

    def test_the_fix_reaches_the_two_volumes_and_nothing_else(self):
        """It runs as root, so what it may touch is spelled out and kept small."""
        targets = [ln for ln in FIX_VOLUMES.splitlines() if ln.strip().startswith("for dir in")]
        assert targets == ["for dir in /app/images /app/files; do"]
        init_mounts = _compose("docker-compose.yml")["services"]["api-init"]["volumes"]
        assert sorted(init_mounts) == ["files:/app/files", "images:/app/images"]

    def test_it_looks_before_it_changes_anything(self):
        """A chown -R over every photograph on every start would be slow on a large
        collection and would churn the backup's view of what changed."""
        find = FIX_VOLUMES.index("find ")
        chown = FIX_VOLUMES.index("chown -R")
        assert find < chown


class TestTheDevelopmentOverride:
    """`docker compose -f docker-compose.yml -f docker-compose.dev.yml up` runs the
    same image with the source mounted over it, reloading on save."""

    def test_it_goes_through_the_entrypoint(self):
        """So a development run migrates first and reads the proxy headers exactly
        as production does, rather than carrying its own copy of the uvicorn line
        that drifts from the real one."""
        command = _compose("docker-compose.dev.yml")["services"]["api"]["command"]
        assert command[0] == "./entrypoint.sh"
        assert '"$@"' in ENTRYPOINT

    def test_it_watches_the_code_and_not_the_photographs(self):
        """uvicorn watches its whole working directory unless told otherwise, and
        the photograph volume is inside it: every upload would restart the server."""
        command = _compose("docker-compose.dev.yml")["services"]["api"]["command"]
        assert "--reload" in command
        assert command[command.index("--reload-dir") + 1] == "app"
