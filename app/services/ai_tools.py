"""มือไม้ของ ai — ฟังก์ชันที่โมเดลสั่งให้แอปไปทำอะไรกับฐานได้

ทุกตัวในไฟล์นี้รับค่าที่โมเดลกรอกมาเอง เชื่อไม่ได้ว่าจะถูกชนิดหรือถูก enum
เลยห่อ pydantic ไว้ทุกตัว ผิดก็ลง log แล้วคืนค่าว่าไม่สำเร็จ ห้ามโยน exception ออกไปข้างนอก
ล้มทั้งรอบสนทนาเพราะโมเดลพิมพ์ "น้ำท่วม" แทน "flood" ไม่คุ้มกัน

ยังไม่มีใครส่งรายการนี้ให้โมเดลเลือกใช้ clients/typhoon.chat ยังไม่ได้ส่งช่อง tools ไปด้วย
ขั้นนี้ทำแต่ตัวมือไว้ให้เรียกได้จริงก่อน ต่อสายให้โมเดลหยิบเองเป็นงานขั้นถัดไป
"""

from typing import TypedDict
from uuid import UUID

from pydantic import ValidationError

from app.clients import psql
from app.schemas.report import Frequency, ProblemType, Report, Threat

PROCESS = "services.ai_tools"


class ReportDraft (TypedDict, total=False):
    """หนึ่งเรื่องตามที่โมเดลกรอกมา — ยังไม่ผ่านการตรวจ

    มีไว้บอกคนอ่าน (กับโมเดล) ว่าก้อนหนึ่งก้อนใส่อะไรได้บ้างและค่าไหนใช้ได้
    total=False เพราะทุกช่องขาดได้ ขาด = ยังไม่ได้ถาม
    ไม่ใช่ Report เพราะ Report มี session_id/status/id ที่โมเดลไม่ต้องรู้จัก
    และ TypedDict ไม่ตรวจอะไรตอนรัน คนตรวจจริงคือ Report(...) ใน save_analyse
    """

    title: str
    type: ProblemType
    threat: Threat
    frequency: Frequency
    effect: str
    is_has_image: bool
    is_has_location: bool


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
async def save_analyse (session_id: UUID, reports: list[ReportDraft]) -> list[UUID]:
    """เก็บ "หลายเรื่อง" ที่ analyzer สรุปได้จากบทสนทนาเดียวลงตาราง reports คืน id ของเรื่องที่เก็บได้

    รับทีเดียวทั้งชุดเพราะ analyzer อ่านบทสนทนาจบแล้วค่อยสรุป ตอนนั้นมันรู้ครบแล้วว่ามีกี่เรื่อง
    ให้เรียกทีละเรื่องหลายรอบแปลว่าโมเดลต้องจำเองว่าเล่าไปถึงเรื่องไหนแล้ว ซ้ำกับตกหล่นได้ทั้งคู่

    หนึ่งก้อนใน reports คือหนึ่งเรื่อง ช่องที่ใส่ได้ดูที่ ReportDraft ข้างบน ช่องไหนไม่รู้ให้ปล่อยว่าง
    ว่างแปลว่า "ยังไม่ได้ถาม" ไม่ใช่ "ไม่มี" — ห้ามเดาเติมแทนเขา
    session_id กับ status ไม่ต้องส่งมา ที่นี่เติมให้เอง ส่งมาก็ถูกทับ
    status เป็น analyzed ตั้งแต่แรกเพราะแถวนี้เป็นผลของการวิเคราะห์ ไม่ใช่ของที่รอวิเคราะห์

    annotation ของ python ไม่มีผลตอนรัน คนกันจริงคือ Report(...) ข้างล่าง
    โมเดลส่ง type="น้ำท่วม" หรือส่งอะไรที่ไม่ใช่ก้อนข้อมูลมาก็เข้ามาถึงในนี้ได้ ต้องมี try ครอบไว้เสมอ
    เรื่องไหนค่าไม่ผ่านก็ข้ามไปเรื่องเดียว ที่เหลือยังเก็บ — ล้มทั้งชุดเพราะเรื่องเดียวพังไม่คุ้มกัน
    คืนมาไม่ครบจำนวนที่ส่งไปคือมีเรื่องตก ดูสาเหตุใน log ได้
    """
    saved: list[UUID] = []
    for record in reports:
        try:
            report = Report(**{**dict(record), "session_id": session_id, "status": "analyzed"})
        except (ValidationError, TypeError, ValueError) as error:
            await psql.create_and_save_log(PROCESS, f"save_analyse ของ session {session_id} ค่าไม่ผ่าน {error}")
            continue

        await psql.save_report(report)
        saved.append(report.id)

    await psql.create_and_save_log(
        PROCESS, f"บันทึกเรื่องของ session {session_id} แล้ว {len(saved)} จาก {len(reports)} เรื่อง"
    )
    return saved


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