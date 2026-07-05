"""services/broadcast.py — สัญญา: ยิงทีละคน, คนเดียวพลาดรอบไม่ล้ม, สรุป sent/failed ตรงจริง

mock LINE client ทั้งก้อน — test วิ่งได้โดยไม่ยิง LINE จริง (ไม่มีข้อความหลุดถึง user)
"""
import pytest
from linebot.v3.messaging import TextMessage

from app.services import broadcast
from app.services.broadcast import push_to_users

MESSAGES = [TextMessage(text="ทดสอบ broadcast")]


# ── ตัวปลอมแทน LINE SDK: จำว่าถูกสั่งยิงหาใคร + แกล้งพลาดตามบท ──

class FakeMessagingApi:
    def __init__(self, fail_for=()):
        self.pushed_to = []          # ยิงสำเร็จหาใครบ้าง (ตามลำดับ)
        self.requests = []           # PushMessageRequest ที่ถูกส่งจริง
        self._fail_for = set(fail_for)

    async def push_message(self, request):
        if request.to in self._fail_for:
            raise RuntimeError(f"user {request.to} blocked the bot")
        self.pushed_to.append(request.to)
        self.requests.append(request)


class FakeApiClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _use(monkeypatch, fake_api: FakeMessagingApi):
    monkeypatch.setattr(broadcast, "AsyncApiClient", FakeApiClient)
    monkeypatch.setattr(broadcast, "AsyncMessagingApi", lambda api_client: fake_api)


# ── เคสปกติ: ส่งครบทุกคน ทีละคน ด้วยข้อความชุดเดียวกัน ──

@pytest.mark.asyncio
async def test_pushes_to_every_user_one_by_one(monkeypatch):
    fake = FakeMessagingApi()
    _use(monkeypatch, fake)

    result = await push_to_users(["U1", "U2", "U3"], MESSAGES)

    assert result == {"sent": ["U1", "U2", "U3"], "failed": []}
    assert fake.pushed_to == ["U1", "U2", "U3"]          # ครบทุกคน ตามลำดับ
    assert all(r.messages == MESSAGES for r in fake.requests)  # ข้อความชุดเดียวกันทุกคน


# ── หัวใจของ service: user เดียวพลาด รอบต้องไม่ล้ม คนที่เหลือต้องได้รับ ──

@pytest.mark.asyncio
async def test_one_failure_does_not_stop_the_round(monkeypatch):
    fake = FakeMessagingApi(fail_for={"U2"})
    _use(monkeypatch, fake)

    result = await push_to_users(["U1", "U2", "U3"], MESSAGES)

    assert result == {"sent": ["U1", "U3"], "failed": ["U2"]}
    assert fake.pushed_to == ["U1", "U3"]                # U3 ยังได้รับแม้ U2 พัง


@pytest.mark.asyncio
async def test_all_failures_reported_not_raised(monkeypatch):
    fake = FakeMessagingApi(fail_for={"U1", "U2"})
    _use(monkeypatch, fake)

    result = await push_to_users(["U1", "U2"], MESSAGES)  # ต้องไม่ raise

    assert result == {"sent": [], "failed": ["U1", "U2"]}


# ── list ว่าง: จบเงียบๆ ไม่สร้าง client ไม่ยิงอะไร ──

@pytest.mark.asyncio
async def test_empty_user_list_sends_nothing(monkeypatch):
    fake = FakeMessagingApi()
    _use(monkeypatch, fake)

    result = await push_to_users([], MESSAGES)

    assert result == {"sent": [], "failed": []}
    assert fake.pushed_to == []
