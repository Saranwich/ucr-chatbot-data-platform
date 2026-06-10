"""แจ้งปัญหา (problem report) — LIFF report form: page, submit, image serving.

Flow: GET /report serves the LIFF page; the page POSTs multipart to
/api/form-reports with the user's LIFF access token in the Authorization header;
we verify it (ADR 0004) for a trusted lineuser_id, store the report + image, and
expose the image back via GET /api/form-reports/{id}/image.

Image store is local uploads/ for now (POC); ADR 0005 moves it to S3.
"""
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import LIFF_ID
from app.database import get_db
from app.models import FormReport, User
from app.utils.liff_auth import resolve_lineuser_id

router = APIRouter(tags=["report"])

_HTML_FILE = Path(__file__).resolve().parent.parent / "static" / "report_form.html"
_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


@router.get("/report", response_class=HTMLResponse)
async def report_page():
    """Serve the LIFF report form, injecting the LIFF id (empty = anonymous dev mode)."""
    html = _HTML_FILE.read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__LIFF_ID__", LIFF_ID or ""))


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

    # Ensure the FK target exists before inserting (a LIFF user may be new to us).
    if lineuser_id:
        existing = await db.execute(select(User).where(User.lineuser_id == lineuser_id))
        if existing.scalars().first() is None:
            db.add(User(lineuser_id=lineuser_id))
            await db.flush()

    # image — POC: save bytes under uploads/, store the filename only (ADR 0005 → S3)
    image_path = None
    if image is not None and image.filename:
        ext = os.path.splitext(image.filename)[1] or ".jpg"
        fname = f"{uuid.uuid4().hex}{ext}"
        _UPLOAD_DIR.mkdir(exist_ok=True)
        (_UPLOAD_DIR / fname).write_bytes(await image.read())
        image_path = fname

    # location — same WKT shape survey_repository uses for PostGIS
    location_data = None
    if latitude is not None and longitude is not None:
        location_data = f"SRID=4326;POINT({longitude} {latitude})"

    report = FormReport(
        lineuser_id=lineuser_id,
        description=description,
        category=category,
        location_data=location_data,
        image_path=image_path,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return {"ok": True, "report_id": report.report_id}


@router.get("/api/form-reports/{report_id}/image")
async def form_report_image(report_id: int, db: AsyncSession = Depends(get_db)):
    """Stream a report's uploaded image from uploads/ (404 if none)."""
    result = await db.execute(select(FormReport).where(FormReport.report_id == report_id))
    report = result.scalars().first()
    if report is None or not report.image_path:
        raise HTTPException(status_code=404, detail="No image for this report")
    path = _UPLOAD_DIR / report.image_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(path)
