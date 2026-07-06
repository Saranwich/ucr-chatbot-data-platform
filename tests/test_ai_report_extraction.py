"""build_question routes a record_complaint tool call → report.save (source='ai').

No live DB/Redis: session + conversation anchor + report.save are stubbed; we assert
the AI core hands report.save the tool args plus the producer-set fields.
"""
import asyncio

import app.services.ai_tool as ai_tool
from app.services import report
from app.services.lookups import CATEGORIES


class FakeSession:
    """In-memory stand-in for the Redis transcript store (no live Redis)."""
    def __init__(self):
        self.msgs = []

    async def append(self, user_id, role, content):
        self.msgs.append({"role": role, "content": content})

    async def load(self, user_id):
        return list(self.msgs)

    async def dump_transcript(self, user_id):
        return f"conversations/{user_id}.json"


def test_record_complaint_calls_report_save(monkeypatch):
    monkeypatch.setattr(ai_tool, "session", FakeSession())
    # conversation anchor — stub the DB seam (returns a fixed id; archive attach noop)
    async def fake_ensure(user_id, trigger="user_initiated"):
        return 5
    async def fake_attach(conversation_id, archive_key):
        pass
    monkeypatch.setattr(ai_tool.conversation, "ensure_active", fake_ensure)
    monkeypatch.setattr(ai_tool.conversation, "attach_archive", fake_attach)

    saved = []
    async def fake_save(lineuser_id, rep):
        saved.append((lineuser_id, rep))
    monkeypatch.setattr(report, "save", fake_save)

    sample = {
        "category": "ไฟฟ้าสาธารณะ",
        "notes": "ไฟถนนดับหน้าปากซอย มืดมากเดินไม่เห็นทาง",
        "severity": "high",
        "title": "ไฟถนนดับหน้าปากซอย",
        "location": "หน้าปากซอย 5",
    }

    async def fake_chat(messages, system=None, tools=None, tool_handler=None):
        # จำลอง Gemini เรียก record_complaint (tool_handler เป็น async แล้ว) แล้วตอบกลับ
        await tool_handler("record_complaint", sample)
        return "ขอบคุณค่ะ เมืองจดเรื่องนี้ไว้ให้แล้ว"

    monkeypatch.setattr(ai_tool.llm, "chat", fake_chat)

    reply = asyncio.run(ai_tool.build_question("U1", "ไฟถนนหน้าบ้านดับ"))
    assert reply == "ขอบคุณค่ะ เมืองจดเรื่องนี้ไว้ให้แล้ว"

    assert len(saved) == 1
    uid, rep = saved[0]
    assert uid == "U1"

    # ค่าที่มาจาก tool
    assert rep["category"] in CATEGORIES
    assert rep["category"] == "ไฟฟ้าสาธารณะ"
    assert rep["notes"] == sample["notes"]
    assert rep["severity"] == "high"
    assert rep["title"] == "ไฟถนนดับหน้าปากซอย"
    assert rep["location"] == "หน้าปากซอย 5"

    # field ที่ record() hook เติมเอง
    assert rep["source"] == "ai"
    assert rep["status"] == "completed"
    assert rep["is_complete"] is True
    # FK ไปยัง conversation anchor ที่เปิดตอนบันทึกเรื่องแรก
    assert rep["conversation_id"] == 5
