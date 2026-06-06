from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import User, SurveySession, CompletedReport


async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.lineuser_id == user_id))
    user = result.scalars().first()
    if not user:
        user = User(lineuser_id=user_id)
        db.add(user)
        await db.flush()
    return user


async def clear_session(db: AsyncSession, user_id: str):
    """Delete any existing session so a survey starts fresh."""
    result = await db.execute(select(SurveySession).where(SurveySession.lineuser_id == user_id))
    existing = result.scalars().first()
    if existing:
        await db.delete(existing)
        await db.flush()


async def create_session(db: AsyncSession, user_id: str, survey_version: str, start_route_id: str) -> SurveySession:
    session = SurveySession(
        lineuser_id=user_id,
        survey_version=survey_version,
        current_route_id=start_route_id,
        current_step=0,
        route_history=[],
        payload={},
    )
    db.add(session)
    await db.commit()
    return session


async def load_session(db: AsyncSession, user_id: str) -> Optional[SurveySession]:
    result = await db.execute(select(SurveySession).where(SurveySession.lineuser_id == user_id))
    return result.scalars().first()


async def save_session(db: AsyncSession):
    """Persist in-place mutations made to the active session."""
    await db.commit()


async def mark_profile_completed(db: AsyncSession, user_id: str):
    """Flag the user as profiled. Does not commit — the caller's save_session does."""
    result = await db.execute(select(User).where(User.lineuser_id == user_id))
    user = result.scalars().first()
    if user:
        user.has_completed_profile = 1


async def finalize_report(db: AsyncSession, session: SurveySession):
    """Turn a finished session into a CompletedReport and delete the session."""
    postgis_point = build_location_point(session.payload)
    report = CompletedReport(
        lineuser_id=session.lineuser_id,
        survey_version=session.survey_version,
        payload=session.payload,
        location_data=postgis_point,
    )
    db.add(report)
    await db.delete(session)
    await db.commit()


def build_location_point(payload: dict) -> Optional[str]:
    """Pure — the PostGIS POINT for the first location answer in the payload.

    Scans the payload values for a dict carrying lat/lng and returns its
    `SRID=4326;POINT(lng lat)` representation, or None when there is no
    location answer.
    """
    loc = next(
        (v for v in payload.values() if isinstance(v, dict) and "lat" in v and "lng" in v),
        None,
    )
    if not loc:
        return None
    return f"SRID=4326;POINT({loc['lng']} {loc['lat']})"
