"""make_mock_forecast.py — สร้างไฟล์ forecast ปลอมไว้เดโม่ ตอน S3 ทีม data มีปัญหา

สร้าง mock_forecast/forecast/<date>.json โครงเดียวกับไฟล์จริงเป๊ะ ครบ 14 ชุมชน
(alert หมุนเวียน flood/heat/both ให้การ์ดบนมือถือหลากหลาย) แล้วเสิร์ฟเองในเครื่อง:

    python scripts/make_mock_forecast.py              # วันนี้ + พรุ่งนี้ (เวลาไทย)
    python scripts/make_mock_forecast.py 2026-07-04   # ระบุวันเอง (กี่วันก็ได้)
    python scripts/make_mock_forecast.py --hour 19    # event ตกชั่วโมง 19:00 (ไว้เดโม่ scheduler)

    python -m http.server 9000 -d mock_forecast       # เทอร์มินัลแยก
    # .env → FORECAST_BASE_URL=http://localhost:9000/forecast  แล้ว restart uvicorn

pipeline ไม่รู้ด้วยซ้ำว่าเป็นของปลอม — เปลี่ยนกลับ = ลบ FORECAST_BASE_URL ออกจาก .env
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from app.services.lookups import COMMUNITIES

_BANGKOK = dt.timezone(dt.timedelta(hours=7))
OUT_DIR = root / "mock_forecast" / "forecast"

# ค่าที่เข้าเกณฑ์ classify_alert (heat: temp > 35 / flood: label ฝน) แบบชัวร์ๆ
_ALERT_WEATHER = {
    "flood": {"temperature": 31.5, "rainfall": 2.0, "condition_label": "มีฝน"},
    "heat":  {"temperature": 36.5, "rainfall": 0, "condition_label": "แจ่มใส"},
    "both":  {"temperature": 36.2, "rainfall": 1.5, "condition_label": "มีฝน"},
}
_ROTATION = ["flood", "heat", "both"]


def build_day(date: dt.date, alert_hour: int) -> dict:
    forecasts_by_community = []
    for i, name in enumerate(COMMUNITIES):
        alert = _ROTATION[i % len(_ROTATION)]
        peak = {"time": f"{date}T{alert_hour:02d}:00:00+07:00",
                "humidity": 70.0, "wind_speed": 3.0, "wind_direction": 200.0, "condition": 5,
                **_ALERT_WEATHER[alert]}
        calm = {"time": f"{date}T{(alert_hour + 1) % 24:02d}:00:00+07:00",
                "temperature": 30.0, "rainfall": 0, "condition_label": "มีเมฆบางส่วน",
                "humidity": 65.0, "wind_speed": 2.0, "wind_direction": 180.0, "condition": 2}
        forecasts_by_community.append({
            "name": name,
            "location": {"province": None, "district": None, "subdistrict": None,
                         "region": None, "geocode": None, "lat": 13.87, "lon": 100.57},
            "forecasts": [peak, calm],
        })
    return {"date": str(date), "WeatherForecasts": forecasts_by_community}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dates", nargs="*", help="YYYY-MM-DD (ไม่ใส่ = วันนี้+พรุ่งนี้)")
    parser.add_argument("--hour", type=int, default=13, help="ชั่วโมงที่ event เกิด (เวลาไทย)")
    args = parser.parse_args()

    if args.dates:
        dates = [dt.date.fromisoformat(d) for d in args.dates]
    else:
        today = dt.datetime.now(_BANGKOK).date()
        dates = [today, today + dt.timedelta(days=1)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for date in dates:
        path = OUT_DIR / f"{date}.json"
        path.write_text(json.dumps(build_day(date, args.hour), ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"✅ {path.relative_to(root)} — {len(COMMUNITIES)} ชุมชน, event {args.hour:02d}:00")


if __name__ == "__main__":
    main()
