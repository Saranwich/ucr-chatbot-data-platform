# สถานะ API สำหรับทีม Dashboard (re: #78)

**โน้ตสำคัญ: นี่คือ Hotfix ชั่วคราว (V1)**
API ชุดนี้ทำขึ้นมาเพื่อให้ทีม Dashboard มีของใช้ปลดบล็อกงานไปก่อน ไม่ใช่โครงสร้างถาวร
- ตอนนี้ระบบ Chatbot กำลังย้ายไปเป็น AI-version (V2) ซึ่งจะเก็บข้อมูลเป็นคอลัมน์ SQL จริง (เช่น severity, title / problem_summary, extraction_confidence)
- ทีม Dashboard ใช้ V1 นี้เชื่อมต่อได้เลย แต่อย่ายึดติดกับ shape ข้อมูลนี้มากเกินไป เพราะเดี๋ยวตอน V2 มา field และ endpoint ชุดนี้จะเปลี่ยน

## 1. กฏทั่วไปของ API

- **HTTP Method:** ทุก endpoint เป็น GET
- **Auth:** ต้องแนบ JWT ใน Header: `Authorization: Bearer <token>` เสมอ
- **Base URL & Token:** ขอทางช่องทางส่วนตัวของทีม
- **Hotfix Scope:** envelope, pagination, derived fields และ stats คือส่วนที่เพิ่มใน hotfix — ตอนนี้อยู่ใน working tree บน branch main (**ยังไม่ commit/deploy**) ส่วนเวอร์ชันก่อน hotfix คือ old/1.0

## 2. ข้อมูลมี 2 สาย (อย่าสับสน)

ข้อมูลมี 2 โครงสร้างที่ต่างกันชัดเจน:

| ข้อมูล | Endpoint | อธิบาย |
|---|---|---|
| **1. Survey Reports** (แบบสำรวจ) | `/api/dashboard/reports` | แบบสำรวจเชิงคุณภาพ ไม่มีคอลัมน์ category/title จริงใน DB — ใช้ `problem_type` แทน category, `status` คำนวณให้ (="completed"), ส่วน title รอ V2 |
| **2. Form Reports** (แจ้งปัญหาผ่านฟอร์ม) | `/api/dashboard/form-reports` | แจ้งปัญหาผ่านฟอร์ม LIFF มีคอลัมน์ category, status และ description จริงใน database |

## 3. รายการ Endpoint ทั้งหมด

| Endpoint | คืนอะไร |
|---|---|
| `/api/dashboard/stats` | ตัวเลขสรุป (total users, completed, incomplete) |
| `/api/dashboard/available-dates` | วันที่ทั้งหมดที่มีรายงาน (เอาไปทำ date filter) |
| `/api/dashboard/reports` | รายการ survey reports ที่เสร็จแล้ว (รองรับ filter ช่วงวันและประเภทปัญหา) |
| `/api/dashboard/reports/{id}` | survey report รายการเดียว (ไม่มี envelope หุ้ม) |
| `/api/dashboard/incomplete-reports` | รายการที่ทำค้าง + บอกว่าเทงานที่คำถามไหน |
| `/api/dashboard/form-reports` | รายการแจ้งปัญหาจากฟอร์ม LIFF |
| `/api/dashboard/image/{id}` | ไฟล์รูปของ survey (ต้องแนบ JWT) |
| `/api/form-reports/{id}/image` | ไฟล์รูปของ form report (ต้องแนบ JWT) |

**เครื่องมือดูข้อมูลจริง:** เข้าไปที่ `/viewer` วาง JWT แล้วดู stats, รายงาน, พิกัด และรูปภาพของ prod ได้เลยระหว่างรอ dashboard ตัวจริง

**ข้อมูลจริงตอนนี้:** 43 users, 49 completed, 28 incomplete (survey fdg210626 และ fdg140626), มีพิกัด 27, มีรูป 19

## 4. จากที่ขอมา (#78) ตอนนี้ทำได้แค่ไหน

### ทำได้แล้วใน V1
- **Core Fields:** `report_id`, `latitude` / `longitude` (เป็น null ได้), `images[]`, `payload`, `survey_version`
- **Derived Fields:** `problem_type` (ดึงจาก payload.q_start), `is_complete`, `status`, `has_location`, `has_image`, `source`
- **Timezone:** `created_at` ปรับเป็นเวลาไทย (+07:00) เรียบร้อยแล้ว
- **Stats (`/stats`):** แยกตาม problem_type, survey_version, การมีพิกัด/รูปภาพ และยอดรายวัน
- **Pagination & Envelope:** ทุก list endpoint ส่งกลับมาเป็น `{items, total, page, limit}` รองรับพารามิเตอร์ `?page` และ `?limit` (default 20, สูงสุด 200)
- **Filter (`/reports`):** กรองด้วย `?date`, `?from`/`?to` และ `?problem_type`
- **Form Reports:** มีคอลัมน์จริงสำหรับ category, status และ description

