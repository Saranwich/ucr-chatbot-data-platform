"""Weather broadcast home (V2, Pim). Push/trigger side + outreach log.

The broadcast REPLY flow is the AI conversation (ai_tool.build_broadcast_reply,
armed by the Redis broadcast_mode flag); the push/trigger side lands here:
run_broadcast() is the orchestrator that only "connects" the one-thing services
(forecast → weather_broadcast → user → broadcast) — no domain logic of its own.
This file also owns the outreach push-log (DBML: outreach) + the anti-spam
frequency cap — the queryable "who did we ping, when, did they reply".
"""
import datetime as dt
from datetime import timedelta

from sqlalchemy import func, select

from app.database.database_manager import get_session
from app.models import Outreach
from app.models._common import get_bangkok_now
from app.services import broadcast, forecast, session, weather_broadcast
from app.services.report import community_id_by_name
from app.services.user import get_users_by_community

_BANGKOK = dt.timezone(dt.timedelta(hours=7))

# ponytail: cap window hardcoded ~1 week — the designed policy ("~สัปดาห์ละครั้ง").
# Move to config / a policy table when the broadcast scheduler is built.
CAP_DAYS = 7


async def log_outreach(lineuser_id: str, alert_type: str,
                       community_id: int | None = None,
                       conversation_id: int | None = None) -> int:
    """Record one push (1 push = 1 row); return its outreach_id.

    response stays null until "declined/answered" gets wired back (deferred — #106 ข้อ 4).
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


async def run_broadcast(date=None, force: bool = False, only_due: bool = False) -> dict:
    """เชื่อม pipeline ทั้งเส้น: forecast → ตัดสิน alert → หาผู้รับ → push → log

    date=None คือวันนี้ (เวลาไทย) / force=True ข้าม cap 7 วัน (คันโยกเดโม่ —
    แต่ "ค้าง flow เก่า" ห้ามข้ามเสมอ) / only_due=True ส่งเฉพาะ event ที่ time
    ตกในชั่วโมงนี้ (โหมด scheduler; โหมดกดเองส่งทันทีไม่สนเวลา)
    """
    summary = {"status": "ok", "communities": [], "sent": [], "failed": [],
               "skipped_cap": [], "skipped_active": [], "unmatched": []}

    data = await forecast.get_daily(date)
    if data is None:                                    # วันนั้นไม่มีไฟล์ = ไม่มีอะไรต้องแจ้ง
        summary["status"] = "no-forecast"
        return summary

    events = weather_broadcast.pick_strongest_per_location(
        weather_broadcast.parse_forecast(data))
    if only_due:
        events = weather_broadcast.filter_due(events, dt.datetime.now(_BANGKOK))

    for event in events:
        name = event["community"]

        async with get_session() as db:
            community_id = await community_id_by_name(db, name)
            if community_id is None:
                summary["unmatched"].append(name)
                print(f"⚠️ broadcast: ชุมชนใน forecast ไม่แมตช์ตาราง communities: {name!r}")
                continue
            user_ids = await get_users_by_community(db, name)

            recipients = []
            for uid in user_ids:
                # กำลังคุยตอบ alert อยู่ (Redis broadcast_mode) — ห้ามยิงทับเสมอ แม้ force
                if await session.get_broadcast_mode(uid):
                    summary["skipped_active"].append(uid)
                elif not force and await recently_contacted(uid):
                    summary["skipped_cap"].append(uid)
                else:
                    recipients.append(uid)

        # ลง summary เสมอ แม้ 0 ผู้รับ — "ชุมชนนี้มี alert แต่ไม่มีใครให้ส่ง" ต้องมองเห็น
        entry = {"community": name, "alert": event["alert"],
                 "users": len(user_ids), "sent": 0}
        summary["communities"].append(entry)
        if not recipients:
            continue

        messages = weather_broadcast.to_sdk_messages(
            weather_broadcast.build_message(event["alert"]))
        result = await broadcast.push_to_users(recipients, messages)

        summary["sent"] += result["sent"]
        summary["failed"] += result["failed"]
        entry["sent"] = len(result["sent"])
        for uid in result["sent"]:
            await log_outreach(uid, event["alert"], community_id=community_id)

    return summary
