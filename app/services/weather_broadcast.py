"""
weather_broadcast.py — ตัดสินจาก forecast ว่าต้องแจ้งเตือนอะไร + แต่งข้อความ (ข้อ ② ของ flow)

service นี้ทำเรื่องเดียว: forecast JSON → รายการ alert event ต่อชุมชน → LINE messages
ไม่ดึงไฟล์เอง (forecast.py), ไม่หา user (user.py), ไม่ยิง push (broadcast.py) —
ตัวเชื่อมทั้งหมดคือ weather.run_broadcast
"""
import datetime as dt

from linebot.v3.messaging import TextMessage, FlexMessage, FlexContainer

# ── เกณฑ์ตัดสิน ────────────────────────────────────────────────
# แยกเป็นค่าคงที่ ปรับที่เดียวจบ + อ่านง่ายกว่าเลข/สตริงลอยๆ กลางโค้ด
HEAT_THRESHOLD = 35.0                                   # °C ตั้งแต่เท่านี้ = ร้อน
RAIN_LABELS = {"มีฝน", "ฝนหนัก", "ฝนฟ้าคะนอง", "พายุ", "ฝนตกหนัก"}    # condition_label ที่นับว่า "ฝนตก"
#           ↑ ต้องครบทุกค่าที่ source ส่งได้ ไม่งั้น label ใหม่จะหลุด
#             (ครบชุดของ forecast Lambda: COND_LABEL ฝั่ง TMD + WMO_LABEL ฝั่ง Open-Meteo fallback)


def classify_alert(temperature: float, condition_label: str) -> str | None:
    """ดูสภาพอากาศ 1 ช่วงเวลา แล้วบอกว่าควรแจ้งแบบไหน

    คืน: "heat" / "flood" / "both" — หรือ None ถ้าไม่เข้าเงื่อนไข (ไม่ต้องแจ้ง)
    """
    is_heat = temperature > HEAT_THRESHOLD
    is_rain = condition_label in RAIN_LABELS

    # ⚠️ เช็ค "both" ก่อนเสมอ — ถ้าเอา heat/flood ขึ้นก่อน พอเข้าอันใดอันหนึ่งแล้ว
    #    return ทันที จะไม่มีวันไปถึง both (บั๊กคลาสสิกของ if-else เรียงผิดลำดับ)
    if is_heat and is_rain:
        return "both"
    if is_heat:
        return "heat"
    if is_rain:
        return "flood"
    return None


def parse_forecast(data: dict) -> list[dict]:
    """แปลง forecast JSON (ทั้งก้อน) → list ของ event ที่ต้องแจ้ง

    ไล่ทีละพื้นที่ (WeatherForecasts) → ทีละช่วงเวลา (forecasts)
    เก็บเฉพาะช่วงที่ classify_alert บอกว่าต้องแจ้ง
    """
    events = []
    for entry in data.get("WeatherForecasts", []):
        community = entry.get("name")                   # ชื่อชุมชน (แมตช์ตาราง communities)
        location = entry.get("location", {})

        for f in entry.get("forecasts", []):            # แต่ละช่วงเวลาของพื้นที่นั้น
            time, temperature = f.get("time"), f.get("temperature")
            if time is None or temperature is None:     # ข้อมูลจริงมีรูขาดได้ — ข้ามช่วงนี้ อย่าล้มทั้ง run
                print(f"⚠️ forecast: ช่วงเวลาข้อมูลไม่ครบ (time={time!r}, "
                      f"temperature={temperature!r}) — ข้ามของ {community!r}")
                continue

            alert = classify_alert(
                temperature,
                f.get("condition_label") or "",
            )
            if alert is None:                           # ช่วงนี้ไม่เข้าเงื่อนไข → ข้าม
                continue

            events.append({
                "community": community,                 # None ได้ (entry เก่าแบบจังหวัด) → unmatched
                "location": location,
                "time": time,
                "temperature": temperature,
                "rainfall": f.get("rainfall") or 0,     # null ใน JSON → 0 (กัน _strength ล้ม)
                "alert": alert,                         # "heat" / "flood" / "both"
            })

    return events


def _strength(event: dict) -> float:
    """คะแนน 'ความแรง' ของ event — ยิ่งมากยิ่งควรถูกเลือกเป็นตัวแทนของพื้นที่

    รวมความแรงฝน (มม.) กับส่วนที่ร้อนเกิน 35° เข้าด้วยกัน:
    - วันฝนตก ไม่ร้อน → เหลือแต่ rainfall
    - วันร้อน ไม่มีฝน → rainfall=0 เหลือแต่ส่วนที่เกิน 35°
    (mixed day ที่มีทั้งฝนแรงและร้อนจัด ค่อยปรับ logic ทีหลังถ้าจำเป็น)
    """
    heat_excess = max(0.0, event["temperature"] - HEAT_THRESHOLD)
    return event["rainfall"] + heat_excess


def pick_strongest_per_location(events: list[dict]) -> list[dict]:
    """ยุบ event ให้เหลือ 'อันเดียวต่อชุมชน' — เลือกช่วงเวลาที่แรงสุด

    กันสแปม: 1 ชุมชนควรถูกถามแค่วันละครั้ง เอาช่วงที่ผลกระทบชัดสุด
    """
    strongest: dict = {}
    for e in events:
        key = e["community"]
        if key not in strongest or _strength(e) > _strength(strongest[key]):
            strongest[key] = e
    return list(strongest.values())