### ยังทำไม่ได้ใน V1 (รอ V2)
- **`severity`:** ใน survey ไม่เคยถามคำถามนี้ เลยไม่มีข้อมูล
- **`title` / `problem_summary`:** ตัว AI สรุปจะมาใน V2 (ตอนนี้ V1 ยัดค่า problem_type แทนไปก่อน)
- **`extraction_confidence` / `confidence_by_field`:** V1 ผู้ใช้กดเลือกค่าตายตัว ไม่ได้ใช้ AI สกัด เลยไม่มีค่าความมั่นใจ (ส่ง null เสมอ)
- **`?severity` Filter & `by_severity` Stats:** ยังไม่มีด้วยเหตุผลเดียวกัน

## 5. ข้อจำกัดที่ต้องรู้

- **CORS:** ตอนนี้ allow แค่ `localhost:4200` และ `FRONTEND_URL` ต้องส่ง domain ของ dashboard (เช่น dashboard_wa) ให้ทีม API เพิ่มก่อน เบราว์เซอร์ถึงจะ fetch ได้
- **รูปภาพ:** รูปทั้งหมดต้องแนบ JWT ใช้แท็ก `<img src="...">` ดึงตรงๆ ไม่ได้ ต้องใช้ `fetch()` พร้อม `Authorization` Header แล้วแปลงเป็น Object URL (ดูตัวอย่างที่ `app/static/viewer.html`)
- **พิกัด null ได้:** ค่า lat/lng เป็น null ได้ (ประมาณ 1/3 ของผู้ใช้ไม่แชร์พิกัด) ระบบจะไม่ข้าม record พวกนี้ และส่งกลับมาตามปกติ
- **Pagination:** default 20 รายการ/หน้า สูงสุด 200 (ข้อมูลจริงตอนนี้มี 49 รายการ ดึงครบได้ในรอบเดียวด้วย `?limit=200`)

## 6. อธิบายการทำงานของแต่ละ Endpoint

### `GET /api/dashboard/stats`
ตัวเลขสรุปสำหรับเอาไปโชว์ในการ์ดหน้า dashboard
```json
{
  "total_users": 43,
  "total_completed_reports": 49,
  "total_incomplete_reports": 28,
  "by_problem_type": { "อากาศร้อน": 35, "น้ำท่วม/น้ำขัง": 13, "ขยะ": 1 },
  "by_survey_version": { "fdg210626": 29, "fdg140626": 20 },
  "with_location": 27, "without_location": 22,
  "with_image": 19, "without_image": 30,
  "daily": [ { "date": "2026-06-14", "count": 12 } ]
}
```

### `GET /api/dashboard/available-dates`
วันที่ทั้งหมดที่มี completed report เอาไปทำ date filter dropdown (เรียงใหม่→เก่า)
```json
{
  "dates": ["2026-06-26", "2026-06-25", "..."]
}
```

### `GET /api/dashboard/reports`
รายการแบบสำรวจที่เสร็จแล้ว (สำหรับปักหมุดบนแผนที่และโชว์ในตาราง)
- **Query Params:** `?date=YYYY-MM-DD`, `?from=` / `?to=` (ช่วงวัน), `?problem_type=`, `?page=` (default 1), `?limit=` (default 20, สูงสุด 200)
- **Response Format:** ส่งกลับมาใน envelope `{items, total, page, limit}` โดย total คือจำนวนทั้งหมดหลัง filter
- **Payload & Images:** `payload` เก็บคำตอบ (key ไม่ตายตัว เช่น `q_heat_*`, `q_flood_*`) ส่วน `images[]` ดึงจาก payload โดย 1 รายงานอาจมีหลายรูป
- **Privacy:** response มี `lineuser_id` (LINE user id = PII) ติดมาด้วย ระวังตอนแสดง/log
```json
{
  "items": [
    {
      "report_id": 17,
      "lineuser_id": "U3770...",
      "source": "survey",
      "survey_version": "fdg140626",
      "problem_type": "น้ำท่วม/น้ำขัง",
      "status": "completed",
      "is_complete": true,
      "latitude": 14.073543,
      "longitude": 100.605714,
      "has_location": true,
      "images": [
        {
          "image_id": "618324572285960278",
          "image_url": "/api/dashboard/image/618324572285960278"
        }
      ],
      "has_image": true,
      "payload": {
        "q_start": "น้ำท่วม/น้ำขัง",
        "q_flood_location": "ทางเดินหรือถนน"
      },
      "created_at": "2026-06-14T03:11:10.732923+07:00"
    }
  ],
  "total": 49,
  "page": 1,
  "limit": 20
}
```

