"""The generated stylesheet, served like a static one.

It is a route rather than a file under /static because its rules are built from
the colour vocabulary at import (see datacss) -- there is nothing on disk to
mount. Everything else about it is the same: one URL, a stamp of its contents in
the query string, and a year in a cache once it has been asked for by that stamp.
"""

from fastapi import APIRouter, Request
from fastapi.responses import Response

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
