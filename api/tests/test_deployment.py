"""What the container is told to do when it starts.

These read a shipped file rather than call a function, as the catalogue.txt test
does. The entrypoint is not import-testable -- it is a line of shell that only
runs in a container -- and it is exactly the sort of thing that is edited once,
works on the author's box, and is never looked at again.
"""

from pathlib import Path

import pytest

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


class TestTheMcpServerDoesNotRunAsRoot:
    """The MCP server runs as its own user too, for the same reason as the app.

    It is reached only on localhost, so the exposure is smaller, but it handles
    what an agent sends it and holds the API token; as root it would own its
    container outright for the price of one line not written.
    """

    MCP_DOCKERFILE = (ROOT / "mcp" / "Dockerfile").read_text()

    def test_the_image_ends_as_a_user_that_is_not_root(self):
        users = _instructions(self.MCP_DOCKERFILE, "USER")
        assert users and users[-1] not in ("root", "0", "0:0")

    def test_the_user_has_a_fixed_uid(self):
        """A fixed uid means the same thing from one build to the next, as api's does."""
        assert "--uid 10001" in self.MCP_DOCKERFILE

    def test_it_owns_none_of_its_own_code(self):
        """It writes nothing, so nothing in the image is given to it."""
        assert "chown" not in self.MCP_DOCKERFILE


def _build_contexts():
    """Every directory a compose file in the repository builds an image from."""
    import yaml

    contexts = set()
    for compose in ROOT.glob("**/docker-compose*.yml"):
        if ".venv" in compose.parts or "node_modules" in compose.parts:
            continue
        for service in (yaml.safe_load(compose.read_text()).get("services") or {}).values():
            build = service.get("build")
            if build is not None:
                where = build if isinstance(build, str) else build.get("context", ".")
                contexts.add((compose.parent / where).resolve())
    return sorted(contexts)


class TestABuildSendsOnlyWhatItNeeds:
    """A build hands its whole context to the daemon before it reads a line of the
    Dockerfile, so what a context holds is what a build sends -- whether or not
    anything copies it. Docker reads the .dockerignore at the root of the context
    and no other, which is why each one has its own rather than the repository
    having one: no build here starts at the repository's root.
    """

    def test_every_build_context_has_a_dockerignore(self):
        contexts = _build_contexts()
        assert {c.name for c in contexts} >= {"api", "mcp", "backup"}
        assert [c for c in contexts if not (c / ".dockerignore").is_file()] == []

    @pytest.mark.parametrize("name", ["backup", "mcp"])
    def test_a_small_context_sends_only_what_its_image_copies(self, name):
        """Each names what it sends, rather than what it leaves out, because what
        lands beside it is not known. On the machine it runs on, the backup's
        directory holds its .env, the key that reaches the server, the repository
        password and, by default, the whole restic repository and a mirror of every
        photograph: none of it belongs in a build, and a rebuild that sends the
        last two takes all evening."""
        context = ROOT / name
        lines = (context / ".dockerignore").read_text().splitlines()
        ignore = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
        assert ignore[0] == "*"
        assert sorted(line[1:] for line in ignore if line.startswith("!")) == sorted(
            _copied_from_the_context(context / "Dockerfile")
        )


def _copied_from_the_context(dockerfile):
    """Every source a COPY takes from the build context: all but its last argument,
    which is where it goes. A COPY --from takes from another stage or image, which
    is not the context and is never sent."""
    sources = []
    for copy in _instructions(dockerfile.read_text(), "COPY"):
        args = copy.split()
        if not any(arg.startswith("--from=") for arg in args):
            sources += [arg for arg in args[:-1] if not arg.startswith("--")]
    return sources


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


class TestEverySettingReachesTheContainer:
    """A variable the app reads, documented in `.env.example` and never passed
    through Compose, is a setting that does nothing in the stack it was written for.

    Compose does not forward the environment wholesale: each service lists what it
    is given. So a new variable is two edits, the second is easy to forget, and
    forgetting it fails in the one place nobody tests -- somebody else's install,
    weeks later, with the value sitting correctly in their .env.
    """

    ROOT = Path(__file__).resolve().parent.parent.parent
    EXAMPLE = ROOT / ".env.example"
    COMPOSE = ROOT / "docker-compose.yml"

    def test_every_documented_variable_is_passed_to_a_service(self):
        import re

        named = set(re.findall(r"^(RHDB_[A-Z0-9_]+)=", self.EXAMPLE.read_text(), re.M))
        assert named, "no variables found in .env.example -- has it moved?"
        compose = self.COMPOSE.read_text()
        missing = sorted(v for v in named if v not in compose)
        assert not missing, f"documented but never given to a container: {missing}"


class TestTheTrafficReportIsWrittenByOneRelease:
    """GoAccess's report runs its scripts in an administrator's browser, over paths
    and user agents that strangers wrote, and what keeps those inert is GoAccess's
    escaping (ADR-0033). So the GoAccess that writes it is one somebody read before
    it ran, rather than whatever the registry calls latest on the day of the pull."""

    def test_the_image_is_pinned_to_a_release(self):
        import re

        image = _compose("docker-compose.yml")["services"]["goaccess"]["image"]
        name, _, tag = image.partition(":")
        assert name == "allinurl/goaccess"
        assert re.fullmatch(r"\d+(?:\.\d+)+", tag), f"{image} is not pinned to a release"


class TestTheDatabaseIsOneMinorRelease:
    """`mariadb:11` is whichever 11 is newest, and it became 11.8, which turned on
    snapshot isolation: a write to a row that another request changed after this one
    began reading is refused, where before it was written over. That reached
    production with nothing in the repository changed. So the engine is a release
    named here and moved on deliberately, and CI runs the suite on the same one, the
    engine production uses (ADR-0008)."""

    def test_the_image_is_pinned_to_a_minor_release(self):
        import re

        image = _compose("docker-compose.yml")["services"]["db"]["image"]
        name, _, tag = image.partition(":")
        assert name == "mariadb"
        assert re.fullmatch(r"\d+\.\d+(?:\.\d+)?", tag), f"{image} is not one minor release"

    def test_ci_runs_the_suite_on_the_same_one(self):
        ci = _compose(".github/workflows/ci.yml")["jobs"]["test"]["services"]["mariadb"]
        assert ci["image"] == _compose("docker-compose.yml")["services"]["db"]["image"]
