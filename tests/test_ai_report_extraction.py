import asyncio
import csv

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
        pass


def test_record_complaint_writes_full_schema_row(tmp_path, monkeypatch):
    # เขียน CSV ลง tmp เพื่อไม่ไปแตะ reports.csv จริง
    path = tmp_path / "reports.csv"
    monkeypatch.setattr(report, "_CSV_PATH", str(path))
    monkeypatch.setattr(ai_tool, "session", FakeSession())

    sample = {
        "category": "ไฟฟ้าสาธารณะ",
        "notes": "ไฟถนนดับหน้าปากซอย มืดมากเดินไม่เห็นทาง",
        "severity": "high",
        "title": "ไฟถนนดับหน้าปากซอย",
        "location": "หน้าปากซอย 5",
    }

    async def fake_chat(messages, system=None, tools=None, tool_handler=None):
        # จำลอง Gemini เรียก record_complaint แล้วตอบกลับ
        tool_handler("record_complaint", sample)
        return "ขอบคุณค่ะ เมืองจดเรื่องนี้ไว้ให้แล้ว"

    monkeypatch.setattr(ai_tool.llm, "chat", fake_chat)

    reply = asyncio.run(ai_tool.build_question("U1", "ไฟถนนหน้าบ้านดับ"))
    assert reply == "ขอบคุณค่ะ เมืองจดเรื่องนี้ไว้ให้แล้ว"

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 1
    row = rows[0]

    # แถวมีครบทุกคอลัมน์ตาม schema reports
    assert set(row.keys()) == set(report._FIELDS)

    # ค่าที่มาจาก tool
    assert row["category"] in CATEGORIES
    assert row["category"] == "ไฟฟ้าสาธารณะ"
    assert row["notes"] == sample["notes"]
    assert row["severity"] == "high"
    assert row["title"] == "ไฟถนนดับหน้าปากซอย"
    assert row["location_text"] == "หน้าปากซอย 5"  # tool arg 'location' → คอลัมน์ location_text
    assert row["lineuser_id"] == "U1"
    assert row["created_at"]  # timestamp ไม่ว่าง

    # field ที่ record() hook เติมเอง
    assert row["source"] == "ai"
    assert row["status"] == "completed"
    assert row["is_complete"] == "True"

    # field ที่ไม่ได้ส่งมา = ว่าง ไม่ใช่หาย
    assert row["community_id"] == ""
    assert row["payload"] == ""
