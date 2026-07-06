import asyncio
import json

import app.services.ai_tool as ai_tool
from app.services import report, session
from app.services.lookups import CATEGORIES
from app.utils import storage


def test_save_read_blob_roundtrip(tmp_path, monkeypatch):
    # เขียน/อ่าน blob ผ่าน storage seam โดยชี้ UPLOAD_DIR ไป tmp (ไม่แตะ uploads/ จริง)
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    key = storage.save_blob("conversations/abc.json", b'{"x": 1}')
    assert key == "conversations/abc.json"
    assert storage.read_blob("conversations/abc.json") == b'{"x": 1}'
    assert storage.read_blob("missing/none.json") is None


def test_recording_dumps_full_transcript(tmp_path, monkeypatch):
    # transcript ในหน่วยความจำแทน Redis + seed บทสนทนาก่อนหน้า
    store = [
        {"role": "user", "content": "สวัสดี"},
        {"role": "model", "content": "สวัสดีค่ะ มีเรื่องอะไรอยากเล่าไหมคะ"},
    ]

    async def fake_append(user_id, role, content):
        store.append({"role": role, "content": content})

    async def fake_load(user_id):
        return list(store)

    monkeypatch.setattr(session, "append", fake_append)
    monkeypatch.setattr(session, "load", fake_load)
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)  # blob ลง tmp ไม่แตะ uploads/ จริง

    async def fake_save(*a, **k):  # ไม่เขียน reports จริง (async seam)
        pass
    monkeypatch.setattr(report, "save", fake_save)

    # conversation anchor — stub the DB seam
    async def fake_ensure(user_id, trigger="user_initiated"):
        return 1
    async def fake_attach(conversation_id, archive_key):
        pass
    monkeypatch.setattr(ai_tool.conversation, "ensure_active", fake_ensure)
    monkeypatch.setattr(ai_tool.conversation, "attach_archive", fake_attach)

    async def fake_chat(messages, system=None, tools=None, tool_handler=None):
        # จำลอง Gemini เรียก record_complaint (tool_handler เป็น async) แล้วตอบกลับ
        await tool_handler("record_complaint", {"category": CATEGORIES[0], "notes": "ไฟถนนดับ"})
        return "ขอบคุณค่ะ เมืองจดไว้ให้แล้ว"

    monkeypatch.setattr(ai_tool.llm, "chat", fake_chat)

    asyncio.run(ai_tool.build_question("U1", "ไฟถนนหน้าบ้านดับ"))

    path = tmp_path / "conversations" / "U1.json"
    assert path.exists()
    dumped = json.loads(path.read_text(encoding="utf-8"))
    # dump เกิดตอนบันทึก (ก่อน append ข้อความตอบของ turn นี้) → transcript ครบถึงจุดนั้น
    assert dumped == [
        {"role": "user", "content": "สวัสดี"},
        {"role": "model", "content": "สวัสดีค่ะ มีเรื่องอะไรอยากเล่าไหมคะ"},
        {"role": "user", "content": "ไฟถนนหน้าบ้านดับ"},
    ]
