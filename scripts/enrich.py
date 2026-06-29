#!/usr/bin/env python3
"""Fill in summaries, photos and (optionally) specs for both tables.

Sources:
  * wikipedia  (default) — free, no key. Fills summary, wikipedia_url, photo.
  * theretroweb          — best effort. Only for rows that already have a
                           theretroweb_url. One identifying, rate-limited
                           request per item; reads the spec table + image if
                           the page is returned. Does NOT bypass Cloudflare /
                           bot protection — if blocked, it logs and keeps just
                           the link. See docs/schema.md.

Only EMPTY fields are filled unless you pass --force.

Usage:
    python scripts/enrich.py                              # wikipedia, all items
    python scripts/enrich.py --only RH-0001
    python scripts/enrich.py --source theretroweb --only RH-0003
    python scripts/enrich.py --source theretroweb --only RH-0003 --dump-html
    python scripts/enrich.py --source all --force
"""
from __future__ import annotations

import argparse
import io
import re
import time
from urllib.parse import quote, urljoin

import requests
from PIL import Image

from common import (IMAGES_DIR, ROOT, display_name, load_computers,
                    load_config, load_parts, parse_specs, save_computers,
                    save_parts)

SEARCH_API = "https://{lang}.wikipedia.org/w/api.php"
SUMMARY_API = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"


# --- shared image helper ---------------------------------------------------

def download_image(session, url, dest, max_px):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    img.thumbnail((max_px, max_px))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=85)


def image_dest(kind, asset_id):
    """kind is 'computers' or 'parts'. Returns (path, column_value)."""
    rel = f"{kind}/{asset_id}.jpg"
    return IMAGES_DIR / rel, rel


# --- Wikipedia -------------------------------------------------------------

