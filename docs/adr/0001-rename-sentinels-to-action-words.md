---
status: accepted (ชั่วคราว — รอ superseded ด้วยงาน postback, issue #18)
---

# เปลี่ยน magic-string sentinel เป็นคำกริยาภาษาคน (ชั่วคราว)

## บริบท

ระบบ survey มี sentinel 2 ตระกูลที่เคยเป็น magic string รูป `__key__`:

- **control** (อยู่ใน Python): `__go_back__`, `__confirm_multi__` — ปุ่ม `MessageAction` ส่งค่านี้กลับมาเป็น "ข้อความ" แล้วโค้ดดักไว้ (`survey_service.py`, `routing.py`)
- **data** (อยู่ใน survey JSON): `__free_text__`, `__skip__` — เป็น `value` ของ option ที่ถูกเซฟเป็น "คำตอบ" (ไม่มี `when`/condition ไหน match มัน)

## สิ่งที่ตัดสินใจ

เปลี่ยนค่าทั้ง 4 เป็นคำภาษาคนตรง ๆ โดย **ยังคง `MessageAction`** ไว้:

| เดิม | ใหม่ | ที่อยู่ |
|---|---|---|
| `__go_back__` | `ย้อนกลับ` | constant `GO_BACK_KEYWORD` ใน `config.py` |
| `__confirm_multi__` | `ยืนยัน` | constant `CONFIRM_KEYWORD` ใน `config.py` |
| `__skip__` | `ข้าม` | `value` ของ option (JSON) |
| `__free_text__` | `พิมพ์เอง` | `value` ของ option (JSON) |

control 2 ตัวตั้งเป็น constant เพื่อให้มีแหล่งความจริงเดียว (ใช้ทั้งจุดสร้างปุ่มและจุดเทียบ)

## ทำไม

- **อ่านง่ายขึ้น** — ค่าที่ส่ง/ที่เซฟลง report เป็นภาษาคน ไม่ใช่ `__skip__`
- **ได้ keyboard fallback มาฟรี** — เพราะปุ่มส่ง text `"ย้อนกลับ"`/`"ยืนยัน"` เท่ากับที่ผู้ใช้พิมพ์เองได้ → กดหรือพิมพ์ก็ทำงานเหมือนกัน ทุกอุปกรณ์ (phone/PC/iPad)

## ⚠️ นี่คือของชั่วคราว — ต้องมาแก้

ตั้งใจให้เป็น **stepping stone** ไม่ใช่ปลายทาง ปลายทางคือเปลี่ยนปุ่ม control ไป **`PostbackAction`** (`data=action=go_back`) — ตาม **issue #18** — เพื่อ:

1. เลิกให้ magic string "รั่ว" เข้าไปปนกับคำตอบใน service layer
2. ปิดจุดชนเชิงทฤษฎี: ถ้าผู้ใช้พิมพ์ `"ย้อนกลับ"`/`"ยืนยัน"`/`"ข้าม"`/`"พิมพ์เอง"` เป็น**คำตอบ free-text** พอดี ระบบจะตีความผิด (ตอนนี้ยอมรับความเสี่ยงนี้ เพราะโดเมนนี้แทบเป็นไปไม่ได้)

แผน hybrid ที่ตกลงไว้: ปุ่ม → postback (machine token นิ่ง) + รับการ**พิมพ์**คำไทยเป็น fallback สำหรับ keyboard

## ความหมายที่ตั้งใจของ data sentinel (ยังไม่ได้ทำ — deferred)

ตอนนี้ `ข้าม`/`พิมพ์เอง` แค่ถูกเซฟเป็น marker แล้วเดินตาม `default` route — **ยังไม่ทำงานตามชื่อจริง** พฤติกรรมที่ตั้งใจไว้ (รอทำพร้อมงาน postback):

- **`ข้าม` (skip):** ข้ามคำถามนี้ → ส่งคำถามถัดไปเลย (ไม่เก็บคำตอบ)
- **`พิมพ์เอง` (free_text):** เปิดคีย์บอร์ดให้ผู้ใช้พิมพ์คำตอบอิสระ แล้วเก็บข้อความนั้นเป็นคำตอบ

## อ้างอิง

- issue #18 — Dispatch: postback go-back (stop leaking `__go_back__`) + typed fallback
