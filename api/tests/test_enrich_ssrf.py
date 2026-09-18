"""enrich.py fetches URLs taken from an item's reference field, so it must not be
usable to reach inside the network -- the database, the API, the cloud metadata
endpoint, localhost. _safe_url is the guard; these cases use IP literals so the
test needs no DNS.
"""

import pytest

from app.enrich import _safe_url

BLOCKED = [
    "http://127.0.0.1/x",  # loopback
    "http://10.0.0.5/",  # private
    "http://172.16.0.1/",  # private
    "http://192.168.1.1/",  # private
    "http://169.254.169.254/latest/meta-data/",  # link-local / cloud metadata
    "http://0.0.0.0/",  # unspecified
    "http://[::1]/",  # IPv6 loopback
    "ftp://8.8.8.8/x",  # non-http scheme
    "file:///etc/passwd",  # non-http scheme
    "gopher://8.8.8.8/",  # non-http scheme
    "://nonsense",  # no scheme/host
    "",  # empty
]

ALLOWED = [
    "http://8.8.8.8/photo.jpg",
    "https://1.1.1.1/card",
]


@pytest.mark.parametrize("url", BLOCKED)
def test_blocks_internal_and_non_http(url):
    assert _safe_url(url) is False


@pytest.mark.parametrize("url", ALLOWED)
def test_allows_public_http(url):
    assert _safe_url(url) is True
