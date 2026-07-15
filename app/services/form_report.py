"""Form report (LIFF แจ้งปัญหา) data layer — insert + image lookup.

routes/report.py stays thin (page render + auth + multipart parse) and calls
these. Same behavior as before; logic just moved out of the route.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.future import select

from app.models import User, Report, ReportImage
from app.services import report as report_service
from app.utils.storage import save_image, local_file, unique_image_name


def point_wkt(latitude, longitude):
    """PostGIS WKT for a lat/lng pair, or None if either is missing."""
    if latitude is None or longitude is None:
        return None
    return f"SRID=4326;POINT({longitude} {latitude})"


async def create(db, lineuser_id, description, category, latitude, longitude,
                 image_bytes: Optional[bytes], image_filename: Optional[str]) -> int:
    """Insert one form report (+ optional image); return its report_id."""
    # Ensure the FK target exists before inserting (a LIFF user may be new to us).
    if lineuser_id:
        existing = await db.execute(select(User).where(User.lineuser_id == lineuser_id))
        if existing.scalars().first() is None:
            db.add(User(lineuser_id=lineuser_id))
            await db.flush()

    # image — เก็บผ่าน storage helper กลาง (key 'reports/<uuid>.<ext>')
    image_path_key = None
    if image_bytes is not None and image_filename:
        key = f"reports/{unique_image_name(image_filename)}"
        image_path_key = save_image(key, image_bytes)

    # Write ONLY the unified reports row (source='form_report') — dashboard V2 reads
    # this single table. The legacy form_reports write was dropped in M4.
    report = Report(
        lineuser_id=lineuser_id or None,
        community_id=await report_service.community_id_for(db, lineuser_id),
        source="form_report",
        category_id=await report_service.category_id_for(db, category),
        notes=description,
        status="new",
        is_complete=True,
        location_data=point_wkt(latitude, longitude),
    )
    db.add(report)
    await db.flush()
    if image_path_key:
        db.add(ReportImage(report_id=report.report_id, image_key=image_path_key))

    await db.commit()
    await db.refresh(report)
    return report.report_id


async def image_path(db, report_id: int) -> str:
    """Resolved local path to a report's uploaded image (404 if missing).

    Reads report_images (V2) — the report_id is a reports.report_id. Serves the
    first image if several exist.
    """
    key = await db.scalar(
        select(ReportImage.image_key)
        .where(ReportImage.report_id == report_id)
        .order_by(ReportImage.image_id)
    )
    path = local_file(key) if key else None
    if path is None:
        raise HTTPException(status_code=404, detail="No image for this report")
    return path
