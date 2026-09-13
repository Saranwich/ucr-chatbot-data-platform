"""มือไม้ของ ai — ฟังก์ชันที่โมเดลสั่งให้แอปไปทำอะไรกับฐานได้

ทุกตัวในไฟล์นี้รับค่าที่โมเดลกรอกมาเอง เชื่อไม่ได้ว่าจะถูกชนิดหรือถูก enum
เลยห่อ pydantic ไว้ทุกตัว ผิดก็ลง log แล้วคืนค่าว่าไม่สำเร็จ ห้ามโยน exception ออกไปข้างนอก
ล้มทั้งรอบสนทนาเพราะโมเดลพิมพ์ "น้ำท่วม" แทน "flood" ไม่คุ้มกัน

ยังไม่มีใครส่งรายการนี้ให้โมเดลเลือกใช้ clients/typhoon.chat ยังไม่ได้ส่งช่อง tools ไปด้วย
ขั้นนี้ทำแต่ตัวมือไว้ให้เรียกได้จริงก่อน ต่อสายให้โมเดลหยิบเองเป็นงานขั้นถัดไป
"""

from uuid import UUID

from pydantic import ValidationError

from app.clients import psql
from app.schemas.report import Frequency, ProblemType, Report, Threat

PROCESS = "services.ai_tools"


## tool ของ communicator ##
async def set_finished_flag (session_id: UUID, is_finished: bool) -> bool:
    """บอกว่าชาวบ้านเล่าจบแล้วหรือยัง จบแล้วตัวกวาดจะปิดให้เลยไม่ต้องรอเงียบครบเวลา

    เป็น true/false ไม่ใช่ปักทางเดียว เพราะโมเดลอ่านผิดได้ — เขาพูดคำที่ฟังเหมือนจะจบ
    (ขอบคุณครับ / โอเคครับ) แล้วพิมพ์เรื่องใหม่ต่อ ต้องมีทางถอนคืน
    แต่ห้ามพึ่งการถอนของโมเดลทางเดียว เพราะมันถอนได้ตอนถูกเรียกรอบถัดไปเท่านั้น
    ตัวกวาดอาจมาถึงก่อน — chatbot เลยถอนธงให้ทุกครั้งที่มีข้อความใหม่เข้ามาอีกชั้น

    ไม่ปิด session ให้ที่นี่ เพราะคนเรียกคือ communicator ที่ยังจะตอบไลน์ต่อ
    ปิดทิ้งกลางทางแล้วคำตอบที่เพิ่งเขียนจะไม่มีที่ลง
    """
    ok = await psql.set_session_finished(session_id, is_finished)
    if not ok:
        await psql.create_and_save_log(PROCESS, f"set_finished_flag ไม่เจอ session {session_id} ในฐาน")
    return ok


## tool ของ analyzer ##
async def save_analyse (
    session_id: UUID,
    title: str | None = None,
    type: ProblemType | None = None,
    threat: Threat | None = None,
    frequency: Frequency | None = None,
    effect: str | None = None,
    is_has_image: bool | None = None,
    is_has_location: bool | None = None,
) -> UUID | None:
    """เก็บ "หนึ่งเรื่อง" ที่ analyzer สรุปได้ลงตาราง reports คืน id ของเรื่องนั้น พังก็คืน None

    เรียกได้หลายครั้งต่อหนึ่ง session เพราะบทสนทนาเดียวชาวบ้านเล่าได้หลายเรื่อง
    ช่องไหนไม่รู้ให้ปล่อยว่าง ว่างแปลว่า "ยังไม่ได้ถาม" ไม่ใช่ "ไม่มี" — ห้ามเดาเติมแทนเขา
    ชนิดของ type/threat/frequency บอกค่าที่ใส่ได้ไว้ให้คนอ่านเห็น แต่ไม่ได้กันอะไรตอนรัน
    annotation ของ python ไม่มีผลตอนรัน คนกันจริงคือ Report(...) ข้างล่าง
    โมเดลส่ง "น้ำท่วม" มาก็เข้ามาถึงในนี้ได้ ต้องมี try ครอบไว้เสมอ
    status เขียน analyzed ตั้งแต่แรกเพราะแถวนี้เป็นผลของการวิเคราะห์ ไม่ใช่ของที่รอวิเคราะห์
    """
    try:
        report = Report(
            session_id=session_id,
            status="analyzed",
            title=title,
            type=type,
            threat=threat,
            frequency=frequency,
            effect=effect,
            is_has_image=is_has_image,
            is_has_location=is_has_location,
        )
    except ValidationError as error:
        await psql.create_and_save_log(PROCESS, f"save_analyse ของ session {session_id} ค่าไม่ผ่าน {error}")
        return None

    await psql.save_report(report)
    await psql.create_and_save_log(PROCESS, f"บันทึกเรื่อง {report.id} ของ session {session_id} แล้ว")
    return report.id


## tool ของ resource analyzer ##
async def submit_resource_detail (image_id: UUID, desc: str) -> bool:
    """เติมคำบรรยายให้รูปที่อ่านแล้วหนึ่งใบ

    เขียนทับได้ อ่านรูปใหม่รอบสองก็ทับของเดิมไป
    ไม่สร้างแถวใหม่ให้ ถ้าไม่เจอ id นี้คือเรียกผิดตัว ไม่ใช่รูปที่ยังไม่ได้เก็บ
    """
    ok = await psql.set_image_desc(image_id, desc)
    if not ok:
        await psql.create_and_save_log(PROCESS, f"submit_resource_detail ไม่เจอรูป {image_id} ในฐาน")
    return ok