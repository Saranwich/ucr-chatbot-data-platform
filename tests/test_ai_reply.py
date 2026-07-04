import asyncio
from types import SimpleNamespace

import app.services.ai_tool as ai_tool
from app.handlers.message_handler import handle_text_message


class FakeApi:
    def __init__(self):
        self.sent = None

    async def reply_message(self, req):
        self.sent = req.messages


def _text_event(text):
    return SimpleNamespace(reply_token="rt", message=SimpleNamespace(text=text))


def test_free_text_gets_ai_reply(monkeypatch):
    # ข้อความทั่วไป → AI core; mock LLM ให้เทสต์ไม่ยิง network จริง
    async def fake_llm(messages):
        return "โมเดลตอบกลับ"

    monkeypatch.setattr(ai_tool, "get_response", fake_llm)

    api = FakeApi()
    asyncio.run(handle_text_message(_text_event("สวัสดีจ้า"), api, db=None))
    assert api.sent[0].text == "โมเดลตอบกลับ"
