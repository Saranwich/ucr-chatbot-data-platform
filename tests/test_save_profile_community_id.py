"""user.save_profile must resolve community_id (FK), not just the legacy
varchar — regression test for #115 (migration gap: writer never populated
the FK it was added for).
"""
import asyncio
from types import SimpleNamespace

from app.services import user as user_service


class FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalars(self):
        return self

    def first(self):
        return self._obj


class FakeSession:
    """Stand-in DB session: captures the User row saved + fakes the
    communities.name -> community_id lookup with a fixed value."""
    def __init__(self, existing_user=None, community_id=None):
        self._existing_user = existing_user
        self._community_id = community_id
        self.added = []
        self.committed = False

    async def execute(self, stmt):
        return FakeResult(self._existing_user)

    async def scalar(self, stmt):
        return self._community_id

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    @property
    def saved_user(self):
        return self._existing_user or (self.added[0] if self.added else None)


def _profile(community):
    return SimpleNamespace(nickname="ต้น", age_range="26–35", gender="ชาย", community=community)


def test_save_profile_sets_community_id_for_new_user():
    fake = FakeSession(existing_user=None, community_id=3)

    asyncio.run(user_service.save_profile(fake, "U1", _profile("ชุมชนคนรักถิ่น")))

    row = fake.saved_user
    assert row.community == "ชุมชนคนรักถิ่น"
    assert row.community_id == 3
    assert fake.committed


def test_save_profile_leaves_community_id_null_for_unmatched_name(capsys):
    fake = FakeSession(existing_user=None, community_id=None)

    asyncio.run(user_service.save_profile(fake, "U1", _profile("ชื่อที่ไม่มีใน communities")))

    row = fake.saved_user
    assert row.community == "ชื่อที่ไม่มีใน communities"
    assert row.community_id is None
    assert fake.committed
    # ชื่อหลุด enum = dropdown drift จริง ต้องเตือน
    assert "not in communities table" in capsys.readouterr().out


def test_save_profile_accepts_no_community_without_warning(capsys):
    """#121: "ไม่เลือกชุมชน" เป็นคำตอบปกติ ไม่ใช่ drift — ห้าม query ห้ามเตือน

    fake ตั้งไว้ให้คืน 5 ถ้ามีการ lookup เกิดขึ้น: ถ้า guard หาย เทสต์นี้จะจับได้
    ทั้งจาก community_id ที่ไม่ควรมีค่า และจาก warning ปลอมที่ไม่ควรพิมพ์
    """
    fake = FakeSession(existing_user=None, community_id=5)

    asyncio.run(user_service.save_profile(fake, "U1", _profile(None)))

    row = fake.saved_user
    assert row.community is None
    assert row.community_id is None
    assert fake.committed
    assert "not in communities table" not in capsys.readouterr().out


def test_save_profile_updates_community_id_on_existing_user():
    existing = SimpleNamespace(
        lineuser_id="U1", community=None, community_id=None,
        nickname=None, age_range=None, gender=None, has_completed_profile=0,
    )
    fake = FakeSession(existing_user=existing, community_id=7)

    asyncio.run(user_service.save_profile(fake, "U1", _profile("ชุมชนหลักสี่พัฒนา 99")))

    assert existing.community_id == 7
    assert existing.has_completed_profile == 1
