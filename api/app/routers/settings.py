"""The settings page: the one place the register is told something because
somebody prefers it (ADR-0023).

A route to show and a route to save each tab, and no logic. What a setting is, what it defaults to and what pins it
are all in `settings.py`, which the template reads directly -- the page is a
rendering of those definitions rather than a form that has to be kept in step with
them by hand, which is what makes adding the next preference a row in a tuple.

Nothing here decides who may see it. `_public_page` in auth.py answers no to
anything it does not name, so a path that is not on its list is behind the login
by default, and this one is not on its list.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from .. import labelpreview, labels, settings
from ..db import get_db
from ..forms import Posted, posted
from ..web import templates

router = APIRouter()


# The three tabs that are settings, each a page of its own with its own form, beside
# the two account pages (MANUAL §19). Each saves its own section and nothing else.
TABS = {
    "/settings": settings.APPEARANCE,
    "/settings/labels": settings.LABELS,
    "/settings/server": settings.SERVER,
}


def _page(request: Request, path: str, saved: int) -> Response:
    """A tab. `saved` is how the redirect after a post says it worked -- a banner
    that is in the address rather than in the session, so reloading says it again
    rather than reporting a save that did not just happen."""
    section = TABS[path]
    rows = [d for d in settings.DEFINITIONS if d.section == section]
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            # A fieldset to each group: the Labels tab has one for each of the two
            # labels, headed by the name the owner gave it.
            "sections": settings.fieldsets(rows),
            "order": settings.order,
            "action": path,
            # The browser's own label destination belongs with the site's.
            "device_box": section == settings.LABELS,
            # A picture of each label beside its settings, drawn again as they change
            # (MANUAL §13, "Seeing it as you set it up"), and what the script needs to
            # say what each picture is without asking.
            "previews": (
                {key: labelpreview.shown(key) for key in labels.LABELS}
                if section == settings.LABELS
                else {}
            ),
            "preview_kinds": labelpreview.KINDS,
            "preview_data": labelpreview.script_data() if section == settings.LABELS else None,
            "choices_for": settings.choices_for,
            "value": settings.value,
            "on": settings.on,
            "pinned": settings.pinned,
            # Whether to say at the foot what greyed means: only when there is
            # something greyed on this tab to explain.
            "pinned_any": any(settings.pinned(d) is not None for d in rows),
            "saved": bool(saved),
            "noindex": True,
        },
    )


async def _save(request: Request, path: str, db: Session) -> Response:
    """Save one tab, then redirect to it rather than rendering it here.

    Post/redirect/get, like every other form in the app: a settings page that
    answered a POST with its own HTML would offer to save again on every reload,
    and a browser's back button would keep the offer for as long as the tab lived.
    """
    settings.save(db, await posted(request), TABS[path])
    return RedirectResponse(f"{path}?saved=1", status_code=303)


@router.get("/settings", include_in_schema=False)
def gui_settings(request: Request, saved: int = 0) -> Response:
    return _page(request, "/settings", saved)


@router.get("/settings/labels", include_in_schema=False)
def gui_settings_labels(request: Request, saved: int = 0) -> Response:
    return _page(request, "/settings/labels", saved)


@router.get("/settings/server", include_in_schema=False)
def gui_settings_server(request: Request, saved: int = 0) -> Response:
    return _page(request, "/settings/server", saved)


@router.post("/settings", include_in_schema=False)
async def gui_save_settings(request: Request, db: Session = Depends(get_db)) -> Response:
    return await _save(request, "/settings", db)


@router.post("/settings/labels", include_in_schema=False)
async def gui_save_settings_labels(request: Request, db: Session = Depends(get_db)) -> Response:
    return await _save(request, "/settings/labels", db)


@router.post("/settings/server", include_in_schema=False)
async def gui_save_settings_server(request: Request, db: Session = Depends(get_db)) -> Response:
    return await _save(request, "/settings/server", db)


@router.post("/settings/labels/move", include_in_schema=False)
async def gui_move_in_a_list(request: Request, db: Session = Depends(get_db)) -> Response:
    """One detail up or down a label's list, kept as it is pressed, then back to the
    list it moved in. Its own form and its own route, and not a button of the tab's
    form: the first button of a form is the one Enter in any of its boxes presses,
    and that would be a detail's up. With a script the row moves in the page and is
    kept by Save like any other change, and this is never asked (settings.js)."""
    key = settings.move(db, (await posted(request)).get("move") or "")
    return RedirectResponse(
        "/settings/labels?saved=1" + (f"#{key}" if key else ""), status_code=303
    )


@router.get("/settings/labels/preview.png", include_in_schema=False)
def gui_label_preview(request: Request, label: str = "", kind: str = "") -> Response:
    """One label's picture, for the example of one sort of thing, drawn from the
    settings the page sends rather than the ones saved -- read the way Save reads
    them, and kept nowhere (MANUAL §13, "Seeing it as you set it up").

    A GET with the page's form in its query, so that it can be a picture's address:
    the content policy takes a picture from this site and from nowhere else, and one
    made in the page would come from `blob:` (ADR-0021). Never kept by the browser,
    because its address with nothing sent is the label as saved, and that changes
    whenever Save is pressed."""
    if label not in labels.LABELS or kind not in dict(labelpreview.KINDS):
        raise HTTPException(status_code=404, detail="No such label")
    form = Posted(FormData(request.query_params))
    png = labelpreview.picture(label, kind, settings.unsaved(form, settings.LABELS))
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
