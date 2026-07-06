"""
broadcast_flow_handler.py — state machine เก็บข้อมูลหลัง user ตอบ broadcast แจ้งเตือน

user กดปุ่มยืนยัน (มีน้ำท่วมขัง / ร้อนมาก / ทั้งฝนทั้งร้อน) → เริ่มเก็บข้อมูลทีละสเต็ป:
    awaiting_note → awaiting_location → awaiting_photo → completed
บอทดู reports.status (source='broadcast') ของ report ที่ยัง active เพื่อรู้ว่า message ที่เข้ามาคืออะไร
(เพราะ LINE ยิงข้อความมาแยกกัน ไม่จำ context ให้ — status คือ "ความจำ" ของบอท)
V2: ไม่มีตาราง broadcast_reports แล้ว — ทั้ง flow เขียน/อ่านแถวเดียวในตาราง reports กลาง
"""
from linebot.v3.messaging import (
    ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, MessageAction, LocationAction, CameraAction,
    Configuration, AsyncApiClient, AsyncMessagingApiBlob,
)
from linebot.v3.webhooks import TextMessageContent, LocationMessageContent, ImageMessageContent
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Report, ReportImage
from app.services import report as report_service
from app.config import CHANNEL_ACCESS_TOKEN
from app.utils import storage

# broadcast flow steps ที่ยังกรอกไม่จบ (report ที่ status อยู่ในนี้ = active อยู่)
_AWAITING = ("awaiting_note", "awaiting_location", "awaiting_photo")


# ── สัญญากับปุ่มใน broadcast (ต้องตรงกับ text ใน weather_broadcast._MESSAGE_CONFIG) ──
YES_MAP = {                              # ปุ่ม "ใช่" → alert_type
    "มีน้ำท่วมขัง": "flood",
    "ร้อนมาก": "heat",
    "ทั้งฝนทั้งร้อน": "both",
}
NO_MAP = {                               # ปุ่ม "ไม่" → alert_type (ไว้เก็บแถว confirmed=0)
    "ไม่ท่วม": "flood",
    "ไม่ร้อน": "heat",
    "ปกติดี": "both",
}
SKIP = "ข้าม"

THANK_YOU = "ขอบคุณมากๆ เลยนะคะ 🙏 ข้อมูลของคุณมีประโยชน์กับการดูแลชุมชนมากเลยค่ะ ☺️"
DECLINE = "ขอบคุณที่บอกนะคะ 🙏 ดูแลสุขภาพด้วยนะคะ 😊"


# ── ข้อความแต่ละสเต็ป (โทนสบายๆ + quick reply ส่ง/ข้าม) ──
# ตัวเลือกให้ "แตะเลือก" ได้ (กันคนพิมพ์ไม่สะดวก เช่น ผู้สูงอายุ) — ยังพิมพ์เองได้อยู่
# แตะปุ่ม = ส่ง text นั้นมาเป็น note (handler เก็บ text ใดๆ เป็น note อยู่แล้ว)
_NOTE_PRESETS = {
    "flood": ("น้ำท่วมแถวบ้านเป็นยังไงบ้างคะ เล่าให้ฟังหน่อยได้นะคะ 🙏",
              [("🌊 ท่วมเยอะ", "ท่วมเยอะ"), ("💧 ขังนิดหน่อย", "ขังนิดหน่อย"), ("🚶 เดินลำบาก", "เดินลำบาก")]),
    "heat":  ("อากาศร้อนกระทบยังไงบ้างคะ เล่าให้ฟังหน่อยได้นะคะ 🙏",
              [("🥵 ร้อนจนไม่สบาย", "ร้อนจนไม่สบาย"), ("😴 นอนไม่หลับ", "นอนไม่หลับ"), ("💸 ค่าไฟแพง", "ค่าไฟแพง")]),
    "both":  ("ทั้งฝนทั้งร้อนเป็นยังไงบ้างคะ เล่าให้ฟังหน่อยได้นะคะ 🙏",
              [("🌊 น้ำท่วม", "น้ำท่วม"), ("🥵 ร้อนมาก", "ร้อนมาก"), ("😣 ลำบากหลายอย่าง", "ลำบากหลายอย่าง")]),
}


def _note_prompt(alert_type: str) -> TextMessage:
    text, presets = _NOTE_PRESETS.get(alert_type, _NOTE_PRESETS["flood"])
    items = [QuickReplyItem(action=MessageAction(label=lbl, text=txt)) for lbl, txt in presets]
    items.append(QuickReplyItem(action=MessageAction(label="⏭️ ขอข้ามก่อน", text=SKIP)))
    return TextMessage(
        text=f"{text}\n(แตะเลือก หรือพิมพ์เล่าเองก็ได้ค่ะ)",
        quick_reply=QuickReply(items=items),
    )


def _location_prompt() -> TextMessage:
    return TextMessage(
        text="เข้าใจแล้วค่ะ 🙏 ถ้าสะดวก ขอตำแหน่งจุดที่เจอปัญหาหน่อยได้มั้ยคะ?",
        quick_reply=QuickReply(items=[
            QuickReplyItem(action=LocationAction(label="📍 ส่งพิกัด")),
            QuickReplyItem(action=MessageAction(label="⏭️ ขอข้ามก่อน", text=SKIP)),
        ]),
    )


def _photo_prompt() -> TextMessage:
    return TextMessage(
        text="ขอบคุณค่ะ 📷 ถ้ามีรูปประกอบ ส่งมาให้ดูหน่อยได้เลยค่ะ",
        quick_reply=QuickReply(items=[
            QuickReplyItem(action=CameraAction(label="📷 ส่งรูป")),
            QuickReplyItem(action=MessageAction(label="⏭️ ขอข้ามก่อน", text=SKIP)),
        ]),
    )


