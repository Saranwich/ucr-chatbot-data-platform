"""User service — the users table lives here (get/create/update)."""
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import Community, User


async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Return the User row, creating an empty one on first contact."""
    result = await db.execute(select(User).where(User.lineuser_id == user_id))
    user = result.scalars().first()
    if not user:
        user = User(lineuser_id=user_id)
        db.add(user)
        await db.flush()
    return user


async def get_users_by_community(db: AsyncSession, community_name: str) -> list[str]:
    """lineuser_id ของทุกคนในชุมชนนี้ — FK เป็นหลัก, legacy varchar กันตก

    คนที่ยังไม่กรอกชุมชนใน profile ไม่ติดมาด้วย (นโยบาย broadcast: ไม่รู้พื้นที่ = ข้าม)
    """
    result = await db.execute(
        select(User.lineuser_id)
        .outerjoin(Community, User.community_id == Community.community_id)
        .where(or_(Community.name == community_name, User.community == community_name))
    )
    return list(result.scalars().all())


async def get_profile(db: AsyncSession, lineuser_id: str) -> dict:
    """Profile fields for the Userdata LIFF (empty shape if no row yet)."""
    result = await db.execute(select(User).where(User.lineuser_id == lineuser_id))
    user = result.scalars().first()
    if user is None:
        # ยังไม่เคยมีแถว (เช่น เปิด LIFF ก่อนเคยคุยกับบอท) — ฟอร์มเปล่า
        return {"nickname": None, "age_range": None, "gender": None, "community": None,
                "has_completed_profile": False}
    return {
        "nickname": user.nickname,
        "age_range": user.age_range,
        "gender": user.gender,
        "community": user.community,
        "has_completed_profile": bool(user.has_completed_profile),
    }


async def save_profile(db: AsyncSession, lineuser_id: str, profile) -> None:
    """Upsert the profile columns; marks the profile complete."""
    result = await db.execute(select(User).where(User.lineuser_id == lineuser_id))
    user = result.scalars().first()
    if user is None:
        user = User(lineuser_id=lineuser_id)
        db.add(user)

    user.nickname = profile.nickname
    user.age_range = profile.age_range
    user.gender = profile.gender
    user.community = profile.community
    user.has_completed_profile = 1
    await db.commit()
