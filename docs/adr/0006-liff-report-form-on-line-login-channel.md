# หน้าฟอร์ม "แจ้งปัญหา" เป็น LIFF โฮสต์บน LINE Login channel — เลือก LIFF (ไม่ใช่ signed token / เว็บ anonymous)

สืบเนื่องจาก [ADR 0004](0004-report-submission-schema-and-storage.md) ที่ตัดสินสคีมา/สตอเรจของ
"แจ้งปัญหา" ไว้แล้ว ADR นี้ตัดสิน **วิธีเปิดฟอร์มและยืนยันตัวตน** ซึ่งเปลี่ยนเงื่อนไขเพราะ
ข้อจำกัดใหม่ของ LINE

## บริบทที่เปลี่ยน

LINE **ยกเลิกการเพิ่ม LIFF app บน Messaging API channel** แล้ว — ต้องสร้างบน **LINE Login
channel** แทน และกำลังรีแบรนด์ LIFF เข้า "LINE MINI App" (ไทยยังสร้าง MINI App channel ไม่ได้
ต้องรออนุมัติจาก subsidiary ซึ่งช่องทางยังไม่เปิด) เอกสาร LINE ระบุเองว่า ถ้ายังไม่เข้าเงื่อนไข
MINI App ให้ **"continue to use LIFF apps"**

## ตัดสินใจ

**1. ใช้ LIFF (ไม่ใช่ signed-token-in-URL หรือเว็บ anonymous)**
ชั่งจาก *ประสบการณ์ผู้ใช้/เป้า crowdsourcing* เป็นหลัก ไม่ใช่ความง่ายฝั่งเรา:
- LIFF = แตะปุ่มเดียวจาก rich menu → เปิดในแอป LINE ทันที, ได้ตัวตนอัตโนมัติ, จบแล้วปิดเอง
- signed token = ได้ตัวตนเหมือนกันแต่ rich menu URI ฝัง token รายคนไม่ได้ → ต้องเด้งลิงก์ในแชต
  (+1 แตะ) ลื่นน้อยกว่า
- เว็บ anonymous = ไม่มีตัวตน → ตามงาน/กัน spam ไม่ได้ ขัดเป้า

ต้นทุนที่เพิ่ม (เปิด Login channel + LIFF app) ตกที่ทีม ไม่ใช่ผู้ใช้

**2. โฮสต์ LIFF app บน LINE Login channel ใต้ provider เดียวกับบอท**
provider เดียวกัน → `userId` ที่ได้จาก LIFF **ตรงกับ** `lineuser_id` ของบอท (LINE การันตี userId
คงที่ข้าม channel ใน provider เดียวกัน) ผูกข้อมูล report กับผู้ใช้คนเดิมที่ทำ survey ได้

**3. ยืนยันตัวตนด้วย LIFF access token (ยึดเจตนา ADR 0004)**
หน้า LIFF ส่ง access token มาใน `Authorization: Bearer` → backend เรียก `api.line.me/v2/profile`
verify เพื่อดึง `lineuser_id` ที่เชื่อถือได้ **ห้ามเชื่อ userId ใน body** (`app/utils/liff_auth.py`)

**4. degrade เป็น anonymous เมื่อเปิดนอกแอป LINE**
ไม่มี `LIFF_ID` หรือไม่มี token → `lineuser_id = null` เพื่อให้ dev เทสฟอร์มได้ก่อนตั้ง channel เสร็จ
(`form_reports.lineuser_id` จึง nullable)

**5. การปักตำแหน่งใช้แผนที่ปักหมุดลากได้ (Leaflet + OpenStreetMap)**
geolocation ในแอปมักเพี้ยน → seed ด้วย geolocation แล้วให้ผู้ใช้ลาก/แตะหมุดปรับเอง ไม่ต้องใช้ API key

## ผลที่ตามมา

- เพิ่ม env `LIFF_ID`; ฉีดเข้าหน้า HTML ตอน serve (`GET /report`)
- ปุ่ม "แจ้งปัญหา" บน rich menu เป็น URI action → `https://liff.line.me/<LIFF_ID>`
- รูปยังเก็บ local `uploads/` (POC) ตาม [ADR 0005](0005-survey-photo-durable-storage.md) → ย้าย S3 ภายหลัง
- โครงเผื่อ MINI App: เมื่อไทยเปิดให้สร้าง MINI App channel ค่อยย้าย LIFF app ไป (LINE จะมีเครื่องมือ migrate)
