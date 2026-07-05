"""Dev-only data viewer page (the JSON API behind it stays JWT-protected)."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["viewer"])

_VIEWER_HTML = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "viewer.html")


@router.get("/viewer")
async def viewer():
    return FileResponse(_VIEWER_HTML)
