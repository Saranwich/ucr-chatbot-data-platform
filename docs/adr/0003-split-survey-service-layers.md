# แยก survey_service ออกเป็นชั้น ๆ — orchestrator + routing + messages + repository

`survey_service.py` โตเป็น god service (`process_survey_answer` ข้อเดียว ~150 บรรทัด)
รวมงานที่ไม่เกี่ยวกันไว้ก้อนเดียว: วงจรชีวิต session, การเดินคำถาม, go-back, multi-select,
การสร้าง URL รูป, การปิดงาน/บันทึก (`CompletedReport` + PostGIS point + ดึง location),
การประกอบข้อความ (flex/quick-reply), และ LINE I/O

ตัดสินใจ **แยกตามความรับผิดชอบ** โดยใช้ precedent ที่มีอยู่แล้ว — logic การตัดสินใจล้วน ๆ
อยู่ใน `routing.py` เป็น `compute_*` (pure, ไม่มี DB/LINE) — แล้วดึงที่เหลือออกตามแนวเดียวกัน:

- `routing.py` — การตัดสินใจล้วน ๆ (เพิ่ม `compute_start_route`)
- `survey_messages.py` — การประกอบข้อความ + ส่งเข้า LINE
- `survey_repository.py` — การเข้าถึง DB ทั้งหมด (users / sessions / ปิดงาน `CompletedReport`)
  รวม helper `build_location_point` (pure) ที่แปลง payload เป็น PostGIS POINT
- `survey_service.py` — เหลือแค่ orchestration: **decide (routing) → persist (repository) → reply (messages)**

เป็นการ refactor แบบ **ไม่เปลี่ยนพฤติกรรม** — รักษาจุด commit และลำดับการตอบกลับไว้เหมือนเดิม
safety net เลือกแบบ pragmatic: ดึงส่วน pure ออกมาเขียน unit test, ของเดิม 29 เทสต้องเขียวครบ,
ส่วน glue ที่ยังไม่มีเทส (เพราะคอลัมน์ PostGIS `Geometry` ทำให้ใช้ sqlite แทนไม่ได้) ตรวจด้วยการ
ลองจริงบน LINE จนจบ survey แล้วเช็คว่า `CompletedReport` ถูกเขียนถูกต้อง — ยังไม่ลงทุนทำ test DB
