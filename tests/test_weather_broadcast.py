"""services/weather_broadcast.py — ตัดสิน alert + key ตามชุมชน + สัญญาปุ่มกับ reply flow

pure functions ทั้งไฟล์ — ไม่แตะ DB/เน็ต
"""
import datetime as dt

from linebot.v3.messaging import TextMessage, FlexMessage

from app.services.weather_broadcast import (
    classify_alert, parse_forecast, pick_strongest_per_location, filter_due,
    build_message, to_sdk_messages, _MESSAGE_CONFIG,
)
from app.handlers.broadcast_flow_handler import YES_MAP, NO_MAP

_BKK = dt.timezone(dt.timedelta(hours=7))

# ตัวอย่างย่อจากไฟล์ forecast จริง (โครงเดียวกับ S3 ของทีม data)
DATA = {
    "date": "2026-07-04",
    "WeatherForecasts": [
        {"name": "ชุมชนเทวสุนทร", "location": {"lat": 13.85, "lon": 100.55},
         "forecasts": [
             {"time": "2026-07-04T13:00:00+07:00", "temperature": 36.0,
              "rainfall": 0, "condition_label": "แจ่มใส"},
             {"time": "2026-07-04T14:00:00+07:00", "temperature": 31.0,
              "rainfall": 2.5, "condition_label": "มีฝน"},
         ]},
        {"name": "ชุมชนตลาดหลักสี่", "location": {},
         "forecasts": [
             {"time": "2026-07-04T15:00:00+07:00", "temperature": 30.0,
              "rainfall": 0, "condition_label": "แจ่มใส"},
         ]},
    ],
}


def test_classify_alert():
    assert classify_alert(36.0, "แจ่มใส") == "heat"
    assert classify_alert(30.0, "มีฝน") == "flood"
    assert classify_alert(36.0, "มีฝน") == "both"
    assert classify_alert(30.0, "แจ่มใส") is None
    assert classify_alert(35.0, "แจ่มใส") is None  # เกณฑ์คือ "เกิน" 35 ไม่ใช่ "ถึง"


def test_parse_forecast_carries_community_name():
    events = parse_forecast(DATA)
    assert len(events) == 2                          # ตลาดหลักสี่ไม่เข้าเงื่อนไข → ไม่มี event
    assert all(e["community"] == "ชุมชนเทวสุนทร" for e in events)
    assert [e["alert"] for e in events] == ["heat", "flood"]


def test_pick_strongest_keyed_by_community():
    # ชุมชนเดียว 2 event → เหลืออันเดียว: ฝน 2.5 มม. แรงกว่าร้อนเกิน 1 องศา
    strongest = pick_strongest_per_location(parse_forecast(DATA))
    assert len(strongest) == 1
    assert strongest[0]["community"] == "ชุมชนเทวสุนทร"
    assert strongest[0]["alert"] == "flood"


def test_filter_due_matches_current_hour_only():
    events = parse_forecast(DATA)
    at_13 = dt.datetime(2026, 7, 4, 13, 30, tzinfo=_BKK)
    due = filter_due(events, at_13)
    assert [e["alert"] for e in due] == ["heat"]     # 14:00 ยังไม่ถึง, ไม่ส่งล่วงหน้า
    at_16 = dt.datetime(2026, 7, 4, 16, 0, tzinfo=_BKK)
    assert filter_due(events, at_16) == []           # เลยเวลาแล้ว = ข้าม ไม่ส่งย้อนหลัง


def test_buttons_match_reply_flow_contract():
    """text บนปุ่มคือ "สัญญา" กับ broadcast_flow_handler — เพี้ยนเมื่อไหร่ปุ่มกดแล้วบอทงง"""
    for alert_type, cfg in _MESSAGE_CONFIG.items():
        assert YES_MAP[cfg["yes"][1]] == alert_type
        assert NO_MAP[cfg["no"][1]] == alert_type


def test_to_sdk_messages():
    msgs = to_sdk_messages(build_message("flood"))
    assert isinstance(msgs[0], TextMessage)
    assert isinstance(msgs[1], FlexMessage)
    assert msgs[1].alt_text == _MESSAGE_CONFIG["flood"]["question"]


def test_parse_forecast_skips_malformed_hours():
    # ข้อมูลจริงมีรูขาดได้ (#106 ข้อ 3) — ช่วงที่ time/temperature หาย ต้องข้าม ไม่ล้มทั้ง run
    data = {"WeatherForecasts": [{
        "name": "ชุมชนคนรักถิ่น", "location": {},
        "forecasts": [
            {"temperature": 36.5, "condition_label": "แจ่มใส"},                # time หายทั้ง key
            {"time": "2026-07-07T12:00:00+07:00", "temperature": None,
             "condition_label": "มีฝน"},                                       # temperature เป็น null
            {"time": "2026-07-07T14:00:00+07:00", "temperature": 36.5,
             "rainfall": None, "condition_label": None},                       # ดี (null → ค่า default)
        ],
    }]}
    events = parse_forecast(data)
    assert len(events) == 1
    assert events[0]["time"] == "2026-07-07T14:00:00+07:00"
    assert events[0]["alert"] == "heat"
    assert events[0]["rainfall"] == 0          # rainfall null ไม่ทำ _strength ล้ม
