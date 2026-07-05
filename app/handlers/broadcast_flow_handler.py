"""
broadcast_flow_handler.py — state machine เก็บข้อมูลหลัง user ตอบ broadcast แจ้งเตือน

user กดปุ่มยืนยัน (มีน้ำท่วมขัง / ร้อนมาก / ทั้งฝนทั้งร้อน) → เริ่มเก็บข้อมูลทีละสเต็ป:
    awaiting_note → awaiting_location → awaiting_photo → done
บอทดู BroadcastReport.status ของ report ที่ยัง active เพื่อรู้ว่า message ที่เข้ามาคืออะไร
(เพราะ LINE ยิงข้อความมาแยกกัน ไม่จำ context ให้ — status คือ "ความจำ" ของบอท)
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

from app.models import BroadcastReport, User
from app.config import CHANNEL_ACCESS_TOKEN
from app.utils import storage


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


async def get_active_report(db: AsyncSession, lineuser_id: str):
    """report ที่ user กำลังกรอกค้างอยู่ (status != done) — ตัวชี้ว่าเขาอยู่ใน flow"""
    result = await db.execute(
        select(BroadcastReport)
        .where(
            BroadcastReport.lineuser_id == lineuser_id,
            BroadcastReport.status != "done",
        )
        .order_by(BroadcastReport.report_id.desc())
    )
    return result.scalars().first()


async def start_report(event, line_bot_api, db: AsyncSession, alert_type: str):
    """user กด "ใช่" → สร้าง report (confirmed=1) + เริ่มถาม note"""
    user_id = event.source.user_id
    user = await db.get(User, user_id)
    db.add(BroadcastReport(
        lineuser_id=user_id, alert_type=alert_type, confirmed=1,
        community=user.community if user else None, status="awaiting_note",
    ))
    await db.commit()
    await _reply(line_bot_api, event.reply_token, _note_prompt(alert_type))


async def decline(event, line_bot_api, db: AsyncSession, alert_type: str):
    """user กด "ไม่" → เก็บแถวเบาๆ (confirmed=0, จบทันที) + ขอบคุณ"""
    user_id = event.source.user_id
    user = await db.get(User, user_id)
    db.add(BroadcastReport(
        lineuser_id=user_id, alert_type=alert_type, confirmed=0,
        community=user.community if user else None, status="done",
    ))
    await db.commit()
    await _reply(line_bot_api, event.reply_token, DECLINE)


async def continue_flow(event, line_bot_api, db: AsyncSession, report: BroadcastReport):
    """message เข้ามาระหว่าง report ยัง active → จัดการตาม report.status"""
    msg = event.message
    is_text = isinstance(msg, TextMessageContent)
    skipped = is_text and msg.text.strip() == SKIP

    # ── รอ note (พิมพ์เล่า/บ่น หรือ ข้าม) ──
    if report.status == "awaiting_note":
        if is_text:
            if not skipped:
                report.note = msg.text.strip()
            report.status = "awaiting_location"          # ทุก type เก็บ location + รูป เหมือนกัน
            await db.commit()
            await _reply(line_bot_api, event.reply_token, _location_prompt())
        else:
            await _reply(line_bot_api, event.reply_token, _note_prompt(report.alert_type))  # ยังไม่ถึงขั้นส่ง → ถามซ้ำ

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
            report.image_path = await _persist_image(msg.id)   # ดึง bytes จริง → storage key (None ถ้าพลาด)
            report.status = "done"
            await db.commit()
            await _reply(line_bot_api, event.reply_token, THANK_YOU)
        elif skipped:
            report.status = "done"
            await db.commit()
            await _reply(line_bot_api, event.reply_token, THANK_YOU)
        else:
            await _reply(line_bot_api, event.reply_token, _photo_prompt())
