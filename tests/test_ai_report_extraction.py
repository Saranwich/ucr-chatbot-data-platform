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
        self.mode = None
        self.mode_cleared = False
        self.pending_images = []
        self.pending_location = None

    async def append(self, user_id, role, content):
        self.msgs.append({"role": role, "content": content})

    async def load(self, user_id):
        return list(self.msgs)

    async def dump_transcript(self, user_id):
        return f"conversations/{user_id}.json"

    async def clear_broadcast_mode(self, user_id):
        self.mode = None
        self.mode_cleared = True

    async def pop_pending_images(self, user_id):
        keys, self.pending_images = self.pending_images, []
        return keys

    async def pop_pending_location(self, user_id):
        loc, self.pending_location = self.pending_location, None
        return loc


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


def test_broadcast_reply_records_source_broadcast(monkeypatch):
    """คุยต่อจาก weather alert → report ลง source='broadcast' + เคลียร์ mode เมื่อบันทึกเสร็จ"""
    fake_session = FakeSession()
    monkeypatch.setattr(ai_tool, "session", fake_session)

    triggers = []
    async def fake_ensure(user_id, trigger="user_initiated"):
        triggers.append(trigger)
        return 7
    async def fake_attach(conversation_id, archive_key):
        pass
    monkeypatch.setattr(ai_tool.conversation, "ensure_active", fake_ensure)
    monkeypatch.setattr(ai_tool.conversation, "attach_archive", fake_attach)

    saved = []
    async def fake_save(lineuser_id, rep):
        saved.append((lineuser_id, rep))
    monkeypatch.setattr(report, "save", fake_save)

    systems = []
    async def fake_chat(messages, system=None, tools=None, tool_handler=None):
        systems.append(system)
        await tool_handler("record_complaint", {
            "category": "น้ำท่วม/น้ำขัง", "notes": "น้ำขังหน้าปากซอย เดินลำบาก",
        })
        return "ขอบคุณค่ะ เมืองจดไว้ให้แล้ว"
    monkeypatch.setattr(ai_tool.llm, "chat", fake_chat)

    reply = asyncio.run(ai_tool.build_broadcast_reply("U2", "มีน้ำท่วมขัง", "flood"))
    assert reply == "ขอบคุณค่ะ เมืองจดไว้ให้แล้ว"

    _, rep = saved[0]
    assert rep["source"] == "broadcast"
    assert rep["source_ref"] == "flood"
    assert rep["conversation_id"] == 7
    assert triggers == ["broadcast"]                    # conversation anchor รู้ที่มา
    assert "เมืองเพิ่งส่งแจ้งเตือนสภาพอากาศ" in systems[0]  # ใช้ prompt broadcast ไม่ใช่ตัวปกติ
    assert fake_session.mode_cleared                    # บันทึกแล้ว → กลับโหมดแชทปกติ


def test_pending_attachments_land_on_report(monkeypatch):
    """รูป/พิกัดที่ส่งระหว่างคุย → pop จาก session มาแนบกับ report ที่บันทึก (ครั้งเดียว)"""
    fake_session = FakeSession()
    fake_session.pending_images = ["reports/img1.jpg", "reports/img2.jpg"]
    fake_session.pending_location = (13.87, 100.57)
    monkeypatch.setattr(ai_tool, "session", fake_session)

    async def fake_ensure(user_id, trigger="user_initiated"):
        return 9
    async def fake_attach(conversation_id, archive_key):
        pass
    monkeypatch.setattr(ai_tool.conversation, "ensure_active", fake_ensure)
    monkeypatch.setattr(ai_tool.conversation, "attach_archive", fake_attach)

    saved = []
    async def fake_save(lineuser_id, rep):
        saved.append(rep)
    monkeypatch.setattr(report, "save", fake_save)

    async def fake_chat(messages, system=None, tools=None, tool_handler=None):
        await tool_handler("record_complaint", {
            "category": "ไฟฟ้าสาธารณะ", "notes": "ไฟถนนดับ",
        })
        return "ขอบคุณค่ะ"
    monkeypatch.setattr(ai_tool.llm, "chat", fake_chat)

    asyncio.run(ai_tool.build_question("U3", "[ระบบ: ผู้ใช้ส่งรูปภาพประกอบ 1 รูป]"))

    rep = saved[0]
    assert rep["image_keys"] == ["reports/img1.jpg", "reports/img2.jpg"]
    assert (rep["lat"], rep["lon"]) == (13.87, 100.57)
    # pop เคลียร์ของฝากแล้ว — บันทึกเรื่องถัดไปต้องไม่ติดรูป/พิกัดชุดเดิม
    assert fake_session.pending_images == []
    assert fake_session.pending_location is None


def test_severity_enum_reconciled_to_medium():
    """severity enum ตรงกับ DBML (low/medium/high) — กัน drift 'med' กลับมา + ยังสั่งให้ AI ประเมินเอง"""
    desc = ai_tool.RECORD_COMPLAINT["parameters"]["properties"]["severity"]["description"]
    assert "low, medium, high" in desc          # reconciled กับ reports.severity CHECK
    assert "med, high" not in desc              # เดิม drift เป็น 'low, med, high'
    assert "ประเมิน" in desc                     # AI ประเมินเอง ไม่ได้ให้ผู้ใช้บอกระดับ