### `GET /api/dashboard/reports/{report_id}`
ดึงข้อมูล survey report รายการเดียว สำหรับหน้า detail
- **Response Format:** ใช้โครงสร้างเดียวกับ item ใน `/reports` แต่ไม่มี envelope หุ้ม
- **Error:** ถ้าไม่เจอ คืนค่า `404 {"detail": "Report not found"}`

### `GET /api/dashboard/incomplete-reports`
รายการแบบสำรวจที่ทำค้าง (drop-off) สำหรับวิเคราะห์ว่าคนเทงานที่จุดไหน
- **Query Params:** `?date=`, `?page=`, `?limit=`
- **Response Format:** มี envelope `{items, total, page, limit}` หุ้ม
- **Special Fields:** มีค่า `is_complete: false` และบอกคำถามสุดท้ายที่ค้างอยู่ใน `drop_off_question_id` กับ `drop_off_question_text` ส่วน `status` จะเป็นเช่น `timeout`, `cancelled`

### `GET /api/dashboard/form-reports`
รายการแจ้งปัญหาจากฟอร์ม LIFF (คนละสายกับ survey) มีคอลัมน์จริงสำหรับ `category`, `status`, `description`
- **Query Params:** `?date=`, `?page=`, `?limit=`
- **Response Format:** มี envelope `{items, total, page, limit}` หุ้ม (item มี `lineuser_id` = PII ระวังด้วย)
```json
{
  "items": [
    {
      "report_id": 29,
      "lineuser_id": "U3770...",
      "source": "form_report",
      "category": "จุดเสี่ยง/ความปลอดภัย",
      "description": "มีการก่อสร้างเขื่อนริมคลอง...",
      "status": "new",
      "latitude": 13.877777,
      "longitude": 100.575571,
      "has_location": true,
      "image_url": "/api/form-reports/29/image",
      "has_image": true,
      "created_at": "2026-06-26T09:30:49.319422+07:00"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

### `GET /api/dashboard/image/{image_id}` — รูปของ survey
- **Format:** Binary Stream (`image/jpeg`) · **Auth:** ต้องแนบ JWT
- **Storage Behavior:** หาในไฟล์เก็บถาวรก่อน (`survey/<id>.jpg`) ถ้าไม่มีดึงสดจาก LINE CDN ให้
- **Error:** รูปหมดอายุ/ไม่เจอ → `404 {"detail": "Image not found or expired"}`

### `GET /api/form-reports/{report_id}/image` — รูปของ form report
- **Format:** Binary Stream (เดา media type จากไฟล์ ไม่ใช่รูปก็ fallback `image/jpeg`) · **Auth:** ต้องแนบ JWT
- **Storage Behavior:** อ่านจาก local storage อย่างเดียว **ไม่มี CDN fallback**
- **Error:** report ไม่มีรูป → `404 {"detail": "No image for this report"}` · ไฟล์หาย → `404 {"detail": "Image file missing"}`

## 7. Auth และ Error

- **Header:** `Authorization: Bearer <token>` (ใช้ JWT HS256 เซ็นด้วย SECRET_KEY)
- **Claims:** ต้องมี `sub` เท่านั้น — `role` จะใส่หรือไม่ก็ได้ (ปัจจุบัน API ไม่ได้ตรวจ role; endpoint ใช้ `get_current_user` ไม่ใช่ admin-only)
- **การสร้าง Token เทส:** ตอนนี้ยังไม่มี endpoint login dev ต้องสร้าง token เองสำหรับเทส โดยเอา SECRET_KEY (ขอจากทีม chatbot) มาเสกผ่านไลบรารี python-jose:

```python
from jose import jwt

SECRET_KEY = "<ขอจากทีม chatbot>"
token = jwt.encode({"sub": "dev", "role": "admin"}, SECRET_KEY, algorithm="HS256")
print(token)
```
เอา token ที่ได้ไปใส่ใน Header `Authorization: Bearer <token>` หรือเอาไปวางใน `/viewer` เพื่อเทส

### ตัวอย่าง Error ที่จะเจอ
- `401 Unauthorized` (ไม่แนบ token): `{"detail": "Not authenticated"}`
- `401 Unauthorized` (token ผิดหรือหมดอายุ): `{"detail": "Could not validate credentials"}`
- `400 Bad Request` (วันที่ผิดรูปแบบ): `{"detail": "Invalid date format, expected YYYY-MM-DD"}`
