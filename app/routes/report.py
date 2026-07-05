"""แจ้งปัญหา (problem report) — LIFF report form: page, submit, image serving.

Flow: GET /report serves the LIFF page; the page POSTs multipart to
/api/form-reports with the user's LIFF access token in the Authorization header;
we verify it (ADR 0004) for a trusted lineuser_id, store the report + image, and
expose the image back via GET /api/form-reports/{id}/image.

Thin route — DB + image logic lives in services/form_report.py.
"""
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import LIFF_REPORT_ID
from app.database import get_db
from app.utils.auth import get_current_user
from app.utils.liff_auth import resolve_lineuser_id
from app.services import form_report as form_report_service

router = APIRouter(tags=["report"])

_HTML_FILE = Path(__file__).resolve().parent.parent / "static" / "report_form.html"


@router.get("/report", response_class=HTMLResponse)
async def report_page():
    """Serve the LIFF report form, injecting the LIFF id (empty = anonymous dev mode)."""
    html = _HTML_FILE.read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__LIFF_ID__", LIFF_REPORT_ID or ""))


@router.post("/api/form-reports")
async def submit_form_report(
    description: str = Form(...),
    category: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    image: Optional[UploadFile] = File(None),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    lineuser_id = await resolve_lineuser_id(authorization)
    has_image = image is not None and image.filename
    image_bytes = await image.read() if has_image else None
    image_filename = image.filename if has_image else None

    report_id = await form_report_service.create(
        db, lineuser_id, description, category, latitude, longitude,
        image_bytes, image_filename,
    )
    return {"ok": True, "report_id": report_id}


@router.get("/api/form-reports/{report_id}/image")
async def form_report_image(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Stream a report's uploaded image (admin only — these are residents' private reports)."""
    path = await form_report_service.image_path(db, report_id)
    # บังคับให้เสิร์ฟเป็นรูปเสมอ ไม่ปล่อยให้เดาเป็น text/html (กันไฟล์เก่านามสกุลแปลก ๆ)
    media_type = mimetypes.guess_type(str(path))[0]
    if not media_type or not media_type.startswith("image/"):
        media_type = "image/jpeg"
    return FileResponse(path, media_type=media_type)
