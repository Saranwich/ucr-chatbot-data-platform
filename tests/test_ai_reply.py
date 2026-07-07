import asyncio
from types import SimpleNamespace

import app.services.ai_tool as ai_tool
import app.handlers.message_handler as message_handler
from app.handlers.message_handler import handle_text_message


class FakeApi:
    def __init__(self):
        self.sent = None

    async def reply_message(self, req):
        self.sent = req.messages


class FakeSession:
    """In-memory stand-in for the Redis transcript store."""
    def __init__(self):
        self.msgs = []

    async def append(self, user_id, role, content):
        self.msgs.append({"role": role, "content": content})

    async def load(self, user_id):
        return list(self.msgs)


def _text_event(text):
    return SimpleNamespace(
        reply_token="rt", source=SimpleNamespace(user_id="U1"),
        message=SimpleNamespace(text=text),
    )


def test_free_text_gets_ai_reply(monkeypatch):
    # ข้อความทั่วไป → AI core; mock LLM + session ให้เทสต์ไม่แตะ network/Redis จริง
    captured = {}
    fake_session = FakeSession()

    async def fake_chat(messages, system=None, tools=None, tool_handler=None):
        captured["messages"] = messages
        captured["system"] = system
        captured["tools"] = tools
        return "โมเดลตอบกลับ"

    monkeypatch.setattr(ai_tool.llm, "chat", fake_chat)
    monkeypatch.setattr(ai_tool, "session", fake_session)

    # _ai_reply เช็คโหมด broadcast ผ่านโมดูล session จริงของ message_handler —
    # ต้อง patch ด้วย ไม่งั้นเทสต์วิ่งชน Redis จริง (แดงบนเครื่องที่ไม่มี Redis)
    async def fake_mode(user_id):
        return None
    monkeypatch.setattr(message_handler.session, "get_broadcast_mode", fake_mode)

    api = FakeApi()
    asyncio.run(handle_text_message(_text_event("ถนนหน้าบ้านมืดมาก"), api, db=None))

    assert api.sent[0].text == "โมเดลตอบกลับ"
    # โมเดลได้ transcript ที่มีข้อความผู้ใช้ + persona prompt + record_complaint tool
    assert captured["messages"][-1] == {"role": "user", "content": "ถนนหน้าบ้านมืดมาก"}
    assert captured["system"] is ai_tool.NONG_MUEANG_SYSTEM_PROMPT
    assert captured["tools"] == [ai_tool.RECORD_COMPLAINT]
    # ทั้งฝั่ง user และ model ถูกเก็บลง session
    assert [m["role"] for m in fake_session.msgs] == ["user", "model"]
