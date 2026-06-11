import asyncio
from types import SimpleNamespace

import app.utils.storage as storage
import app.handlers.chatbot_handler as ch


# --- storage helper ----------------------------------------------------------

def test_save_image_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    key = storage.save_image("survey/abc123.jpg", b"fake-bytes")
    assert key == "survey/abc123.jpg"
    found = storage.local_file(key)
    assert found is not None
    assert found.read_bytes() == b"fake-bytes"


def test_local_file_none_for_missing_or_empty_key(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    assert storage.local_file("survey/nope.jpg") is None
    assert storage.local_file(None) is None
    assert storage.local_file("") is None


def test_local_file_resolves_legacy_bare_filename(tmp_path, monkeypatch):
    # แถวเก่าของ form_reports เก็บชื่อไฟล์เปล่า ๆ (ไม่มี prefix) ใต้ uploads/ ตรง ๆ
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    (tmp_path / "legacy.jpg").write_bytes(b"old")
    assert storage.local_file("legacy.jpg") is not None


# --- survey image answer carries storage_key ---------------------------------

def _image_event():
    return SimpleNamespace(
        reply_token="rt",
        source=SimpleNamespace(user_id="U1"),
        message=SimpleNamespace(id="MSG123"),
    )


def _run_image_handler(monkeypatch, persist_result):
    async def fake_persist(image_id):
        return persist_result

    captured = {}

    async def fake_process(user_id, answer_data, reply_token, line_bot_api, db):
        captured["answer"] = answer_data

    monkeypatch.setattr(ch, "_persist_line_image", fake_persist)
    monkeypatch.setattr(ch, "process_survey_answer", fake_process)
    asyncio.run(ch.handle_chatbot_image(_image_event(), None, None))
    return captured["answer"]


def test_image_answer_includes_storage_key_when_persisted(monkeypatch):
    answer = _run_image_handler(monkeypatch, "survey/MSG123.jpg")
    assert answer == {"image_id": "MSG123", "storage_key": "survey/MSG123.jpg"}


def test_image_answer_degrades_to_image_id_when_persist_fails(monkeypatch):
    # เก็บรูปพลาดต้องไม่พัง flow — เหลือ image_id ให้ proxy สดได้
    answer = _run_image_handler(monkeypatch, None)
    assert answer == {"image_id": "MSG123"}
