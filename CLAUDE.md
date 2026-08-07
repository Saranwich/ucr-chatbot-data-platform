# UCR Smartcity Chatbot — น้องเมือง

## โปรเจกต์นี้คืออะไร

บอทบน LINE OA (UCR / TONKIT Lab) ที่ชวนคนในชุมชนเล่าเรื่องสภาพแวดล้อมและ
โครงสร้างพื้นฐานแถวบ้าน แล้วสกัดออกมาเป็น **รายงาน** พร้อมพิกัด ปลายทางคือ
**หมุดบนแผนที่ให้ทีมออกแบบเมือง**ใช้ตัดสินใจว่าควรปรับปรุงตรงไหนก่อน

sensor บอกได้ว่าตรงนี้ 38°C แต่บอกไม่ได้ว่ายายที่เดินไปตลาดทุกเช้าเดินไม่ไหว
เพราะไม่มีร่มเงา — **เราเก็บส่วนหลัง** เราไม่ใช่ศูนย์ช่วยเหลือ ไม่ได้เป็นคนไปแก้

หนึ่งบทสนทนา → หนึ่งใบรายงาน เก็บลงตาราง `reports` ตารางเดียว
ทีมเปิดดูที่ `/dashboard` (แผนที่ Leaflet อ่านอย่างเดียว)

**หัวใจที่ห้ามพัง:** AI พิมพ์ว่า "จดให้แล้วค่ะ" ไม่มีผลอะไรทั้งนั้น
ต้องเรียก `record_report` เท่านั้นข้อมูลถึงลง และ **`services/survey.py` เป็นคนตัดสิน**
ว่าครบหรือยัง ไม่ใช่ AI

> โครงสร้างนี้ยกมาจาก `Saranwich/Here-what-I-think-cstusparkcampphase3`
> คอมเมนต์ยาว ๆ ในโค้ดคือบันทึกเหตุการณ์ที่เคยพังจริง **อย่าลบทิ้งเวลาแก้โค้ด**

---

# กฎของโปรเจกต์นี้

อ่านก่อนเขียนโค้ด ใช้ทั้งกับคนและกับ AI

## โครงสร้าง

```
app/
  main.py              สร้าง app + lifespan + ต่อ router เท่านั้น
  core/config.py       อ่านค่าจาก .env
  api/                 route — ชั้นเดียวที่รู้จัก FastAPI
  services/            ตรรกะของเรา (สมอง)
  clients/             คุยกับของนอกบ้าน (Redis, AI, LINE)
```

## กฎ

**1. ลูกศรวิ่งทางเดียว — ห้ามย้อน**

```
api/ → services/ → clients/
```

`services/` และ `clients/` ห้าม import อะไรจาก `api/`
`clients/` ห้าม import อะไรจาก `services/`

**2. มีแต่ `api/` ที่รู้จัก FastAPI**

ถ้าเปิดไฟล์ใน `services/` หรือ `clients/` แล้วเจอคำว่า `fastapi`, `Request`, `Depends` แปลว่าวางผิดที่

`Depends` ทุกตัวอยู่ใน `api/deps.py`

**3. `services/` ห้ามรู้จัก LINE**

`services/` รับ-ส่งแค่ `str` และ `dict` ธรรมดา ห้ามมีคำว่า `linebot`, `reply_token`, `event`
งานแกะกล่องของ LINE อยู่ใน `api/line.py` งานยิงกลับอยู่ใน `clients/line.py`

เหตุผล: วันหลังเพิ่ม Discord หรือเว็บ จะได้เพิ่มแค่ไฟล์ใน `api/` โดยไม่ต้องแตะสมอง

**4. `main.py` ห้ามมี route**

มีได้แค่ lifespan กับ `include_router`

**5. ตั้งชื่อไฟล์ตามหน้าที่ ไม่ใช่ตามยี่ห้อ**

`llm.py` ไม่ใช่ `openai.py` — วันหลังเปลี่ยนเจ้าจะได้ไม่ต้องแก้ชื่อทั้งโปรเจกต์

**6. lifespan มี `yield` ได้อันเดียว**

บนสุด = ตอนเปิดแอป / ล่าง `yield` = ตอนปิด / `yield` ต้องอยู่ใน `try` ส่วน setup อยู่นอก
ห้ามใช้ `@app.on_event` มันตกรุ่นแล้ว

**7. ห้ามสร้าง connection เองในไฟล์อื่น**

Redis ต่อครั้งเดียวใน lifespan แล้วส่งต่อผ่าน `Depends(get_redis)`

## วิธีเช็คเร็ว ๆ ว่ายังไม่พัง

```bash
grep -rniE "fastapi|linebot|request" app/services   # ต้องไม่เจอ
grep -rniE "fastapi" app/clients                    # ต้องไม่เจอ
grep -rn "from app.api" app/services app/clients    # ต้องไม่เจอ
grep -rn "from app.services" app/clients            # ต้องไม่เจอ
```

## เรื่อง schema

Postgres + PostGIS ใช้อยู่แล้ว ผ่าน `asyncpg` ดิบ ๆ ไม่มี ORM
ตารางอยู่ที่ `schema.sql` รากโปรเจกต์ **รันมือ** — แอปไม่สร้างตารางให้ตอนเปิด
โค้ดที่แก้ schema ได้ระหว่างรัน คือโค้ดที่ทำ schema พังได้ระหว่างรันเหมือนกัน

สองตารางเท่านั้น: `reports` (แบน `categories` เป็น `text[]`) กับ `report_images`
**ไม่มี FK ไม่มี CHECK โดยตั้งใจ** — `_sanitize()` ใน `services/survey.py` กรองให้แล้ว
ใส่ CHECK เมื่อไหร่ ค่าเพี้ยนช่องเดียวจะทำ INSERT ล้มทั้งแถว = เสียเรื่องที่เขาอุตส่าห์เล่าทั้งใบ

pydantic schemas, SQLAlchemy, alembic — เอาไว้ทีหลัง ตอนใส่ค่อยเพิ่ม
`schemas/`, `models/`, `repositories/` เข้ามา โดยไม่ต้องรื้อของเดิม

## ยังไม่ทำตอนนี้

- **broadcast อากาศ** (พยากรณ์ → ร้อน/น้ำท่วม → ยิงการ์ด → เก็บผลกระทบ)
  ถอดออกตอนรื้อ ยกกลับมาทีหลังเป็นสาขาของตัวเอง — `source='broadcast'`
  กับ `survey.reply(..., source=)` เดินสายรอไว้แล้ว
  ของเดิมยังอ่านได้: `git show dev:app/services/weather.py`
- **auth ของแดชบอร์ด** ตอนนี้เปิดโล่ง ยังไม่ได้ต่อออกเน็ต
- **S3** — แก้แค่ `clients/media.py` กับ `clients/transcript.py` สองไฟล์
- **tests** ยังไม่มี ตัวที่ควรมีก่อนเพื่อน: `missing()` / `next_goal()` /
  `_sanitize()` / `_buttons()` / `public()` — ฟังก์ชันล้วน ไม่ต้องมี Redis หรือ Postgres

## git

commit ใช้ชื่อเจ้าของ repo เท่านั้น **ห้ามใส่ Co-Authored-By หรือ link ของ AI**

## Agent skills

- **Issue tracker** — GitHub Issues ของ `tonkitcstu/ucr-smartcity_chatbot` ดู `docs/agents/issue-tracker.md`
- **Triage labels** — ห้าป้ายหลัก ดู `docs/agents/triage-labels.md`
