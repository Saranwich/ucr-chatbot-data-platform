"""run_broadcast: กติกา "ห้ามยิงทับคนที่กำลังตอบ alert ค้าง" ต้องกันแม้ force=True (#106 ข้อ 1)

สถานะ "กำลังคุย" อยู่ใน Redis (broadcast_mode) — เทสนี้ stub ทุก seam รอบ
orchestrator แล้วยืนยันว่า user ที่ mode ติดอยู่ลง skipped_active และไม่ถูก push
"""
import asyncio

import app.services.weather as weather


class FakeDB:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_broadcast_mode_user_skipped_even_with_force(monkeypatch):
    async def fake_get_daily(date=None):
        return {"date": "2026-07-07", "WeatherForecasts": []}
    monkeypatch.setattr(weather.forecast, "get_daily", fake_get_daily)
    monkeypatch.setattr(weather.weather_broadcast, "parse_forecast", lambda d: [])
    monkeypatch.setattr(
        weather.weather_broadcast, "pick_strongest_per_location",
        lambda evs: [{"community": "ชุมชนคนรักถิ่น", "alert": "flood"}])
    monkeypatch.setattr(weather.weather_broadcast, "build_message", lambda alert: [])
    monkeypatch.setattr(weather.weather_broadcast, "to_sdk_messages", lambda msgs: msgs)

    monkeypatch.setattr(weather, "get_session", lambda: FakeDB())

    async def fake_cid(db, name):
        return 1
    monkeypatch.setattr(weather, "community_id_by_name", fake_cid)

    async def fake_users(db, name):
        return ["U_busy", "U_free"]
    monkeypatch.setattr(weather, "get_users_by_community", fake_users)

    # U_busy กำลังคุยตอบ alert อยู่ (Redis mode ติด) / U_free ว่าง
    async def fake_mode(uid):
        return "flood" if uid == "U_busy" else None
    monkeypatch.setattr(weather.session, "get_broadcast_mode", fake_mode)

    async def fake_recent(uid):
        return True                        # ทุกคนติด cap — force ต้องข้าม cap ได้ แต่ห้ามข้าม mode
    monkeypatch.setattr(weather, "recently_contacted", fake_recent)

    pushed = {}
    async def fake_push(uids, msgs):
        pushed["uids"] = uids
        return {"sent": uids, "failed": []}
    monkeypatch.setattr(weather.broadcast, "push_to_users", fake_push)

    logged = []
    async def fake_log(uid, alert, community_id=None, conversation_id=None):
        logged.append(uid)
    monkeypatch.setattr(weather, "log_outreach", fake_log)

    summary = asyncio.run(weather.run_broadcast(force=True))

    assert summary["skipped_active"] == ["U_busy"]   # mode ติด = ห้ามยิง แม้ force
    assert pushed["uids"] == ["U_free"]              # force ข้าม cap ให้คนว่างตามเดิม
    assert logged == ["U_free"]
    assert summary["communities"] == [
        {"community": "ชุมชนคนรักถิ่น", "alert": "flood", "users": 2, "sent": 1}]
