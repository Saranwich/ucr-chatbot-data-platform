import asyncio
from types import SimpleNamespace

from app.handlers.message_handler import handle_text_message


class FakeApi:
    def __init__(self):
        self.sent = None

    async def reply_message(self, req):
        self.sent = req.messages


def _text_event(text):
    return SimpleNamespace(reply_token="rt", message=SimpleNamespace(text=text))


def test_free_text_gets_ai_reply():
    # ข้อความทั่วไป (ไม่ใช่ปุ่ม rich menu / broadcast) → AI core ตอบ
    api = FakeApi()
    asyncio.run(handle_text_message(_text_event("สวัสดีจ้า"), api, db=None))
    assert api.sent[0].text == "AI question here"
