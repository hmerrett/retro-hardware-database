"""The chrome's own small route: folding the side rail away, and opening it again.

A link rather than a script, which is what makes it work on a browser running
none: the link asks the server to remember, the server writes the cookie and sends
the page back the other way round. It is the device's answer and not the
installation's -- the wide screen in the workshop can hold the rail open while the
laptop folds it away -- which is why it is a cookie and never a row in `setting`
(ADR-0023).

A GET that writes a cookie, and deliberately: nothing on the server changes, so
there is nothing for a POST to protect. The worst a forged one can do is fold
somebody's rail, which they unfold by pressing the thing that is now labelled
Expand.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..rail import COOKIE, OPEN, SHUT
from ..web import _safe_next

router = APIRouter()

# Long enough that a rail folded once stays folded, and the same shape as the
# other two choices a reader is allowed to keep.
KEEP = 60 * 60 * 24 * 365


@router.get("/rail/{state}", include_in_schema=False)
def rail_state(state: str, request: Request) -> RedirectResponse:
    """Fold or unfold the rail, and go back to the page it was asked from.

    Public, because a visitor has a rail too. `next` is checked before it is
    followed: a redirect that will take any address it is handed is an open
    redirect, whatever it was built for.
    """
    if state not in (OPEN, SHUT):
        raise HTTPException(status_code=404)
    resp = RedirectResponse(_safe_next(request.query_params.get("next", "/")), status_code=303)
    if state == SHUT:
        resp.set_cookie(
            COOKIE,
            SHUT,
            max_age=KEEP,
            httponly=True,
            samesite="lax",
            secure=request.headers.get("x-forwarded-proto") == "https",
        )
    else:
        # Deleted rather than set to "open": the rail standing open is the state a
        # browser that has never been asked is already in, and a cookie saying so
        # is a cookie stored for nothing.
        resp.delete_cookie(COOKIE)
    return resp
