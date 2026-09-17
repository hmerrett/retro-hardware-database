"""An installation's own logo, and the placeholder it replaces.

The artwork that ships is deliberately anonymous -- a beige machine with a bare
prompt on its screen -- because this is somebody's own catalogue on their own
domain, and the mark at the top of the page should be able to be theirs. A file
dropped into the branding directory under the same name as a shipped one is served
instead of it, and nothing in that directory is in git.

The rule that matters is the one below: a name nobody has overridden still comes
back, so an installation replaces the one file it cares about rather than all ten.
"""

import pytest

from app import main


@pytest.fixture
def branding():
    """Put a file in the branding directory for one test and take it away after."""
    written = []

    def put(name, data=b"\\x89PNG\\r\\n\\x1a\\nthis installation's own"):
        path = main.BRANDING_DIR / name
        path.write_bytes(data)
        written.append(path)
        return data

    yield put
    for path in written:
        path.unlink(missing_ok=True)


class TestChoosingTheArtwork:
    def test_the_shipped_one_is_used_when_there_is_no_other(self):
        assert main.branded("logo-256.png") == main.STATIC_DIR / "logo-256.png"

    def test_an_installations_own_wins(self, branding):
        branding("logo-256.png")
        assert main.branded("logo-256.png") == main.BRANDING_DIR / "logo-256.png"

    def test_overriding_one_leaves_the_rest_shipped(self, branding):
        """The point of resolving name by name rather than directory by directory:
        replacing the header logo does not mean supplying every icon size."""
        branding("logo-256.png")
        assert main.branded("favicon.ico") == main.STATIC_DIR / "favicon.ico"


class TestServingIt:
    def test_a_static_file_falls_through_to_what_ships(self, client):
        r = client.get("/static/logo-256.png")
        assert r.status_code == 200
        assert r.content == (main.STATIC_DIR / "logo-256.png").read_bytes()

    def test_a_static_file_is_replaced_by_the_installations_own(self, client, branding):
        data = branding("logo-256.png")
        assert client.get("/static/logo-256.png").content == data

    def test_the_favicon_is_replaced_too(self, client, branding):
        """Asked for at the domain root by browsers that never read the markup, so
        it is a route of its own rather than part of the static mount -- and it has
        to obey the same rule, or the tab keeps somebody else's mark."""
        data = branding("favicon.ico")
        assert client.get("/favicon.ico").content == data

    def test_and_the_home_screen_icon(self, client, branding):
        data = branding("apple-touch-icon.png")
        assert client.get("/apple-touch-icon.png").content == data

    def test_nothing_outside_the_two_directories_is_reachable(self, client):
        """The branding directory goes in front of the shipped one in the static
        mount's own search list, so the traversal checks are the ones it already
        makes -- this says so out loud, because a directory that can be written to
        from outside the image sitting in the serving path is worth a test."""
        assert client.get("/static/../../../etc/passwd").status_code in (307, 404)