def filter_due(events: list[dict], now: dt.datetime) -> list[dict]:
    """เฉพาะ event ที่ `time` ตกในชั่วโมงเดียวกับ now — รอบยิงของ scheduler รายชั่วโมง

    now ต้องเป็น aware datetime โซนไทย (time ในไฟล์มากับ +07:00)
    ชั่วโมงที่ผ่านไปแล้ว = ข้าม ไม่ส่งย้อนหลัง
    """
    due = []
    for e in events:
        t = dt.datetime.fromisoformat(e["time"])
        if (t.date(), t.hour) == (now.date(), now.hour):
            due.append(e)
    return due


# ── ข้อความ broadcast แต่ละแบบ ─────────────────────────────────
# แยก "คำพูด/ปุ่ม" ออกมาเป็น config → อยากแก้ข้อความ แก้ที่เดียว ไม่ต้องยุ่ง logic
# ปุ่มแต่ละอันมี (label ที่โชว์, text ที่ส่งกลับเมื่อกด) — text ตัวนี้คือ "สัญญา"
# ที่ตัว reply handler (issue AI conversation) จะเอาไปแมตช์ทีหลัง
_MESSAGE_CONFIG = {
    # flood: พยากรณ์บอกว่า "ฝนตก" อยู่แล้ว → ไม่ถามซ้ำว่าฝนตกมั้ย (รู้อยู่แล้ว)
    #        แต่ถามสิ่งที่ยังไม่รู้ = "น้ำท่วมขังตรงไหน" (ข้อมูลที่อาจารย์อยากได้)
    "flood": {
        "greeting": "🌧️ สวัสดีค่ะ ช่วงนี้ฝนตกแถวบ้าน ทีมบ้านอยู่เย็นขอถามหน่อยนะคะ",
        "question": "มีน้ำท่วมขัง หรือน้ำรอระบายตรงไหนแถวบ้านไหมคะ?",
        "yes": ("🌊 ท่วมขัง", "มีน้ำท่วมขัง"),
        "no": ("🙂 ปกติดี", "ไม่ท่วม"),
        "color": "#1DA1F2",
    },
    "heat": {
        "greeting": "☀️ สวัสดีค่ะ ทีมบ้านอยู่เย็นแวะมาทักทายค่ะ",
        "question": "วันนี้อากาศแถวบ้านร้อนมากไหมคะ?",
        "yes": ("🔥 ร้อนมาก", "ร้อนมาก"),
        "no": ("🙂 ปกติดี", "ไม่ร้อน"),
        "color": "#F59E0B",
    },
    "both": {
        "greeting": "🌧️☀️ สวัสดีค่ะ ทีมบ้านอยู่เย็นแวะมาทักทายค่ะ",
        "question": "ช่วงนี้แถวบ้านฝนตกแต่ยังร้อนอบอ้าวอยู่ไหมคะ?",
        "yes": ("😣 ใช่เลย", "ทั้งฝนทั้งร้อน"),
        "no": ("🙂 ปกติดี", "ปกติดี"),
        "color": "#8B5CF6",
    },
}


def _confirm_bubble(question: str, yes: tuple, no: tuple, color: str) -> dict:
    """สร้าง flex การ์ดคำถาม + ปุ่มใช่/ไม่ใช่ (โครงเดียว ใช้ได้ทั้ง 3 แบบ)"""
    yes_label, yes_text = yes
    no_label, no_text = no
    return {
        "type": "flex",
        "altText": question,                            # ข้อความ fallback (เวลาโชว์ preview/ไม่รองรับ flex)
        "contents": {
            "type": "bubble", "size": "kilo",
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": question, "wrap": True, "weight": "bold", "size": "md"},
            ]},
            "footer": {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "color": color,
                 "action": {"type": "message", "label": yes_label, "text": yes_text}},
                {"type": "button", "style": "secondary",
                 "action": {"type": "message", "label": no_label, "text": no_text}},
            ]},
        },
    }


def build_message(alert_type: str) -> list[dict]:
    """สร้างข้อความ broadcast ตามประเภท (heat / flood / both)

    คืน list ของ message: [ข้อความทักทาย (text), การ์ดคำถาม (flex + ปุ่ม)]
    """
    cfg = _MESSAGE_CONFIG[alert_type]
    return [
        {"type": "text", "text": cfg["greeting"]},
        _confirm_bubble(cfg["question"], cfg["yes"], cfg["no"], cfg["color"]),
    ]


def to_sdk_messages(messages: list[dict]) -> list:
    """แปลง raw dict จาก build_message → SDK objects ที่ broadcast.push_to_users รับ

    (send_test_broadcast.py ยิง HTTP ตรงเลยใช้ dict ได้ แต่ AsyncMessagingApi ต้องการ Message)
    """
    out = []
    for m in messages:
        if m["type"] == "flex":
            out.append(FlexMessage(alt_text=m["altText"],
                                   contents=FlexContainer.from_dict(m["contents"])))
        else:
            out.append(TextMessage(text=m["text"]))
    return out
