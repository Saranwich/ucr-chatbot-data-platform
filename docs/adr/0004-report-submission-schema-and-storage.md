# สคีมาและการจัดเก็บของ "แจ้งปัญหา" (problem report) — ตารางแยก, โฮสต์ LIFF บน FastAPI, auth ด้วย access token

กำลังจะสร้างหน้าฟอร์ม LIFF สำหรับ "แจ้งปัญหา" ก่อนลงมือต้องตัดสินว่า report หนึ่งใบ
มีฟิลด์อะไร, เก็บที่ไหน (ใช้ `CompletedReport` ซ้ำหรือทำตารางใหม่), หน้า LIFF โฮสต์ที่ไหน,
และยืนยันตัวตนตอน submit อย่างไร

"แจ้งปัญหา" คือ **คนละความหมาย** กับ survey: มันไม่ใช่การเดิน survey จนจบ — ไม่มี
`survey_version`, ไม่มี route, ไม่มี payload ที่เป็นคำตอบรายข้อ มันคือรายงานปัญหาอิสระ
หนึ่งใบ (คำอธิบาย + หมวด + ตำแหน่ง + รูป)

## ตัดสินใจ

**1. เก็บใน `problem_reports` (ตารางใหม่) ไม่ใช้ `CompletedReport` ซ้ำ**
ถ้าเอา `CompletedReport` มาใช้ซ้ำต้องปล่อย `survey_version`/`payload` เป็น null หรือใส่ค่าปลอม
และต้องมี discriminator แยกประเภท ซึ่งทำให้ความหมายของตาราง survey เพี้ยน
จึงทำตารางใหม่แยก domain ออกจากกัน — **แต่ลอกคอลัมน์ geospatial + รูปมาให้เหมือนเดิม**
(`location_data` เป็น PostGIS `Geometry(POINT, 4326)`, `image_path`) เพื่อให้โค้ด list/map
ของ dashboard (#32) พล็อตผ่าน `ST_X`/`ST_Y` ได้แบบเดียวกับ survey report ไม่ต้องเขียนทางใหม่

ยังคงอยู่บน Postgres เหมือนเดิมตาม [ADR 0002](0002-keep-postgres-hybrid.md): report มีตำแหน่ง
ต้องพล็อตแผนที่ → ต้องการ PostGIS ไม่ย้าย NoSQL

**2. ฟิลด์ของ report**
- `description` — ข้อความอิสระ
- `category` — หมวดจากลิสต์ตายตัว (เช่น ขยะ / ไฟส่องสว่าง / ถนน / น้ำท่วม)
- `location_data` — PostGIS `Geometry(POINT, 4326)`
- `image_path` — รูปแนบ
- `lineuser_id` (FK → `users`), `status`, `created_at`

ตัวเชื่อม (#29 tracer) ต่อแค่ `description` + `location` ให้ครบ end-to-end ก่อน
แล้ว #31 ค่อยเติม `category` + รูป

**3. โฮสต์ LIFF + auth**
เสิร์ฟหน้า LIFF เป็น static file จาก FastAPI เอง — origin เดียวกับ API จึงไม่ต้องตั้ง CORS
และ deploy ที่เดียว ตอน submit ส่ง **LIFF access token** มาใน header แล้ว backend verify token
กับ LINE เพื่อดึง `lineuser_id` ที่เชื่อถือได้ **ห้ามเชื่อ userId ที่ส่งมาใน body** (ปลอมได้)

## ผลที่ตามมา
- เพิ่ม model `ProblemReport` + สร้างตารางตอน startup เหมือน model อื่น
- endpoint รับ submit ต้อง verify access token ก่อน (logic ใหม่ที่ survey flow ไม่มี
  เพราะ survey เข้ามาทาง webhook ที่เซ็น signature แล้ว)
- dashboard ได้ report มาพล็อตฟรี ๆ เพราะคอลัมน์ตำแหน่ง/รูปหน้าตาเหมือน `CompletedReport`
