from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexBubble,
    FlexBox,
    FlexText,
    FlexSeparator,
)


def _step(num: str, title: str, desc: str) -> FlexBox:
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
                    FlexText(
                        text=num,
                        color="#ffffff",
                        align="center",
                        gravity="center",
                        weight="bold",
                        size="sm",
                    )
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


async def handle_manual_request(event, line_bot_api):
    """Handles the 'คู่มือการใช้งาน' request from the Rich Menu."""
    bubble = FlexBubble(
        header=FlexBox(
            layout="vertical",
            background_color="#1E88E5",
            padding_all="16px",
            contents=[
                FlexText(
                    text="📖 วิธีใช้งาน",
                    color="#ffffff",
                    weight="bold",
                    size="lg",
                )
            ],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="md",
            padding_all="16px",
            contents=[
                _step("1", 'กดเมนู "สำรวจ"', "แตะช่องใหญ่ด้านบน เพื่อเริ่มตอบคำถามเกี่ยวกับพื้นที่บ้านคุณ"),
                FlexSeparator(),
                _step("2", "แตะปุ่มคำตอบได้เลย", 'ไม่ต้องพิมพ์ แค่แตะปุ่มที่ตรงกับคำตอบ ถ้าไม่มีตัวเลือก กด "ยกเลิก" ได้'),
                FlexSeparator(),
                _step("3", 'เจอปัญหา กด "แจ้งปัญหา"', "เลือกหัวข้อ แล้วกรอกรูปหรือรายละเอียด เจ้าหน้าที่จะรับไปดำเนินการ"),
                FlexSeparator(),
                _step("4", "แก้ไขข้อมูลส่วนตัว", "อัปเดตที่อยู่หรือข้อมูลของคุณได้ที่นี่ตลอดเวลา"),
            ],
        ),
    )

    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[
                TextMessage(text="นี่คือวิธีใช้งานง่ายๆ ครับ 📖\nทำตาม 4 ขั้นตอนนี้ได้เลย"),
                FlexMessage(alt_text="วิธีใช้งาน", contents=bubble),
            ],
        )
    )
