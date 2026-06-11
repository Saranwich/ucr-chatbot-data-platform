"""Flex message ชวนผู้ใช้ไปกรอกข้อมูลส่วนตัวใน Userdata LIFF.

ใช้ซ้ำสองที่: ข้อความขอบคุณท้าย survey (เมื่อยังไม่มี profile) และ
welcome message ตอน add เพื่อน — ปุ่มเปิด LIFF ตัวเดียวกัน
"""
from typing import Optional

from linebot.v3.messaging import (
    FlexMessage,
    FlexBubble,
    FlexBox,
    FlexText,
    FlexButton,
    URIAction,
)

from app.config import LIFF_USERDATA_ID


def build_profile_invite() -> Optional[FlexMessage]:
    """Flex bubble พร้อมปุ่มเปิดหน้าแก้ไขข้อมูลส่วนตัว

    คืน None เมื่อยังไม่ได้ตั้ง LIFF_USERDATA_ID (dev) — ผู้เรียกข้ามการแนบได้เลย
    """
    if not LIFF_USERDATA_ID:
        return None

    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            spacing="md",
            padding_all="16px",
            contents=[
                FlexText(text="📋 ข้อมูลส่วนตัว", weight="bold", size="lg"),
                FlexText(
                    text="ช่วยกรอกข้อมูลสั้น ๆ (ชื่อเล่น ช่วงอายุ เพศ ชุมชน) เพื่อให้ข้อมูลที่คุณรายงานถูกนำไปวิเคราะห์พัฒนาชุมชนได้ตรงจุดขึ้นครับ",
                    size="sm",
                    color="#555555",
                    wrap=True,
                ),
            ],
        ),
        footer=FlexBox(
            layout="vertical",
            padding_all="12px",
            contents=[
                FlexButton(
                    style="primary",
                    color="#1E88E5",
                    action=URIAction(
                        label="กรอกข้อมูลส่วนตัว",
                        uri=f"https://liff.line.me/{LIFF_USERDATA_ID}",
                    ),
                )
            ],
        ),
    )
    return FlexMessage(alt_text="กรอกข้อมูลส่วนตัว", contents=bubble)
