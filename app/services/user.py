"""User service — the users table lives here (get/create/update)."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import User


async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Return the User row, creating an empty one on first contact."""
    result = await db.execute(select(User).where(User.lineuser_id == user_id))
    user = result.scalars().first()
    if not user:
        user = User(lineuser_id=user_id)
        db.add(user)
        await db.flush()
    return user
