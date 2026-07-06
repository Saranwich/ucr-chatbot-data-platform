"""Weather broadcast home (V2, Pim). Push/trigger side + outreach log.

The broadcast REPLY flow lives in handlers/broadcast_flow_handler.py; the push/
trigger side lands here. For M3 this owns the outreach push-log (DBML: outreach) +
the anti-spam frequency cap — the queryable "who did we ping, when, did they reply".

# ponytail: the actual push (LINE multicast) is still Pim's stub — these two helpers
# are the DB seam it will call: log_outreach() after each push, recently_contacted()
# before it (cap).
"""
from datetime import timedelta

from sqlalchemy import func, select

from app.database.database_manager import get_session
from app.models import Outreach
from app.models._common import get_bangkok_now

# ponytail: cap window hardcoded ~1 week — the designed policy ("~สัปดาห์ละครั้ง").
# Move to config / a policy table when the broadcast scheduler is built.
CAP_DAYS = 7


async def log_outreach(lineuser_id: str, alert_type: str,
                       community_id: int | None = None,
                       conversation_id: int | None = None) -> int:
    """Record one push (1 push = 1 row); return its outreach_id.

    response stays null until the user replies (broadcast_flow_handler links it back).
    """
    async with get_session() as db:
        row = Outreach(
            lineuser_id=lineuser_id, alert_type=alert_type,
            community_id=community_id, conversation_id=conversation_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.outreach_id


async def recently_contacted(lineuser_id: str, within_days: int = CAP_DAYS) -> bool:
    """Frequency cap: True if this user was pushed within the window (skip re-pinging)."""
    async with get_session() as db:
        last = await db.scalar(
            select(func.max(Outreach.sent_at)).where(Outreach.lineuser_id == lineuser_id)
        )
    if last is None:
        return False
    return last >= get_bangkok_now() - timedelta(days=within_days)
