"""Report persistence (V2) — insert into the central `reports` table.

# ponytail: this used to be a CSV stand-in that mirrored the full reports schema;
# the swap to Postgres is this single seam (async). category string → category_id FK
# (unknown value = null, see below); location string → location_text; location_data
# (geometry) stays null for AI reports until the location-pin upgrade (DBML defers).
"""
from sqlalchemy import select

from app.database.database_manager import get_session
from app.models import Report, ReportImage, Category, Community, User


async def category_id_for(db, category: str | None):
    """categories.value → id, or None. Shared by every reports writer.

    # ponytail: enum is locked at the tool spec + seeded categories, so create-if-missing
    # is out of scope — an unknown value (drift) lands null rather than inventing a row.
    """
    if not category:
        return None
    return await db.scalar(select(Category.id).where(Category.value == category))


async def community_id_for(db, lineuser_id: str | None):
    """Best-effort community snapshot from the user's profile (FK, else legacy varchar)."""
    user = await db.get(User, lineuser_id) if lineuser_id else None
    if user is None:
        return None
    if user.community_id is not None:
        return user.community_id
    if user.community:
        return await db.scalar(select(Community.community_id).where(Community.name == user.community))
    return None


async def community_id_by_name(db, name: str | None):
    """communities.name → id, or None (ชื่อจาก forecast อาจสะกดไม่ตรง — exact match เท่านั้น)"""
    if not name:
        return None
    return await db.scalar(select(Community.community_id).where(Community.name == name))


# สเต็ปของ broadcast flow ที่ยังกรอกไม่จบ — ต้องตรงกับ _AWAITING ใน broadcast_flow_handler
BROADCAST_AWAITING = ("awaiting_note", "awaiting_location", "awaiting_photo")


async def has_unfinished_broadcast(db, lineuser_id: str) -> bool:
    """user ยังค้าง broadcast flow เก่าอยู่ไหม — ห้ามยิง alert ใหม่ใส่ (state machine จะชนกัน:
    ปุ่ม "ใช่" ที่กดจะโดน get_active_report ดักไปเป็น note ของเรื่องเก่า)"""
    found = await db.scalar(
        select(Report.report_id)
        .where(
            Report.lineuser_id == lineuser_id,
            Report.source == "broadcast",
            Report.status.in_(BROADCAST_AWAITING),
        )
        .limit(1)
    )
    return found is not None


async def save(lineuser_id: str, report: dict) -> int:
    """Insert one extracted report; return its report_id.

    `report` carries the tool args (category/notes/severity/title/location) plus the
    producer-set fields the record() hook adds (source/status/is_complete). Optional
    keys (conversation_id/community_id/source_ref/payload/…) default to null.
    Attachments the user sent mid-chat ride along as lat/lon (→ PostGIS point)
    and image_keys (→ report_images rows).
    """
    lat, lon = report.get("lat"), report.get("lon")
    location_data = f"SRID=4326;POINT({lon} {lat})" if lat is not None and lon is not None else None
    async with get_session() as db:
        row = Report(
            conversation_id=report.get("conversation_id"),
            lineuser_id=lineuser_id or None,
            community_id=report.get("community_id") or await community_id_for(db, lineuser_id),
            source=report.get("source"),
            source_ref=report.get("source_ref"),
            category_id=await category_id_for(db, report.get("category")),
            notes=report.get("notes"),
            severity=report.get("severity"),
            title=report.get("title"),
            status=report.get("status"),
            is_complete=bool(report.get("is_complete")),
            location_text=report.get("location"),  # tool arg 'location' → column location_text
            location_data=location_data,
            extraction_confidence=report.get("extraction_confidence"),
            confidence_by_field=report.get("confidence_by_field"),
            payload=report.get("payload"),
        )
        db.add(row)
        await db.flush()  # ได้ report_id ก่อน commit — ให้แถวรูป FK ชี้ได้
        for key in report.get("image_keys") or ():
            db.add(ReportImage(report_id=row.report_id, image_key=key))
        await db.commit()
        await db.refresh(row)
        return row.report_id
