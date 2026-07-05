import asyncio
from types import SimpleNamespace

import app.handlers.follow_handler as fh


class FakeApi:
    def __init__(self):
        self.sent = None

    async def reply_message(self, req):
        self.sent = req.messages


class FakeDb:
    async def commit(self):
        pass


def _event():
    return SimpleNamespace(reply_token="rt", source=SimpleNamespace(user_id="U1"))


def _run_follow(monkeypatch, profiled: bool):
    async def fake_get_or_create_user(db, user_id):
        return SimpleNamespace(lineuser_id=user_id, has_completed_profile=1 if profiled else 0)

    monkeypatch.setattr(fh, "get_or_create_user", fake_get_or_create_user)

    api = FakeApi()
    asyncio.run(fh.handle_follow(_event(), api, FakeDb()))
    return api.sent


def test_new_user_gets_welcome(monkeypatch):
    # V2: ไม่ชวนกรอก profile แล้ว — คนใหม่ได้คำทักทายเดียว
    sent = _run_follow(monkeypatch, profiled=False)
    assert len(sent) == 1


def test_profiled_user_gets_welcome_back(monkeypatch):
    sent = _run_follow(monkeypatch, profiled=True)
    assert len(sent) == 1
    assert "ต้อนรับกลับ" in sent[0].text