def wiki_search_title(session, lang, query):
    resp = session.get(SEARCH_API.format(lang=lang), params={
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": 1, "format": "json"}, timeout=20)
    resp.raise_for_status()
    hits = resp.json().get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


def wiki_summary(session, lang, title):
    url = SUMMARY_API.format(lang=lang, title=quote(title.replace(" ", "_")))
    resp = session.get(url, timeout=20)
    return resp.json() if resp.status_code == 200 else None


def looks_relevant(name, title):
    """True if the matched article title shares a significant token (>=3 chars)
    with the item name — guards against junk matches (e.g. 'ECS CI-90' -> the
    'Climate inertia' article). If there are no such tokens, don't block."""
    tokens = {t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) >= 3}
    if not tokens:
        return True
    tl = title.lower()
    return any(t in tl for t in tokens)


def enrich_wikipedia(session, row, kind, lang, max_px, force):
    need_summary = force or not row["summary"]
    need_url = force or not row["wikipedia_url"]
    need_image = force or not row["image"]
    if not (need_summary or need_url or need_image):
        return False

    # Generic / unbranded items have no meaningful article — a Wikipedia search
    # would just match junk (e.g. a "generic 3.5\" floppy" hitting SimCity).
    generic = {"generic", "unknown", "mixed", "clone", "custom build",
               "unknown (clone)", "n/a", "none", "noname"}
    if ((row.get("manufacturer") or "").strip().lower() in generic
            or display_name(row).strip().lower().startswith("generic")):
        print(f"  [{row['asset_id']}] skipping Wikipedia (generic/unknown: "
              f"{display_name(row)})")
        return False

    query = display_name(row)
    print(f"  [{row['asset_id']}] wikipedia: {query}")
    try:
        title = wiki_search_title(session, lang, query)
        if not title:
            print("      no match")
            return False
        if not looks_relevant(query, title):
            print(f"      '{title}' looks unrelated to '{query}' — skipping "
                  "(paste a wikipedia_url yourself to override)")
            return False
        data = wiki_summary(session, lang, title)
        if not data:
            print("      no summary")
            return False
        if need_summary and data.get("extract"):
            row["summary"] = data["extract"]
        if need_url:
            row["wikipedia_url"] = (data.get("content_urls", {})
                                    .get("desktop", {}).get("page")
                                    or f"https://{lang}.wikipedia.org/wiki/{quote(title)}")
        if need_image:
            src = (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
            if src:
                dest, rel = image_dest(kind, row["asset_id"])
                try:
                    download_image(session, src, dest, max_px)
                    row["image"] = rel
                    print(f"      photo -> images/{rel}")
                except Exception as exc:  # noqa: BLE001
                    print(f"      image failed: {exc}")
        print(f"      matched: {title}")
        time.sleep(0.4)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"      error: {exc}")
        return False


# --- The Retro Web (best effort) -------------------------------------------

def parse_theretroweb(html):
    """Best-effort extraction of (specs list, image url) from a TRW page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("      (install beautifulsoup4 to parse theretroweb pages)")
        return [], None
    soup = BeautifulSoup(html, "html.parser")
    specs, seen = [], set()
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) == 2:
                k = cells[0].get_text(" ", strip=True)
                v = cells[1].get_text(" ", strip=True)
                if k and v and len(k) < 40 and k.lower() not in seen:
                    specs.append((k, v))
                    seen.add(k.lower())
    for dl in soup.find_all("dl"):
        terms, defs = dl.find_all("dt"), dl.find_all("dd")
        for dt, dd in zip(terms, defs):
            k = dt.get_text(" ", strip=True)
            v = dd.get_text(" ", strip=True)
            if k and v and k.lower() not in seen:
                specs.append((k, v))
                seen.add(k.lower())
    og = soup.find("meta", attrs={"property": "og:image"})
    image = og["content"] if og and og.get("content") else None
    return specs, image


# A current Chrome UA so Cloudflare serves the page to headless Chromium.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def fetch_theretroweb_browser(url, ua=BROWSER_UA, timeout=45):
    """Render a Retro Web page in headless Chromium (gets past the Cloudflare JS
    challenge that blocks plain requests). Returns (html, image_bytes); either
    may be None. Requires the optional Playwright dependency."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      Playwright not installed — run: pip install -r requirements-browser.txt")
        print("      (it then drives your installed Google Chrome; no browser download)")
        return None, None
    try:
        with sync_playwright() as pw:
            launch_args = ["--disable-blink-features=AutomationControlled"]
            try:
                # Use the locally-installed Google Chrome — no download needed.
                browser = pw.chromium.launch(channel="chrome", args=launch_args)
            except Exception:
                # Fall back to Playwright's bundled Chromium if Chrome isn't found.
                browser = pw.chromium.launch(args=launch_args)
            ctx = browser.new_context(user_agent=ua)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(1800)  # let any Cloudflare / JS settle
            html = page.content()
            page_url = page.url
            try:
                img_url = page.get_attribute('meta[property="og:image"]', "content")
            except Exception:  # noqa: BLE001
                img_url = None
            img_bytes = None
            if img_url:
                img_url = urljoin(page_url, img_url)  # resolve relative og:image
                try:
                    resp = ctx.request.get(img_url, timeout=timeout * 1000)
                    if resp.ok:
                        img_bytes = resp.body()
                except Exception as exc:  # noqa: BLE001
                    print(f"      (image fetch failed: {exc})")
            browser.close()
            return html, img_bytes
    except Exception as exc:  # noqa: BLE001
        print(f"      browser fetch failed: {exc}")
        return None, None


def _save_image_bytes(data, kind, asset_id, max_px):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_px, max_px))
    dest, rel = image_dest(kind, asset_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=85)
    return rel


