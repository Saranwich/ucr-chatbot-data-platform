"""Form report (LIFF แจ้งปัญหา) data layer — insert + image lookup.

routes/report.py stays thin (page render + auth + multipart parse) and calls
these. Same behavior as before; logic just moved out of the route.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.future import select

from app.models import FormReport, User
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
    image_path = None
    if image_bytes is not None and image_filename:
        key = f"reports/{unique_image_name(image_filename)}"
        image_path = save_image(key, image_bytes)

    report = FormReport(
        lineuser_id=lineuser_id,
        description=description,
        category=category,
        location_data=point_wkt(latitude, longitude),
        image_path=image_path,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report.report_id


async def image_path(db, report_id: int) -> str:
    """Resolved local path to a report's uploaded image (404 if missing)."""
    result = await db.execute(select(FormReport).where(FormReport.report_id == report_id))
    report = result.scalars().first()
    if report is None or not report.image_path:
        raise HTTPException(status_code=404, detail="No image for this report")
    # image_path เป็น storage key ('reports/<name>'); แถวเก่าเก็บชื่อไฟล์เปล่า ๆ
    # ใต้ uploads/ ตรง ๆ ซึ่ง local_file ก็ resolve ได้เหมือนกัน
    path = local_file(report.image_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Image file missing")
    return path
