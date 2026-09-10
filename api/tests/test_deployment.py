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
        lines = [ln.strip() for ln in ENTRYPOINT.splitlines() if ln.strip()
                 and not ln.strip().startswith("#")]
        upgrade = next(i for i, ln in enumerate(lines) if "alembic upgrade head" in ln)
        serve = next(i for i, ln in enumerate(lines) if "uvicorn" in ln)
        assert upgrade < serve
