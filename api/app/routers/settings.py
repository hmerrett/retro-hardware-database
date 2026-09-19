"""The settings page: the one place the register is told something because
somebody prefers it (ADR-0023).

Two routes and no logic. What a setting is, what it defaults to and what pins it
are all in `settings.py`, which the template reads directly -- the page is a
rendering of those definitions rather than a form that has to be kept in step with
them by hand, which is what makes adding the next preference a row in a tuple.

Nothing here decides who may see it. `_public_page` in auth.py answers no to
anything it does not name, so a path that is not on its list is behind the login
by default, and this one is not on its list.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from .. import settings
from ..db import get_db
from ..forms import posted
from ..web import templates

router = APIRouter()


@router.get("/settings", include_in_schema=False)
def gui_settings(request: Request, saved: int = 0) -> Response:
    """The page. `saved` is how the redirect after a post says it worked -- a
    banner that is in the address rather than in the session, so reloading says it
    again rather than reporting a save that did not just happen."""
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "definitions": settings.DEFINITIONS,
            "value": settings.value,
            "on": settings.on,
            "pinned": settings.pinned,
            "saved": bool(saved),
            "noindex": True,
        },
    )


@router.post("/settings", include_in_schema=False)
async def gui_save_settings(request: Request, db: Session = Depends(get_db)) -> Response:
    """Save, then redirect to the page rather than rendering it here.

    Post/redirect/get, like every other form in the app: a settings page that
    answered a POST with its own HTML would offer to save again on every reload,
    and a browser's back button would keep the offer for as long as the tab lived.
    """
    settings.save(db, await posted(request))
    return RedirectResponse("/settings?saved=1", status_code=303)