def enrich_theretroweb(session, row, kind, max_px, delay, force, dump_html,
                       use_browser=False, browser_ua=BROWSER_UA):
    url = row.get("theretroweb_url", "")
    if not url:
        return False
    has_specs = "specs" in row          # computers have no specs column
    need_specs = has_specs and (force or not row.get("specs", ""))
    need_image = force or not row.get("image", "")
    if not (need_specs or need_image):
        return False

    print(f"  [{row['asset_id']}] theretroweb{' (browser)' if use_browser else ''}: {url}")
    try:
        time.sleep(delay)  # be polite
        img_bytes = None
        if use_browser:
            html, img_bytes = fetch_theretroweb_browser(url, browser_ua)
            if html is None:
                return False
        else:
            resp = session.get(url, timeout=30)
            html = resp.text or ""
            if resp.status_code != 200 or not html.strip():
                print(f"      blocked/empty (status {resp.status_code}) — keeping link only")
                return False
        if dump_html and html:
            dump = ROOT / "labels" / f"trw_{row['asset_id']}.html"
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_text(html, encoding="utf-8")
            print(f"      dumped HTML -> {dump}")

        specs, og_image = parse_theretroweb(html)
        changed = False
        if need_specs and specs:
            row["specs"] = " | ".join(f"{k}: {v}" for k, v in specs[:12])
            print(f"      specs: {len(specs[:12])} field(s)")
            changed = True
        if need_image:
            try:
                if img_bytes:
                    row["image"] = _save_image_bytes(img_bytes, kind, row["asset_id"], max_px)
                    print(f"      photo -> images/{row['image']}")
                    changed = True
                elif og_image and not use_browser:
                    dest, rel = image_dest(kind, row["asset_id"])
                    download_image(session, og_image, dest, max_px)
                    row["image"] = rel
                    print(f"      photo -> images/{rel}")
                    changed = True
            except Exception as exc:  # noqa: BLE001
                print(f"      image failed: {exc}")
        if not changed:
            print("      nothing retrieved — Cloudflare may have blocked it; "
                  "save the photo into images/ by hand instead")
        return changed
    except Exception as exc:  # noqa: BLE001
        print(f"      error: {exc} — keeping link only")
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["wikipedia", "theretroweb", "all"],
                    default="wikipedia")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", help="only this asset_id")
    ap.add_argument("--dump-html", action="store_true",
                    help="save fetched theretroweb HTML for debugging")
    ap.add_argument("--browser", action="store_true",
                    help="render theretroweb via headless Chromium (Playwright) to "
                         "get past Cloudflare; grabs the photo + specs")
    args = ap.parse_args()

    config = load_config()
    enr = config.get("enrich", {})
    lang = enr.get("wikipedia_lang", "en")
    max_px = int(enr.get("image_max_px", 1000))

    wiki_session = requests.Session()
    wiki_session.headers.update({"User-Agent": enr.get("user_agent", "RetroHardwareDB/1.0")})
    trw_session = requests.Session()
    trw_session.headers.update({
        "User-Agent": enr.get("theretroweb_user_agent", "RetroHardwareDB/1.0"),
        "Accept": "text/html,application/xhtml+xml",
    })
    trw_delay = float(enr.get("theretroweb_delay_seconds", 3))
    browser_ua = enr.get("theretroweb_browser_ua") or BROWSER_UA

    computers = load_computers()
    parts = load_parts()
    rows = [("computers", r) for r in computers] + [("parts", r) for r in parts]

    changed_c = changed_p = 0
    for kind, row in rows:
        if args.only and row["asset_id"] != args.only:
            continue
        changed = False
        if args.source in ("wikipedia", "all"):
            changed |= enrich_wikipedia(wiki_session, row, kind, lang, max_px, args.force)
        if args.source in ("theretroweb", "all"):
            changed |= enrich_theretroweb(trw_session, row, kind, max_px,
                                          trw_delay, args.force, args.dump_html,
                                          use_browser=args.browser, browser_ua=browser_ua)
        if changed:
            if kind == "computers":
                changed_c += 1
            else:
                changed_p += 1

    if changed_c:
        save_computers(computers)
    if changed_p:
        save_parts(parts)
    total = changed_c + changed_p
    if total:
        print(f"\nUpdated {total} item(s) ({changed_c} computers, "
              f"{changed_p} parts). Re-run build_site.py to refresh the site.")
    else:
        print("\nNothing to update.")


if __name__ == "__main__":
    main()
