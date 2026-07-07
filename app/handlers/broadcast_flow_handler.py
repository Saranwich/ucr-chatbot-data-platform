"""
broadcast_flow_handler.py — สัญญาปุ่มของ weather broadcast + ทางปุ่ม "ไม่"

การเก็บข้อมูลหลัง user กด "ใช่" เป็นหน้าที่ AI แล้ว (ai_tool.build_broadcast_reply
ผ่าน Redis broadcast_mode) — state machine awaiting_* เดิมถูกลบหลัง DB ไม่เหลือ
แถวค้าง (0 rows, 2026-07-07) เหลือไว้เฉพาะของที่ message_handler ยังใช้จริง
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report
from app.services import report as report_service
from app.services.line import reply_text

# ── สัญญากับปุ่มใน broadcast (ต้องตรงกับ text ใน weather_broadcast._MESSAGE_CONFIG) ──
YES_MAP = {                              # ปุ่ม "ใช่" → alert_type
    "มีน้ำท่วมขัง": "flood",
    "ร้อนมาก": "heat",
    "ทั้งฝนทั้งร้อน": "both",
}
NO_MAP = {                               # ปุ่ม "ไม่" → alert_type (ไว้เก็บแถวปฏิเสธ)
    "ไม่ท่วม": "flood",
    "ไม่ร้อน": "heat",
    "ปกติดี": "both",
}

DECLINE = "ขอบคุณที่บอกนะคะ 🙏 ดูแลสุขภาพด้วยนะคะ 😊"

# broadcast alert_type → หมวดหลักในตาราง categories
# ponytail: 'both' ยุบเป็น flood ในแถวรวม (report มี category เดียว) — source_ref
# ยังเก็บ alert_type จริงไว้ ('both') ให้ dashboard แยกได้ถ้าต้องการ
_BROADCAST_CATEGORY_VALUE = {"flood": "น้ำท่วม/น้ำขัง", "heat": "อากาศร้อน", "both": "น้ำท่วม/น้ำขัง"}


async def decline(event, line_bot_api, db: AsyncSession, alert_type: str):
    """user กด "ไม่" → เก็บแถวเบาๆ (status='cancelled', จบทันที) + ขอบคุณ.

    # ponytail: บ้านจริงของ "ปฏิเสธ" คือ outreach.response='declined' (ยังไม่ wire) —
    # ระหว่างนี้เก็บเป็นแถว reports status='cancelled' is_complete=False คงพฤติกรรมเดิม
    # (แถว confirmed=0 เดิม) ให้นับ response rate ได้
    """
    user_id = event.source.user_id
    db.add(Report(
        lineuser_id=user_id or None,
        community_id=await report_service.community_id_for(db, user_id),
        source="broadcast", source_ref=alert_type,
        category_id=await report_service.category_id_for(db, _BROADCAST_CATEGORY_VALUE.get(alert_type)),
        status="cancelled", is_complete=False,
    ))
    await db.commit()
    await reply_text(line_bot_api, event.reply_token, DECLINE)
