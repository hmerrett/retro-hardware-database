"""The two pages of figures: what the register adds up to, and who has been reading it.

/stats draws a handful of the facts stats.py counts, and is the only page whose
content changes between two looks at it. /traffic is not the register at all -- it
is the report GoAccess writes from the access logs, handed out as it was written,
and it is behind the login because who reads the site is the owner's business.
"""
import os
import random
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..common import RELIABILITY_MIN, _maker_reliability
from ..db import get_db
from ..stats import FACTS_SHOWN, _collection_stats, _facts
from ..web import _og, templates

router = APIRouter()


# GoAccess writes a self-contained traffic report here (read-only mount from the
# shared volume). The route is login-only via the auth gate above.
STATS_DIR = Path(os.getenv("RHDB_STATS_DIR", "/app/stats"))

@router.get("/traffic", response_class=HTMLResponse, include_in_schema=False)
def gui_traffic():
    report = STATS_DIR / "index.html"
    if not report.exists():
        return HTMLResponse(
            "<p style='font-family:system-ui;margin:2rem'>No traffic report yet "
            "&mdash; it is generated from the access logs every five minutes, so "
            "check back shortly.</p>")
    return HTMLResponse(report.read_text(encoding="utf-8"))

# --- the pointless department -----------------------------------------------
# Figures that answer nothing anyone needs to know, which is the point of them. A
# page of totals says how big the collection is; these say what it is like.







@router.get("/stats", response_class=HTMLResponse, include_in_schema=False)
def gui_stats(request: Request, db: Session = Depends(get_db)):
    this_year = date.today().year
    st = _collection_stats(db)
    # A different handful each time the page is looked at. The pool is only the
    # figures that have something to say today, so the draw is never padded with
    # blanks.
    #
    # Shuffled and then taken one at a time, skipping any figure whose headline a
    # tile in this draw already shows: the storage total and the hard disks that are
    # very nearly all of it both read "2464.1 GiB" here, and two tiles showing one
    # number looks like the shuffle is broken rather than like two facts. Same reason
    # "arrived this year" stands down when this year is also the busiest.
    pool = _facts(db, st, this_year)
    drawn, seen = [], set()
    for fact in random.sample(pool, len(pool)):
        if fact["v"] in seen:
            continue
        seen.add(fact["v"])
        drawn.append(fact)
        if len(drawn) == FACTS_SHOWN:
            break
    st["facts"] = drawn
    st["n_facts"] = len(pool)
    rel = _maker_reliability(db)
    # Shaped for the rank macro here rather than in the template: (label, bar, the
    # value /browse needs). The macro takes rows, not a data model.
    st["reliability_rank"] = [(maker, pct, maker) for maker, _n, _w, pct in rel]
    st["reliability_min"] = RELIABILITY_MIN
    # The description a crawler or a chat window sees is the collection, not
    # whichever eight figures this particular render drew.
    blurb = (f"{st['n_total']} things in the register: {st['n_computers']} machines "
             f"and {st['n_parts']} parts, averaging {st['mean_year']}.")
    return templates.TemplateResponse(request, "stats.html", {
        "st": st, "this_year": this_year,
        "og": _og(request, "The collection by numbers", blurb)})
