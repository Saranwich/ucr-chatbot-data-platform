"""Conversation anchor (V2) — one lightweight row per AI chat (DBML: conversations).

No transcript body here: live turns live in Redis (session.py), the full transcript
is archived through the storage seam (session.dump_transcript). This table is the
queryable anchor + the archive_key pointer, so reports can FK to the chat that
produced them.
"""
from sqlalchemy import select, update

from app.database.database_manager import get_session
from app.models import Conversation


async def ensure_active(lineuser_id: str, trigger: str = "user_initiated") -> int:
    """Return the user's active conversation id, creating one if none is open.

    Reuses the (lineuser_id, status) index — one chat = one anchor even when the
    user reports several problems in the same session.
    """
    async with get_session() as db:
        cid = await db.scalar(
            select(Conversation.conversation_id)
            .where(Conversation.lineuser_id == lineuser_id, Conversation.status == "active")
            .order_by(Conversation.conversation_id.desc())
        )
        if cid is not None:
            return cid
        row = Conversation(lineuser_id=lineuser_id, trigger=trigger, status="active")
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.conversation_id


async def attach_archive(conversation_id: int, archive_key: str | None) -> None:
    """Point the anchor at the dumped transcript (backup pointer).

    # ponytail: status stays 'active' — V2 sessions have no end hook (they just
    # TTL-expire in Redis), so a later sweep flips active→done/abandoned + sets
    # ended_at. For now the anchor + archive_key are enough for insight queries.
    """
    async with get_session() as db:
        await db.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(archive_key=archive_key)
        )
        await db.commit()
