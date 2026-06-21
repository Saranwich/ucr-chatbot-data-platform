"""แจ้งปัญหา (problem report) — LIFF report form: page, submit, image serving.

Flow: GET /report serves the LIFF page; the page POSTs multipart to
/api/form-reports with the user's LIFF access token in the Authorization header;
we verify it (ADR 0004) for a trusted lineuser_id, store the report + image, and
expose the image back via GET /api/form-reports/{id}/image.

Image store is local uploads/ for now (POC); ADR 0005 moves it to S3.
"""
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import LIFF_REPORT_ID
from app.database import get_db
from app.models import FormReport, User
from app.utils.auth import get_current_user
from app.utils.liff_auth import resolve_lineuser_id
from app.utils.storage import save_image, local_file, unique_image_name

router = APIRouter(tags=["report"])

_HTML_FILE = Path(__file__).resolve().parent.parent / "static" / "report_form.html"


def point_wkt(latitude, longitude):
    """PostGIS WKT for a lat/lng pair, or None if either is missing."""
    if latitude is None or longitude is None:
        return None
    return f"SRID=4326;POINT({longitude} {latitude})"


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

    # Ensure the FK target exists before inserting (a LIFF user may be new to us).
    if lineuser_id:
        existing = await db.execute(select(User).where(User.lineuser_id == lineuser_id))
        if existing.scalars().first() is None:
            db.add(User(lineuser_id=lineuser_id))
            await db.flush()

    # image — เก็บผ่าน storage helper กลาง (key 'reports/<uuid>.<ext>')
    image_path = None
    if image is not None and image.filename:
        key = f"reports/{unique_image_name(image.filename)}"
        image_path = save_image(key, await image.read())

    # location — same WKT shape survey_repository uses for PostGIS
    location_data = point_wkt(latitude, longitude)

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
async def form_report_image(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Stream a report's uploaded image (admin only — these are residents' private reports)."""
    result = await db.execute(select(FormReport).where(FormReport.report_id == report_id))
    report = result.scalars().first()
    if report is None or not report.image_path:
        raise HTTPException(status_code=404, detail="No image for this report")
    # image_path เป็น storage key ('reports/<name>'); แถวเก่าเก็บชื่อไฟล์เปล่า ๆ
    # ใต้ uploads/ ตรง ๆ ซึ่ง local_file ก็ resolve ได้เหมือนกัน
    path = local_file(report.image_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Image file missing")
    # บังคับให้เสิร์ฟเป็นรูปเสมอ ไม่ปล่อยให้เดาเป็น text/html (กันไฟล์เก่านามสกุลแปลก ๆ)
    media_type = mimetypes.guess_type(str(path))[0]
    if not media_type or not media_type.startswith("image/"):
        media_type = "image/jpeg"
    return FileResponse(path, media_type=media_type)
