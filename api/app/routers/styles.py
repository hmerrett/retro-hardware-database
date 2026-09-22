"""The generated stylesheets, served like static ones.

They are routes rather than files under /static because nothing writes them to
disk. One is built from the colour vocabulary at import (see datacss); the other
is built from the accent setting, and so is rebuilt whenever the owner answers it.
Everything else about them is the same as a file's: one URL, a stamp of the
contents in the query string, and a year in a cache once asked for by that stamp.
"""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .. import settings
from ..datacss import DATA_CSS

router = APIRouter()


@router.get("/style/data.css", include_in_schema=False)
def data_css(request: Request) -> Response:
    """The rules whose values are data. Public, like the stylesheet beside it: a
    page a stranger may read is a page they may read the styling of."""
    stamped = "v" in request.query_params
    return Response(
        DATA_CSS,
        media_type="text/css",
        headers={
            "Cache-Control": (
                "public, max-age=31536000, immutable" if stamped else "public, max-age=3600"
            )
        },
    )


@router.get("/style/accent.css", include_in_schema=False)
def accent_css(request: Request) -> Response:
    """The installation's accent, worked out for the preset in force.

    Public, like the stylesheets beside it. It is also the one generated sheet
    whose contents can change while the site is up, which is what the stamp is
    for: `base.html` asks for it by a hash of what this returns, so a browser
    holding last week's colour for a year is asking for a different URL.
    """
    stamped = "v" in request.query_params
    return Response(
        settings.accent_css(),
        media_type="text/css",
        headers={
            "Cache-Control": (
                "public, max-age=31536000, immutable" if stamped else "public, max-age=60"
            )
        },
    )
