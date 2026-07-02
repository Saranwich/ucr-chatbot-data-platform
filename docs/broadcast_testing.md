# วิธีเทส Weather Broadcast

คู่มือเทสฟีเจอร์ broadcast แจ้งเตือนอากาศ (`scripts/weather_broadcast.py`)
ตั้งแต่เทส logic แบบ offline จนถึงยิงข้อความจริงเข้ามือถือ

---

## หลักการออกแบบคำถาม — ถามสิ่งที่ "ไม่รู้" ไม่ถามสิ่งที่ "รู้แล้ว"

หลักคิดกลางของ broadcast นี้: **พยากรณ์บอกเราแล้วว่าจะฝนตก/ร้อน → ถามซ้ำว่า
"ฝนตกมั้ย" ไม่มีประโยชน์** เพราะเรารู้อยู่แล้ว สิ่งที่มีค่าคือ **สิ่งที่พยากรณ์บอกไม่ได้**
= ผลกระทบจริงในพื้นที่

### กรณี flood (ฝนตก)
- ❌ ถาม "ฝนตกมั้ย" → user กดใช่ (ก็ฝนตกจริง) แต่ได้ข้อมูลที่รู้อยู่แล้ว = เปล่าประโยชน์
- ✅ ถาม "มีน้ำท่วมขังตรงไหนไหม" → **น้ำท่วมขังคือสิ่งที่พยากรณ์บอกไม่ได้** และเป็นสิ่งที่
  อาจารย์อยากได้ (แผนที่จุดน้ำท่วม)
- **"ไม่ท่วม" ก็มีค่า** — บอกว่าจุดนี้ระบายน้ำดี ไม่ใช่จุดเสี่ยง → ทั้ง "ใช่/ไม่" ช่วยปั้น
  แผนที่ "ตรงไหนท่วม / ตรงไหนไม่ท่วม"
- 🎯 หัวใจ = ตอนตอบ "มีน้ำท่วม" ต้อง **ขอตำแหน่ง (location) ต่อ** เพื่อได้ "จุด" มาปักแผนที่จริง
  (step นี้อยู่ใน reply handler / issue AI conversation)

### กรณี heat / both
- อุณหภูมิเรารู้จากพยากรณ์ แต่ **"ร้อนแล้วกระทบชีวิตเขายังไง" เราไม่รู้** → คำถามแรกเป็น
  ด่านเปิดบทสนทนา ข้อมูลจริงมาจากการ **คุยต่อ** (AI conversation) ว่าร้อนแล้วลำบากตรงไหน

> สรุปหลักการ: **ทุกคำถามควรเล็งไปที่ "ข้อมูลที่ยังไม่มี"** ไม่ใช่ยืนยันสิ่งที่พยากรณ์บอกได้อยู่แล้ว

---

## เทสมี 3 ระดับ

| ระดับ | เทสอะไร | ต้องมี |
|---|---|---|
| **1. Logic (offline)** | parse JSON + เลือก heat/flood/both + dedup | แค่ Python (ไม่ต้องต่อเน็ต/LINE) |
| **2. ส่งข้อความ** | ยิง flex จริงเข้ามือถือ | test OA token + user id ของตัวเอง |
| **3. ครบวง** | กดปุ่ม → reply → AI คุยต่อ | server + ngrok (= scope ของ issue AI conversation) |

> ตอนนี้ทำได้ถึง **ระดับ 2** — ระดับ 3 รอ issue AI conversation

---

## ระดับ 1 — เทส logic (offline)

พิสูจน์ว่าอ่าน forecast แล้วตัดสิน heat/flood/both + ยุบเหลือวันละครั้งต่อพื้นที่ได้ถูก
โดยไม่ต้องยุ่งกับ LINE เลย

```python
import json
from scripts.weather_broadcast import parse_forecast, pick_strongest_per_location

data = json.load(open("forecast_2026-06-30.json", encoding="utf-8"))
events = parse_forecast(data)                 # ดิบ: ทุกช่วงที่ต้องแจ้ง
final = pick_strongest_per_location(events)   # ยุบ: อันเดียวต่อพื้นที่ (แรงสุด)

for e in final:
    print(e["location"].get("province"), e["time"], e["alert"])
```
- เอา forecast จริงมาลองได้: `https://ucr-forecatst-bucket.s3.ap-southeast-1.amazonaws.com/forecast/YYYY-MM-DD.json`
- ตรวจว่าวันฝน → `flood`, วันร้อน (>35°) → `heat`, ทั้งคู่ → `both`

---

## ระดับ 2 — ยิงข้อความจริงเข้ามือถือ

ใช้ `scripts/send_test_broadcast.py` ส่ง flex ไปหา **user id ของตัวเองคนเดียว**
(ใช้ `push` ไม่ใช่ `multicast` → ไม่โดนคนอื่น)

### เตรียม 2 อย่าง
1. **`CHANNEL_ACCESS_TOKEN` ใน `.env`** = token ของ **test OA** (ไม่ใช่ production!)
2. **LINE user id ของแก** — เอาจาก LINE Developers Console → Messaging API channel (ตัว test)
   → แท็บ **Basic settings** → หัวข้อ **"Your user ID"** (`Uxxxx...`)
   > อย่าลืม **แอดเพื่อนกับ test OA** ด้วย ไม่งั้น bot ส่งหาไม่ได้

### รัน
```bash
# ลองดูก่อนแบบไม่ส่งจริง (แนะนำให้ทำก่อนทุกครั้ง)
python scripts/send_test_broadcast.py --test-user Uxxxx --type flood --dry-run

# ส่งจริง — แล้วเช็คที่มือถือ
python scripts/send_test_broadcast.py --test-user Uxxxx --type flood
python scripts/send_test_broadcast.py --test-user Uxxxx --type heat
python scripts/send_test_broadcast.py --test-user Uxxxx --type both
```
เปิด LINE แล้วดูว่าได้ข้อความทักทาย + การ์ดคำถาม + ปุ่มยืนยัน ครบมั้ย หน้าตาโอเคมั้ย

---

## ⚠️ ข้อควรระวัง
- **ใช้ test OA เท่านั้น** — เช็ก `.env` ให้ชัวร์ว่า token ไม่ใช่ของ production
- **อย่าเพิ่ง `multicast` ตามชุมชน** ตอนเทส — จะโดน user จริง ใช้ `send_test_broadcast.py` (push หาตัวเอง) ก่อน
- กด `--dry-run` ดูก่อนส่งจริงทุกครั้ง จะปลอดภัยสุด

---

## ยังไม่ได้เทส (รอต่อ)
- **จับ user ตามชุมชน + multicast จริง** — รอ schema ชุมชนจากเพื่อน (ตอนนี้ location ใน forecast ยังเป็นจังหวัด mock)
- **timing +30 นาที / EventBridge** — รอความถี่ trigger จากเพื่อน
- **ครบวง (กดปุ่ม → AI คุยต่อ)** — issue AI conversation แยกต่างหาก (ต้องรัน server + ngrok)
