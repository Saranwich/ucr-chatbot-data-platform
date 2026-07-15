"""Forecast service — ไปหยิบ forecast รายวันจาก S3 ของทีม data (ข้อ ① ของ flow broadcast)

หน้าที่เดียว: GET forecast/<YYYY-MM-DD>.json → คืน JSON ดิบทั้งก้อนให้ caller
ไม่กรอง ไม่แยกประเภท heat/flood (นั่นเป็นงานของ broadcast handler)

สัญญากับ caller:
- ไฟล์ของวันนั้นไม่มี (404) → คืน None (วันนั้นไม่มีอะไรต้องแจ้ง — caller ตัดสินใจเอง)
- พังอย่างอื่น (เน็ตล่ม / timeout / JSON เพี้ยน) → raise ForecastUnavailable ชัดๆ ห้ามเงียบ

ข้อมูลถูก Lambda ของทีม data อัพเดททุกตี 1 (เวลาไทย)
โครง JSON: {"date": "YYYY-MM-DD", "WeatherForecasts": [{location, forecasts[]}]}
"""
import asyncio
import datetime as dt

import aiohttp

from app.config import FORECAST_BASE_URL

# วันของไฟล์อิงเวลาไทยเสมอ — บน Lambda นาฬิกาเครื่องเป็น UTC ถ้าใช้ date ตรงๆ
# ช่วงก่อน 7 โมงเช้าไทยจะได้ไฟล์ของ "เมื่อวาน" (ผิดวัน)
_BANGKOK = dt.timezone(dt.timedelta(hours=7))

_TIMEOUT = aiohttp.ClientTimeout(total=10)


class ForecastUnavailable(Exception):
    """ดึง forecast ไม่สำเร็จ (คนละกรณีกับ 'วันนั้นไม่มีไฟล์' ซึ่งคืน None)"""


def _date_str(date) -> str:
    """แปลง date ที่รับมา (None/str/date) เป็น 'YYYY-MM-DD' — None = วันนี้ตามเวลาไทย"""
    if date is None:
        return dt.datetime.now(_BANGKOK).date().isoformat()
    if isinstance(date, str):
        return date
    return date.isoformat()


async def get_daily(date=None) -> dict | None:
    """ดึง forecast ของวันที่กำหนด (ไม่ใส่ = วันนี้) คืน dict ทั้งก้อน หรือ None ถ้าไม่มีไฟล์"""
    url = f"{FORECAST_BASE_URL.rstrip('/')}/{_date_str(date)}.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=_TIMEOUT) as resp:
                # S3 ที่ไม่เปิดสิทธิ์ list ตอบ 403 (AccessDenied) สำหรับ key ที่ไม่มีจริง
                # แทนที่จะเป็น 404 (เจอจากการยิง bucket จริง) → ทั้งคู่ = วันนั้นไม่มีไฟล์
                if resp.status in (404, 403):
                    return None
                resp.raise_for_status()
                # content_type=None: S3 อาจ serve เป็น binary/octet-stream — parse ตามเนื้อจริง
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        raise ForecastUnavailable(f"ดึง forecast จาก {url} ไม่สำเร็จ: {e}") from e
