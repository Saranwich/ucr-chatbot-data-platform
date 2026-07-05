"""LINE message building + reply helpers, reusable across handlers.

Broadcast keeps its own builders in handlers/broadcast_flow_handler.py (Pim's).
"""
from linebot.v3.messaging import (
    ReplyMessageRequest, TextMessage,
    FlexMessage, FlexBubble, FlexBox, FlexText, FlexSeparator,
)


async def reply_text(line_bot_api, reply_token, text: str):
    """Reply with a single text message."""
    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
    )


async def reply_messages(line_bot_api, reply_token, messages: list):
    """Reply with a prebuilt list of messages."""
    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=reply_token, messages=messages)
    )


def _manual_step(num: str, title: str, desc: str) -> FlexBox:
    return FlexBox(
        layout="horizontal",
        spacing="md",
        contents=[
            FlexBox(
                layout="vertical",
                width="28px",
                height="28px",
                background_color="#1E88E5",
                corner_radius="14px",
                contents=[
                    FlexText(text=num, color="#ffffff", align="center", gravity="center",
                             weight="bold", size="sm"),
                ],
            ),
            FlexBox(
                layout="vertical",
                flex=1,
                contents=[
                    FlexText(text=title, weight="bold", size="sm", wrap=True),
                    FlexText(text=desc, size="xs", color="#888888", wrap=True),
                ],
            ),
        ],
    )


def build_manual_messages() -> list:
    """The 'คู่มือการใช้งาน' reply: intro text + a 4-step Flex card."""
    bubble = FlexBubble(
        header=FlexBox(
            layout="vertical",
            background_color="#1E88E5",
            padding_all="16px",
            contents=[FlexText(text="📖 วิธีใช้งาน", color="#ffffff", weight="bold", size="lg")],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="md",
            padding_all="16px",
            contents=[
                _manual_step("1", 'กดเมนู "สำรวจ"', "แตะช่องใหญ่ด้านบน เพื่อเริ่มตอบคำถามเกี่ยวกับพื้นที่บ้านคุณ"),
                FlexSeparator(),
                _manual_step("2", "แตะปุ่มคำตอบได้เลย", 'ไม่ต้องพิมพ์ แค่แตะปุ่มที่ตรงกับคำตอบ ถ้าไม่มีตัวเลือก กด "ยกเลิก" ได้'),
                FlexSeparator(),
                _manual_step("3", 'เจอปัญหา กด "แจ้งปัญหา"', "เลือกหัวข้อ แล้วกรอกรูปหรือรายละเอียด เจ้าหน้าที่จะรับไปดำเนินการ"),
                FlexSeparator(),
                _manual_step("4", "แก้ไขข้อมูลส่วนตัว", "อัปเดตที่อยู่หรือข้อมูลของคุณได้ที่นี่ตลอดเวลา"),
            ],
        ),
    )
    return [
        TextMessage(text="นี่คือวิธีใช้งานง่ายๆ ครับ 📖\nทำตาม 4 ขั้นตอนนี้ได้เลย"),
        FlexMessage(alt_text="วิธีใช้งาน", contents=bubble),
    ]
