# UCR Smartcity Chatbot — น้องเมือง

บอทบน LINE OA (UCR / TONKIT Lab) ที่ชวนคนในชุมชนเล่าเรื่องสภาพแวดล้อมและ
โครงสร้างพื้นฐานแถวบ้าน แล้วสกัดออกมาเป็นรายงานพร้อมพิกัด ปลายทางคือหมุดบน
แผนที่ให้ทีมออกแบบเมืองใช้ตัดสินใจว่าควรปรับปรุงตรงไหนก่อน

กฎการเขียนโค้ดอยู่ใน [`CLAUDE.md`](CLAUDE.md) — **อ่านก่อนแก้โค้ด**

## ต้องมีอะไรบ้าง

| ของ | ใช้ทำอะไร | จำเป็นตอนเปิดแอปไหม |
|---|---|---|
| Python 3.12+ | | ใช่ |
| **Redis** | บทสนทนาที่คุยค้าง ใบที่ยังกรอกไม่เสร็จ คิวกันตาชนกัน | **ใช่** — `main.py` ping ตอนเปิด |
| **Postgres + PostGIS** | รายงานที่ปิดใบแล้ว (ของถาวร) | **ใช่** — เปิด pool ตอนเปิด |
| endpoint ของ AI | คุยกับชาวบ้าน | เฉพาะตอนคุยจริง |
| LINE OA | ช่องทางแชท | เฉพาะตอนต่อ webhook |

ทั้ง Redis และ Postgres **ไม่มีตัวไหนเป็น optional** — lifespan ต่อทั้งคู่ตอนเปิดแอป
ขาดตัวใดตัวหนึ่งแอปจะไม่ขึ้น

## ตั้งเครื่องใหม่

```bash
pip install -r requirements.txt

cp .env.example .env        # แล้วเติมค่าจริง (ดูคำอธิบายในไฟล์)

psql "$DATABASE_URL" -f schema.sql      # ครั้งเดียว
```

`schema.sql` **ไม่มี `IF NOT EXISTS`** ตั้งใจให้รันซ้ำแล้วพังให้เห็น
ดีกว่าเงียบแล้วปล่อยตารางเก่าที่หน้าตาไม่ตรงกับไฟล์นี้อยู่ต่อไป

## รัน

```bash
uvicorn app.main:app --reload
```

ขึ้นแล้วจะเห็น `app opened` เช็คได้ที่ `GET /api/health`

ต่อ LINE: `ngrok http 8000` แล้วเอา URL ไปตั้งเป็น webhook `https://<ngrok>/callback`

## ทางเข้าที่มี

| ทาง | ทำอะไร |
|---|---|
| `POST /callback` | webhook ของ LINE — ตอบ 200 ทันที แล้วไปคุยต่อเบื้องหลัง |
| `GET /dashboard` | แผนที่ให้ทีมออกแบบเปิดดู (อ่านอย่างเดียว) |
| `GET /api/dashboard/reports` | ข้อมูลที่หน้าแผนที่ไปดึงเอง |
| `GET /api/dashboard/image/{id}` | รูปของใบนั้น |
| `GET /api/health` | Redis ยังอยู่ไหม |

ของสำหรับ dev (ไม่ต้องผ่าน LINE):

| ทาง | ทำอะไร |
|---|---|
| `GET /api/playground?message=` | ยิงเข้าโมเดลตรง ๆ — เช็คว่า key กับ endpoint ใช้ได้ |
| `GET /api/survey?message=&session_id=` | คุยกับน้องเมืองโดยไม่ต้องมี LINE ใส่ `latitude`/`longitude` แทนปุ่มแชร์ตำแหน่งได้ |
| `GET /api/survey/draft?session_id=` | ตอนนี้ในใบมีอะไรแล้ว ยังขาดอะไร |
| `DELETE /api/survey/draft?session_id=` | เริ่มคุยใหม่ |
| `GET /api/reports` | ทุกใบที่ลงที่เก็บถาวรแล้ว |

## ของที่ไม่ขึ้น git

- `storage/` — รูปที่ชาวบ้านส่งมา + บทสนทนาต้นฉบับ (วันย้ายขึ้น S3 แก้แค่
  `clients/media.py` กับ `clients/transcript.py`)
- `.env` — ค่าจริง
- `local/` — สมุดจดส่วนตัว
