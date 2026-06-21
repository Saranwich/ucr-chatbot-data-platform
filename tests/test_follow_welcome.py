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


def _run_follow(monkeypatch, profiled: bool, liff_id):
    async def fake_get_or_create_user(db, user_id):
        return SimpleNamespace(lineuser_id=user_id, has_completed_profile=1 if profiled else 0)

    monkeypatch.setattr(fh, "get_or_create_user", fake_get_or_create_user)
    import app.services.profile_messages as pm
    monkeypatch.setattr(pm, "EDIT_PROFILE_ID", liff_id)

    api = FakeApi()
    asyncio.run(fh.handle_follow(_event(), api, FakeDb()))
    return api.sent


def test_new_user_gets_welcome_plus_profile_invite(monkeypatch):
    sent = _run_follow(monkeypatch, profiled=False, liff_id="1234-abcd")
    assert len(sent) == 2  # ทักทาย + Flex ชวนกรอก


def test_profiled_user_gets_welcome_back_only(monkeypatch):
    sent = _run_follow(monkeypatch, profiled=True, liff_id="1234-abcd")
    assert len(sent) == 1
    assert "ต้อนรับกลับ" in sent[0].text


def test_new_user_without_liff_id_still_gets_welcome(monkeypatch):
    # dev: EDIT_PROFILE_ID ยังไม่ตั้ง — ต้องไม่พังและยังทักทายได้
    sent = _run_follow(monkeypatch, profiled=False, liff_id=None)
    assert len(sent) == 1
