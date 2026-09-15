from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from app.clients import psql
from app.core.config import UPLOAD_DIR


def _image_url(image_id: UUID) -> str:
    return f"/api/dashboard/images/{image_id}"


async def _attach_media(reports: list[dict]) -> list[dict]:
    if not reports:
        return reports

    report_ids = [report["id"] for report in reports]
    locations = await psql.get_locations_of_reports(report_ids)
    images = await psql.get_images_of_reports(report_ids)

    by_id = {report["id"]: report for report in reports}
    for report in reports:
        report["locations"] = []
        report["images"] = []
    for location in locations:
        by_id[location.pop("report_id")]["locations"].append(location)
    for image in images:
        image["url"] = _image_url(image["id"])
        by_id[image.pop("report_id")]["images"].append(image)
    return reports


async def list_reports(
    limit: int, offset: int, report_type: str | None = None, days: int | None = None
) -> dict:
    total = await psql.count_reports(report_type, days)
    reports = await _attach_media(await psql.get_reports(limit, offset, report_type, days))
    for report in reports:
        report.pop("session_id")
    return {"items": reports, "total": total}


async def get_report(report_id: UUID) -> dict | None:
    report = await psql.get_report(report_id)
    if report is None:
        return None
    return (await _attach_media([report]))[0]


async def get_statistics(days: int = 30) -> dict:
    totals = await psql.get_entity_totals()
    session_counts = await psql.get_session_status_counts()
    coverage = await psql.get_report_media_coverage(days)
    type_counts = await psql.get_report_type_counts(days)
    daily_counts = await psql.get_report_daily_counts(days)
    return {
        "period_days": days,
        "users": {"total": totals["users"]},
        "sessions": {
            "total": totals["sessions"],
            "by_status": {row["status"]: row["count"] for row in session_counts},
        },
        "reports": {
            "total": coverage["total"],
            "by_type": {row["type"]: row["count"] for row in type_counts},
            "by_day": daily_counts,
            "with_image": coverage["with_image"],
            "with_location": coverage["with_location"],
            "with_both": coverage["with_both"],
            "without_media": coverage["without_media"],
        },
        "images": {"total": totals["images"]},
        "locations": {"total": totals["locations"]},
    }


async def list_users(limit: int, offset: int) -> dict:
    total = await psql.count_users()
    return {"items": await psql.get_users(limit, offset), "total": total}


async def get_image_path(image_id: UUID) -> Path | None:
    """แปลง image_key ที่เก็บไว้เป็นไฟล์จริงใต้ UPLOAD_DIR

    คีย์ที่ชี้ออกนอก UPLOAD_DIR คืน None ทิ้ง ไม่ให้ใครอ่านไฟล์อื่นในเครื่องผ่าน endpoint รูป
    """
    image_key = await psql.get_image_key(image_id)
    if not image_key:
        return None

    key = Path(image_key)
    if key.is_absolute():
        return None
    parts: Iterable[str] = key.parts
    if key.parts and key.parts[0] == "uploads":
        parts = key.parts[1:]
    candidate = UPLOAD_DIR.joinpath(*parts).resolve()
    try:
        candidate.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
