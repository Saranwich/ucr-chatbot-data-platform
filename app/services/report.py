"""Report persistence (V2) — insert into the central `reports` table.

# ponytail: this used to be a CSV stand-in that mirrored the full reports schema;
# the swap to Postgres is this single seam (async). category string → category_id FK
# (unknown value = null, see below); location string → location_text; location_data
# (geometry) stays null for AI reports until the location-pin upgrade (DBML defers).
"""
from sqlalchemy import select

from app.database.database_manager import get_session
from app.models import Report, Category, Community, User


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


async def save(lineuser_id: str, report: dict) -> int:
    """Insert one extracted report; return its report_id.

    `report` carries the tool args (category/notes/severity/title/location) plus the
    producer-set fields the record() hook adds (source/status/is_complete). Optional
    keys (conversation_id/community_id/source_ref/payload/…) default to null.
    """
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
            extraction_confidence=report.get("extraction_confidence"),
            confidence_by_field=report.get("confidence_by_field"),
            payload=report.get("payload"),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.report_id
