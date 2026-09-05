"""Fetch a photo for an item from its reference URL.

Wikipedia URLs use the free summary API to get the page's lead image. Any other
site is a best effort grab of its Open Graph image (`og:image`). The bytes are
downscaled and re-saved as JPEG; known placeholder images are skipped. No bot
protection is bypassed, so a Cloudflare-gated site may simply return nothing.
"""
from __future__ import annotations

import hashlib
import io
import ipaddress
import os
import re
import socket
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx
from PIL import Image

# What we call ourselves when fetching somebody else's page. The convention is to
# say where the request came from so the other end can find out who is asking; that
# is this installation's own address, from the environment, and nothing at all when
# it has not been set -- naming a site that is not this one would send strangers to
# a stranger.
_SITE = (os.getenv("RHDB_BASE_URL") or "").strip().rstrip("/")
USER_AGENT = f"RetroHardwareDB/1.0 (+{_SITE})" if _SITE else "RetroHardwareDB/1.0"
MAX_PX = 1000


def _public_ip(host: str) -> bool:
    """Whether every address the host resolves to is a public one. A host that
    resolves to a private, loopback, link-local, reserved, multicast or
    unspecified address is refused -- that is where the internal services and the
    cloud metadata endpoint live."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _safe_url(url: str) -> bool:
    """A URL we are willing to fetch on a user's behalf: http(s) only, with a
    hostname that resolves solely to public addresses. This is the SSRF guard --
    the reference URL comes from whoever edited the item."""
    p = urlparse(url or "")
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    return _public_ip(p.hostname)


def _safe_get(client, url, **kw):
    """client.get, but validating the target and every redirect hop against
    _safe_url: a public URL can 302 to an internal one, so redirects are followed
    by hand rather than by httpx. Returns None if the chain leaves what is public
    or runs too long."""
    for _ in range(6):
        if not _safe_url(url):
            return None
        resp = client.get(url, **kw)
        if resp.is_redirect and "location" in resp.headers:
            url = urljoin(url, resp.headers["location"])
            continue
        return resp
    return None

# SHA1s of "please send a picture" placeholder images to ignore.
SKIP_SHA1 = {
    "0e07517a48ddafd09fe2834ef5e50d52dbbaeec0",
    "b1b631422579c64ffd1f7eaf392d9c6c36ca8a16",
}


def _client():
    # Redirects are followed by _safe_get instead, so each hop can be checked.
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0,
                        follow_redirects=False)


def _wikipedia_image(client, url):
    m = re.search(r"/wiki/([^?#]+)", url)
    if not m:
        return None
    title = unquote(m.group(1))
    host = urlparse(url).hostname or "en.wikipedia.org"
    lang = host.split(".")[0] if host.endswith("wikipedia.org") else "en"
    api = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    resp = _safe_get(client, api)
    if resp is None or resp.status_code >= 400:
        return None
    data = resp.json()
    return (data.get("originalimage") or data.get("thumbnail") or {}).get("source")


def _og_image(client, url):
    resp = _safe_get(client, url)
    if resp is None or resp.status_code >= 400:
        return None
    html = resp.text
    for prop in ("og:image", "twitter:image"):
        m = (re.search(r'<meta[^>]+(?:property|name)=["\']' + prop
                       + r'["\'][^>]+content=["\']([^"\']+)', html, re.I)
             or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']'
                          + prop, html, re.I))
        if m:
            return urljoin(url, m.group(1))
    return None


def _favicon_url(client, url):
    """Best link to the site's icon: a declared <link rel=icon/apple-touch-icon>,
    else the conventional /favicon.ico."""
    try:
        resp = _safe_get(client, url)
        if resp is not None and resp.status_code < 400:
            best = None
            for m in re.finditer(r"<link\b([^>]+)>", resp.text, re.I):
                attrs = m.group(1)
                if not re.search(r'rel=["\'][^"\']*icon', attrs, re.I):
                    continue
                href = re.search(r'href=["\']([^"\']+)', attrs, re.I)
                if not href:
                    continue
                cand = urljoin(url, href.group(1))
                # Prefer an apple-touch-icon (usually a clean, larger PNG).
                if re.search(r"apple-touch", attrs, re.I):
                    return cand
                best = best or cand
            if best:
                return best
    except Exception:
        pass
    p = urlparse(url)
    return f"{p.scheme}://{p.hostname}/favicon.ico" if p.scheme and p.hostname else None


def fetch_favicon(url):
    """Return small square PNG bytes of the site's favicon, or None. Used as a
    provenance marker on reference images, cached locally so nothing hotlinks."""
    url = (url or "").strip()
    if not url:
        return None
    try:
        with _client() as client:
            icon_url = _favicon_url(client, url)
            if not icon_url:
                return None
            resp = _safe_get(client, icon_url)
            if resp is None or resp.status_code >= 400 or not resp.content:
                return None
            img = Image.open(io.BytesIO(resp.content))
            # For multi-size .ico, pick the largest frame available.
            sizes = getattr(img, "info", {}).get("sizes")
            if sizes:
                img.size = max(sizes)
                img.load()
            img = img.convert("RGBA")
    except Exception:
        return None
    img.thumbnail((48, 48))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def fetch_jpeg(url):
    """Return downscaled JPEG bytes for the item's reference URL, or None if
    nothing usable was found."""
    url = (url or "").strip()
    if not url:
        return None
    try:
        with _client() as client:
            img_url = None
            if "wikipedia.org" in url.lower():
                img_url = _wikipedia_image(client, url)
            if not img_url:
                img_url = _og_image(client, url)
            if not img_url:
                return None
            resp = _safe_get(client, img_url)
            if resp is None or resp.status_code >= 400 or not resp.content:
                return None
            raw = resp.content
    except Exception:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None
    img.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    data = buf.getvalue()
    if hashlib.sha1(data).hexdigest() in SKIP_SHA1:
        return None
    return data