async def _reply(line_bot_api, token, message):
    if isinstance(message, str):
        message = TextMessage(text=message)
    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=token, messages=[message])
    )


async def _persist_image(image_id: str) -> str | None:
    """ดึง bytes รูปจาก LINE CDN มาเก็บถาวรทันที (CDN ลบรูปทิ้งหลังผ่านไปสักพัก)

    คืน storage key (เช่น 'broadcast/<id>.jpg') หรือ None ถ้าพลาด —
    การเก็บรูปต้องไม่ทำให้ flow พัง (note/location ที่ได้มาแล้วสำคัญกว่า)
    """
    try:
        configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
        async with AsyncApiClient(configuration) as api_client:
            blob_api = AsyncMessagingApiBlob(api_client)
            content = await blob_api.get_message_content(image_id)
        return storage.save_image(f"broadcast/{image_id}.jpg", content)
    except Exception as e:
        print(f"⚠️ persist broadcast image {image_id} failed: {e}")
        return None


# broadcast alert_type → หมวดหลักในตาราง categories
# ponytail: 'both' ยุบเป็น flood ในแถวรวม (report มี category เดียว) — source_ref
# ยังเก็บ alert_type จริงไว้ ('both') ให้ dashboard แยกได้ถ้าต้องการ
_BROADCAST_CATEGORY_VALUE = {"flood": "น้ำท่วม/น้ำขัง", "heat": "อากาศร้อน", "both": "น้ำท่วม/น้ำขัง"}


async def get_active_report(db: AsyncSession, lineuser_id: str):
    """report ที่ user กำลังกรอกค้างอยู่ (status อยู่ในสเต็ป awaiting_*) — อยู่ใน flow"""
    result = await db.execute(
        select(Report)
        .where(
            Report.lineuser_id == lineuser_id,
            Report.source == "broadcast",
            Report.status.in_(_AWAITING),
        )
        .order_by(Report.report_id.desc())
    )
    return result.scalars().first()


async def start_report(event, line_bot_api, db: AsyncSession, alert_type: str):
    """user กด "ใช่" → สร้างแถว reports (source='broadcast', ยังไม่ครบ) + เริ่มถาม note.

    แถวนี้ทำหน้าที่เป็น "ความจำ" ของ flow ด้วย (status = สเต็ปที่กรอกถึง) จนกรอกจบ
    ค่อย flip เป็น completed — ไม่มีตาราง broadcast_reports แล้ว (M4).
    """
    user_id = event.source.user_id
    db.add(Report(
        lineuser_id=user_id or None,
        community_id=await report_service.community_id_for(db, user_id),
        source="broadcast", source_ref=alert_type,
        category_id=await report_service.category_id_for(db, _BROADCAST_CATEGORY_VALUE.get(alert_type)),
        status="awaiting_note", is_complete=False,
    ))
    await db.commit()
    await _reply(line_bot_api, event.reply_token, _note_prompt(alert_type))


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
    await _reply(line_bot_api, event.reply_token, DECLINE)


async def _finish(db: AsyncSession, report: Report, image_key: str | None) -> None:
    """flow จบ → flip แถว reports เป็น completed + แนบรูป (ถ้ามี)."""
    report.status = "completed"
    report.is_complete = True
    await db.flush()
    if image_key:
        db.add(ReportImage(report_id=report.report_id, image_key=image_key))
    await db.commit()


async def continue_flow(event, line_bot_api, db: AsyncSession, report: Report):
    """message เข้ามาระหว่าง report ยัง active → จัดการตาม report.status"""
    msg = event.message
    is_text = isinstance(msg, TextMessageContent)
    skipped = is_text and msg.text.strip() == SKIP

    # ── รอ note (พิมพ์เล่า/บ่น หรือ ข้าม) ──
    if report.status == "awaiting_note":
        if is_text:
            if not skipped:
                report.notes = msg.text.strip()
            report.status = "awaiting_location"          # ทุก type เก็บ location + รูป เหมือนกัน
            await db.commit()
            await _reply(line_bot_api, event.reply_token, _location_prompt())
        else:
            await _reply(line_bot_api, event.reply_token, _note_prompt(report.source_ref))  # ยังไม่ถึงขั้นส่ง → ถามซ้ำ

    # ── รอ location (แชร์พิกัด หรือ ข้าม) ──
    elif report.status == "awaiting_location":
        if isinstance(msg, LocationMessageContent):
            report.location_data = WKTElement(f"POINT({msg.longitude} {msg.latitude})", srid=4326)
            report.status = "awaiting_photo"
            await db.commit()
            await _reply(line_bot_api, event.reply_token, _photo_prompt())
        elif skipped:
            report.status = "awaiting_photo"
            await db.commit()
            await _reply(line_bot_api, event.reply_token, _photo_prompt())
        else:
            await _reply(line_bot_api, event.reply_token, _location_prompt())

    # ── รอ photo (ส่งรูป หรือ ข้าม) → จบ ──
    elif report.status == "awaiting_photo":
        if isinstance(msg, ImageMessageContent):
            image_key = await _persist_image(msg.id)   # ดึง bytes จริง → storage key (None ถ้าพลาด)
            await _finish(db, report, image_key)        # flip แถว reports → completed + แนบรูป
            await _reply(line_bot_api, event.reply_token, THANK_YOU)
        elif skipped:
            await _finish(db, report, None)
            await _reply(line_bot_api, event.reply_token, THANK_YOU)
        else:
            await _reply(line_bot_api, event.reply_token, _photo_prompt())
