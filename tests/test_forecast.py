"""services/forecast.py — สัญญากับ caller: dict เมื่อสำเร็จ / None เมื่อ 404 / raise เมื่อพังอย่างอื่น

mock aiohttp ทั้งก้อน (FakeSession/FakeResponse) — test วิ่งได้โดยไม่แตะเน็ตจริง
"""
import datetime as dt

import aiohttp
import pytest

from app.services import forecast
from app.services.forecast import ForecastUnavailable, get_daily, _date_str

SAMPLE = {"date": "2026-06-14", "WeatherForecasts": [{"location": {"province": "นครพนม"}}]}


# ── ตัวปลอมแทน aiohttp: จำ URL ที่ถูกเรียก + ตอบตามบทที่กำหนด ──

class FakeResponse:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status = status
        self._payload = payload
        self._bad_json = bad_json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientError(f"HTTP {self.status}")

    async def json(self, content_type=None):
        if self._bad_json:
            raise ValueError("not valid json")
        return self._payload


class FakeSession:
    """แทน aiohttp.ClientSession — คืน response ตามบท + จด URL ล่าสุดไว้ให้ assert"""
    last_url = None

    def __init__(self, response=None, connect_error=False):
        self._response = response
        self._connect_error = connect_error

    def __call__(self):          # โค้ดจริงเรียก aiohttp.ClientSession() — ให้ instance นี้ทำตัวเป็น factory
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, timeout=None):
        FakeSession.last_url = url
        if self._connect_error:
            raise aiohttp.ClientError("connection refused")
        return self._response


def _use(monkeypatch, session: FakeSession):
    monkeypatch.setattr(forecast.aiohttp, "ClientSession", session)


# ── เคสปกติ ──

@pytest.mark.asyncio
async def test_get_daily_returns_parsed_json(monkeypatch):
    _use(monkeypatch, FakeSession(FakeResponse(status=200, payload=SAMPLE)))
    data = await get_daily("2026-06-14")
    assert data == SAMPLE
    assert FakeSession.last_url.endswith("/forecast/2026-06-14.json")


@pytest.mark.asyncio
async def test_get_daily_accepts_date_object(monkeypatch):
    _use(monkeypatch, FakeSession(FakeResponse(status=200, payload=SAMPLE)))
    await get_daily(dt.date(2026, 6, 14))
    assert FakeSession.last_url.endswith("/forecast/2026-06-14.json")


# ── วันนั้นไม่มีไฟล์ → None (ไม่ใช่ error) ──
# S3 ที่ปิดสิทธิ์ list ตอบ 403 แทน 404 สำหรับ key ที่ไม่มี (เจอจาก bucket จริง)

@pytest.mark.asyncio
async def test_get_daily_returns_none_on_404(monkeypatch):
    _use(monkeypatch, FakeSession(FakeResponse(status=404)))
    assert await get_daily("2026-01-01") is None


@pytest.mark.asyncio
async def test_get_daily_returns_none_on_403_missing_key(monkeypatch):
    _use(monkeypatch, FakeSession(FakeResponse(status=403)))
    assert await get_daily("2026-01-01") is None


# ── พังอย่างอื่น → ForecastUnavailable เสมอ (caller จับ type เดียวพอ) ──

@pytest.mark.asyncio
async def test_get_daily_raises_on_connection_error(monkeypatch):
    _use(monkeypatch, FakeSession(connect_error=True))
    with pytest.raises(ForecastUnavailable):
        await get_daily("2026-06-14")


@pytest.mark.asyncio
async def test_get_daily_raises_on_server_error(monkeypatch):
    _use(monkeypatch, FakeSession(FakeResponse(status=500)))
    with pytest.raises(ForecastUnavailable):
        await get_daily("2026-06-14")


@pytest.mark.asyncio
async def test_get_daily_raises_on_bad_json(monkeypatch):
    _use(monkeypatch, FakeSession(FakeResponse(status=200, bad_json=True)))
    with pytest.raises(ForecastUnavailable):
        await get_daily("2026-06-14")


# ── ไม่ใส่วันที่ = วันนี้ตามเวลาไทย (UTC+7) ไม่ใช่เวลาเครื่อง ──

def test_date_str_defaults_to_bangkok_today():
    bangkok_today = dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).date().isoformat()
    assert _date_str(None) == bangkok_today


def test_date_str_passes_string_through():
    assert _date_str("2026-06-14") == "2026-06-14"
