"""มือไม้ของ ai — ฟังก์ชันที่โมเดลสั่งให้แอปไปทำอะไรกับฐานได้

ทุกตัวในไฟล์นี้รับค่าที่โมเดลกรอกมาเอง เชื่อไม่ได้ว่าจะถูกชนิดหรือถูก enum
เลยห่อ pydantic ไว้ทุกตัว ผิดก็ลง log แล้วคืนค่าว่าไม่สำเร็จ ห้ามโยน exception ออกไปข้างนอก
ล้มทั้งรอบสนทนาเพราะโมเดลพิมพ์ "น้ำท่วม" แทน "flood" ไม่คุ้มกัน

ตัวที่โมเดลหยิบเองได้ต้องมีสองอย่างคู่กัน — schema ไว้ยื่นให้มันเลือก กับชื่อใน allowlist ข้างล่าง
ไม่ได้อยู่ใน allowlist คือเรียกไม่ได้ ต่อให้มันเดาชื่อฟังก์ชันในไฟล์นี้ถูกก็ตาม
"""

import json
from typing import Literal, NamedTuple, TypedDict, get_args
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
    location_ids: list[str] | None


class QuickReply (TypedDict):
    """ปุ่มที่ communicator ขอให้ LINE แสดง — ยังต้องตรวจค่าจากโมเดลก่อนใช้"""

    type: Literal["message", "location"]
    label: str
    text: str | None


## tool ของ communicator ##
QUICK_REPLY_MAX_ITEMS = 5
QUICK_REPLY_MAX_LABEL_UNITS = 20
QUICK_REPLY_MAX_TEXT_UNITS = 300

SET_FINISHED_FLAG_TOOL = {
    "type": "function",
    "function": {
        "name": "set_finished_flag",
        "description": (
            "รายงานว่าชาวบ้านจบบทสนทนารอบนี้แล้วหรือยัง ต้องเรียกหนึ่งครั้งทุกตา "
            "ส่ง true เมื่อเขาบอกชัดว่าไม่มีเรื่องจะเล่าต่อ ต้องการหยุด หรือกล่าวลา นอกนั้นส่ง false"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "is_finished": {
                    "type": "boolean",
                    "description": "true=ชาวบ้านต้องการจบรอบนี้, false=ยังไม่ได้ยืนยันว่าจบ",
                },
                "quick_replies": {
                    "type": "array",
                    "minItems": 0,
                    "maxItems": QUICK_REPLY_MAX_ITEMS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["message", "location"],
                                "description": "message=ส่งข้อความกลับ, location=เปิดหน้าจอแชร์พิกัด",
                            },
                            "label": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": QUICK_REPLY_MAX_LABEL_UNITS,
                                "description": "ข้อความสั้นที่แสดงบนปุ่ม ต้องยาวไม่เกิน 20 ตัวอักษรตามข้อกำหนด LINE",
                            },
                            "text": {
                                "type": ["string", "null"],
                                "maxLength": QUICK_REPLY_MAX_TEXT_UNITS,
                                "description": "ข้อความที่จะส่งเมื่อ type=message; ต้องเป็น null เมื่อ type=location",
                            },
                        },
                        "required": ["type", "label", "text"],
                        "additionalProperties": False,
                    },
                    "description": (
                        "ปุ่มใต้ข้อความ: message ใช้ตอบตัวเลือกสั้น ๆ, location ใช้ขอให้แชร์พิกัด "
                        "ถ้าไม่ควรมีปุ่มให้ส่ง []"
                    ),
                }
            },
            "required": ["is_finished", "quick_replies"],
        },
    },
}

SET_FINISHED_PROTOCOL = """\
# กติกาการปิดบทสนทนา (ระบบกำหนด)
- ป้าย [got location from user: location_id=...] แปลว่าเขาแชร์พิกัดมา รหัสเป็นของระบบ ห้ามพูดรหัสกลับไป
- ต้องเรียก set_finished_flag หนึ่งครั้งทุกตาก่อนตอบ
- ส่ง is_finished=true เมื่อชาวบ้านยืนยันว่าไม่มีเรื่องจะเล่าต่อ ต้องการหยุด หรือกล่าวลาชัดเจน
- ส่ง is_finished=false เมื่อยังไม่ได้ยืนยันว่าจบ รวมถึงคำสั้น ๆ อย่างขอบคุณหรือโอเคที่ยังอาจคุยต่อ
- ใน set_finished_flag ให้ส่ง quick_replies เป็นรายการ object ที่มี type, label และ text ถ้าไม่ควรมีปุ่มให้ส่ง []
- ปุ่มตอบข้อความใช้ {"type":"message","label":"บางครั้ง","text":"บางครั้ง"} ให้ 2-5 ตัวเลือกสั้นชัดเจน
- ปุ่มขอพิกัดใช้ {"type":"location","label":"แชร์พิกัด","text":null} ใช้ปุ่มเดียวได้ และใช้เมื่อกำลังขอจุดเกิดเหตุเท่านั้น
- label ทุกปุ่มยาวไม่เกิน 20 ตัวอักษรโดยเด็ดขาด ห้ามใส่คำถามหรือประโยคอธิบายในปุ่ม
- คำถามที่ควรให้พิมพ์เล่าเองหรือขอรูป ไม่ต้องสร้าง quick reply
- ถ้าได้รับผลของ tool แล้ว ให้ตอบชาวบ้านตามปกติโดยไม่เรียก tool ซ้ำ
"""


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


COMMUNICATOR_TOOLS = {
    "set_finished_flag": set_finished_flag,
}


def _utf16_units(value: str) -> int:
    """LINE นับความยาว label เป็น UTF-16 code units ไม่ใช่จำนวนตัวอักษรของ Python"""
    return len(value.encode("utf-16-le")) // 2


async def extract_quick_replies(tool_calls: list) -> list[QuickReply]:
    """อ่านคำขอ quick reply จากโมเดล คืนข้อความที่ส่งให้ LINE ได้จริง

    Quick reply เป็นข้อมูลประกอบคำตอบ ไม่ใช่ side effect จึงปั้นก่อนส่ง LINE ส่วน is_finished
    ใน tool ก้อนเดียวกันค่อยถูก execute หลังส่ง รายการผิดถูกตัดเฉพาะปุ่ม คำตอบหลักยังส่งต่อได้
    """
    calls = [
        call for call in (tool_calls or [])
        if isinstance(call, dict)
        and isinstance(call.get("function"), dict)
        and call["function"].get("name") == "set_finished_flag"
    ]
    if not calls:
        return []
    if len(calls) > 1:
        await psql.create_and_save_log(PROCESS, "communicator เรียก set_finished_flag ซ้ำ ตัด quick reply รอบนี้ทิ้ง")
        return []

    raw = calls[0]["function"].get("arguments")
    if isinstance(raw, str):
        try:
            arguments = json.loads(raw)
        except (ValueError, TypeError) as error:
            await psql.create_and_save_log(PROCESS, f"set_finished_flag ส่ง json ที่อ่านไม่ได้ {error}")
            return []
    else:
        arguments = raw

    if not isinstance(arguments, dict) or not isinstance(arguments.get("quick_replies"), list):
        await psql.create_and_save_log(PROCESS, "set_finished_flag ต้องส่ง quick_replies เป็นลิสต์")
        return []

    quick_replies: list[QuickReply] = []
    for raw_item in arguments["quick_replies"]:
        if not isinstance(raw_item, dict):
            continue
        action_type = raw_item.get("type")
        raw_label = raw_item.get("label")
        if not isinstance(raw_label, str):
            continue
        label = raw_label.strip()
        if not label or "\n" in label or _utf16_units(label) > QUICK_REPLY_MAX_LABEL_UNITS:
            continue

        if action_type == "message":
            raw_text = raw_item.get("text")
            if not isinstance(raw_text, str):
                continue
            reply_text = raw_text.strip()
            if not reply_text or _utf16_units(reply_text) > QUICK_REPLY_MAX_TEXT_UNITS:
                continue
            item: QuickReply = {"type": "message", "label": label, "text": reply_text}
        elif action_type == "location":
            if raw_item.get("text") is not None:
                continue
            item = {"type": "location", "label": label, "text": None}
        else:
            continue

        if item not in quick_replies:
            quick_replies.append(item)
        if len(quick_replies) == QUICK_REPLY_MAX_ITEMS:
            break

    # ตัวเลือกข้อความปุ่มเดียวไม่มีประโยชน์ แต่ location ปุ่มเดียวคือคำสั่งเปิดหน้าแชร์พิกัดที่สมบูรณ์
    if len(quick_replies) == 1 and quick_replies[0]["type"] != "location":
        # [] หมายถึงตั้งใจไม่แสดงปุ่ม ไม่ต้องสร้าง log รบกวน
        await psql.create_and_save_log(PROCESS, "quick_replies แบบข้อความเหลือปุ่มเดียว ตัดทิ้ง")
        return []
    return quick_replies


async def run_communicator_tool_calls (session_id: UUID, tool_calls: list) -> int:
    """ทำตาม tool call ของ communicator หลังส่งคำตอบ LINE แล้ว คืนจำนวนคำสั่งที่ทำสำเร็จ

    จงใจทำหลังตอบผู้ใช้ ไม่ทำระหว่างสองรอบของ tool protocol เพราะถ้าปัก finished เร็วไป
    runtime อาจปิด session ขณะที่ communicator ยังสร้างคำตอบรอบสุดท้ายอยู่
    """
    executed = 0

    for call in tool_calls or []:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง communicator tool มาในรูปที่อ่านไม่ออก")
            continue

        name = function.get("name")
        handler = COMMUNICATOR_TOOLS.get(name)
        if handler is None:
            await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง communicator tool ชื่อ {name} ที่ไม่มีสิทธิ์เรียก")
            continue

        raw = function.get("arguments")
        if isinstance(raw, str):
            try:
                arguments = json.loads(raw)
            except (ValueError, TypeError) as error:
                await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง {name} ด้วย json ที่อ่านไม่ได้ {error}")
                continue
        else:
            arguments = raw

        if not isinstance(arguments, dict) or type(arguments.get("is_finished")) is not bool:
            await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง {name} ด้วย is_finished ที่ไม่ใช่ boolean")
            continue

        arguments.pop("quick_replies", None)  # ใช้ประกอบข้อความ LINE ไปแล้ว ไม่ใช่อาร์กิวเมนต์ของ handler
        arguments.pop("session_id", None)
        try:
            ok = await handler(session_id, **arguments)
        except Exception as error:
            await psql.create_and_save_log(PROCESS, f"session {session_id} เรียก {name} แล้วพัง {type(error).__name__} {error}")
            continue

        if ok:
            executed += 1

    return executed


## tool ของ analyzer ##
class SaveOutcome (NamedTuple):
    """ผลของ save_analyse หนึ่งครั้ง — บอกทั้งของที่ถูกสั่งและของที่ลงฐานได้จริง

    คืนแต่ลิสต์ id ไม่พอ เพราะลิสต์ว่างมีสองความหมายที่ต้องทำคนละอย่าง
    ถูกสั่งมา 0 เรื่อง = อ่านแล้วไม่มีเรื่อง จบได้
    ถูกสั่งมา 3 เรื่องแล้วเก็บไม่ได้สักเรื่อง = โมเดลกรอกผิด ต้องให้มันลองใหม่
    """

    requested: int
    saved: list[UUID]


async def save_analyse (session_id: UUID, reports: list[ReportDraft]) -> SaveOutcome:
    """เก็บ "หลายเรื่อง" ที่ analyzer สรุปได้จากบทสนทนาเดียวลงตาราง reports คืน id ของเรื่องที่เก็บได้

    รับทีเดียวทั้งชุดเพราะ analyzer อ่านบทสนทนาจบแล้วค่อยสรุป ตอนนั้นมันรู้ครบแล้วว่ามีกี่เรื่อง
    ให้เรียกทีละเรื่องหลายรอบแปลว่าโมเดลต้องจำเองว่าเล่าไปถึงเรื่องไหนแล้ว ซ้ำกับตกหล่นได้ทั้งคู่

    หนึ่งก้อนใน reports คือหนึ่งเรื่อง ช่องที่ใส่ได้ดูที่ ReportDraft ข้างบน ช่องไหนไม่รู้ให้ปล่อยว่าง
    ว่างแปลว่า "ยังไม่ได้ถาม" ไม่ใช่ "ไม่มี" — ห้ามเดาเติมแทนเขา
    location_ids เป็นรหัสจากป้ายในบทสนทนา โค้ดตรวจว่าอยู่ใน session นี้และไม่ชี้ข้าม report
    session_id, report_id, lat, lon กับ status ไม่ต้องส่งมา ที่นี่เติมหรือดึงของจริงจากฐานเอง
    status เป็น analyzed ตั้งแต่แรกเพราะแถวนี้เป็นผลของการวิเคราะห์ ไม่ใช่ของที่รอวิเคราะห์

    annotation ของ python ไม่มีผลตอนรัน คนกันจริงคือ Report(...) ข้างล่าง
    โมเดลส่ง type="น้ำท่วม" หรือส่งอะไรที่ไม่ใช่ก้อนข้อมูลมาก็เข้ามาถึงในนี้ได้ ต้องมี try ครอบไว้เสมอ
    เรื่องไหนค่าไม่ผ่านก็ข้ามไปเรื่องเดียว ที่เหลือยังเก็บ — ล้มทั้งชุดเพราะเรื่องเดียวพังไม่คุ้มกัน
    คืนมาไม่ครบจำนวนที่ส่งไปคือมีเรื่องตก ดูสาเหตุใน log ได้
    """
    saved: list[UUID] = []
    locations_used_in_this_call: set[UUID] = set()

    for record in reports:
        try:
            values = dict(record)
        except (ValidationError, TypeError, ValueError) as error:
            await psql.create_and_save_log(PROCESS, f"save_analyse ของ session {session_id} ค่าไม่ผ่าน {error}")
            continue

        raw_location_ids = values.pop("location_ids", [])
        if raw_location_ids is None:
            raw_location_ids = []
        if not isinstance(raw_location_ids, list):
            await psql.create_and_save_log(
                PROCESS, f"save_analyse ของ session {session_id} location_ids ต้องเป็นลิสต์"
            )
            continue

        try:
            location_ids: list[UUID] = []
            for value in raw_location_ids:
                if not isinstance(value, str):
                    raise ValueError("location_id ต้องเป็นข้อความ UUID")
                location_ids.append(UUID(value))
        except (ValueError, TypeError) as error:
            await psql.create_and_save_log(
                PROCESS, f"save_analyse ของ session {session_id} location_id อ่านไม่ได้ {error}"
            )
            continue

        location_id_set = set(location_ids)
        if len(location_id_set) != len(location_ids):
            await psql.create_and_save_log(
                PROCESS, f"save_analyse ของ session {session_id} ใส่ location_id ซ้ำใน report เดียว"
            )
            continue
        if location_id_set & locations_used_in_this_call:
            await psql.create_and_save_log(
                PROCESS, f"save_analyse ของ session {session_id} เอา location เดียวไปผูกหลาย report"
            )
            continue

        # true ต้องมีพิกัดจริงรองรับ ส่วน false/null ยังเก็บความหมายเดิมเมื่อไม่มี location ให้ผูก
        if location_ids:
            values["is_has_location"] = True
        elif values.get("is_has_location") is True:
            await psql.create_and_save_log(
                PROCESS, f"save_analyse ของ session {session_id} อ้างว่ามีพิกัดแต่ไม่ส่ง location_id"
            )
            continue

        try:
            report = Report(**{**values, "session_id": session_id, "status": "analyzed"})
        except (ValidationError, TypeError, ValueError) as error:
            await psql.create_and_save_log(PROCESS, f"save_analyse ของ session {session_id} ค่าไม่ผ่าน {error}")
            continue

        if location_ids:
            saved_report_id = await psql.save_report_with_locations(report, location_ids)
            if saved_report_id is None:
                await psql.create_and_save_log(
                    PROCESS,
                    f"save_analyse ของ session {session_id} อ้าง location ที่ไม่มี พิกัดไม่ครบ อยู่คนละ session หรือชี้คนละ report",
                )
                continue
        else:
            await psql.save_report(report)
            saved_report_id = report.id

        saved.append(saved_report_id)
        locations_used_in_this_call.update(location_id_set)

    await psql.create_and_save_log(
        PROCESS, f"บันทึกเรื่องของ session {session_id} แล้ว {len(saved)} จาก {len(reports)} เรื่อง"
    )
    return SaveOutcome(requested=len(reports), saved=saved)


def _nullable_enum (literal, description: str) -> dict:
    """ปั้นช่องแบบ "เลือกหนึ่งค่าจากลิสต์ หรือไม่รู้ก็ null" ให้โมเดลอ่าน

    ดึงค่าที่ใช้ได้จาก Literal ใน schemas/report.py ตรง ๆ ไม่พิมพ์ซ้ำไว้ที่นี่
    พิมพ์ซ้ำเมื่อไหร่ วันที่มีคนเพิ่มชนิดปัญหาใหม่ใน schema แล้ว schema ฝั่งโมเดลจะไม่รู้เรื่องด้วย
    ต้องใส่ null ทั้งใน type และใน enum เพราะ enum เป็นรายการค่าที่ผ่านทั้งหมด ไม่ใช่แค่ตอนที่มีค่า
    """
    return {
        "type": ["string", "null"],
        "enum": [*get_args(literal), None],
        "description": description,
    }


SAVE_ANALYSE_TOOL = {
    "type": "function",
    "function": {
        "name": "save_analyse",
        "description": (
            "บันทึกเรื่องที่สรุปได้จากบทสนทนาลงฐานข้อมูล ต้องเรียกทุกครั้งที่อ่านบทสนทนาจบ เรียกครั้งเดียว "
            "ใส่ทุกเรื่องที่เจอลงในลิสต์ reports เรื่องละหนึ่งก้อน "
            "บทสนทนาที่ไม่มีเรื่องสภาพพื้นที่เลย ก็ยังต้องเรียก โดยส่ง reports เป็นลิสต์ว่าง "
            "การไม่เรียก tool นี้ถือว่าทำงานไม่สำเร็จ"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reports": {
                    "type": "array",
                    "description": "เรื่องทั้งหมดที่สรุปได้ เรื่องเดียวกันจุดเดียวกันรวมเป็นก้อนเดียว คนละจุดแยกก้อน ไม่มีเรื่องเลยให้ส่งลิสต์ว่าง",
                    "items": {
                        "type": "object",
                        "description": "หนึ่งเรื่อง ช่องไหนเขาไม่ได้บอกให้ใส่ null ห้ามเดาแทน",
                        "properties": {
                            "title": {
                                "type": ["string", "null"],
                                "description": "หัวเรื่องสั้น ๆ ด้วยคำของเขาเอง เช่น น้ำท่วมขังหน้าปากซอย",
                            },
                            "type": _nullable_enum(
                                ProblemType,
                                "ชนิดของเรื่อง flood=น้ำท่วม heat=ความร้อน light=ไฟทาง other=อื่น ๆ",
                            ),
                            "threat": _nullable_enum(
                                Threat,
                                "ระดับความน่ากังวลเท่าที่ประเมินจากที่เขาเล่า not_relate=ไม่เกี่ยว low=น้อย mid=กลาง high=มาก",
                            ),
                            "frequency": _nullable_enum(
                                Frequency,
                                "เกิดบ่อยแค่ไหน always=ตลอด usually=ประจำ often=บ่อย subtle=นาน ๆ ที "
                                "first_time=ครั้งแรก dont_know=เขาบอกว่าไม่รู้",
                            ),
                            "effect": {
                                "type": ["string", "null"],
                                "description": 'กระทบเขาหรือคนแถวนั้นยังไง เล่าด้วยคำของเขา ถามแล้วเขาบอกว่าไม่กระทบให้ใส่ "-"',
                            },
                            "is_has_image": {
                                "type": ["boolean", "null"],
                                "description": "เรื่องนี้มีรูปที่เขาส่งมาไหม true=มี false=ถามแล้วไม่มี null=ยังไม่ได้คุยเรื่องรูป",
                            },
                            "is_has_location": {
                                "type": ["boolean", "null"],
                                "description": "true เมื่อ location_ids มีพิกัดที่ผูกกับเรื่องนี้ได้ false=ถามแล้วไม่มี null=ยังไม่รู้",
                            },
                            "location_ids": {
                                "type": ["array", "null"],
                                "items": {"type": "string", "format": "uuid"},
                                "uniqueItems": True,
                                "description": (
                                    "รหัสจากป้าย [got location from user: location_id=...] ที่เป็นของเรื่องนี้แน่ ๆ "
                                    "ใช้ได้เฉพาะรหัสที่มีในบทสนทนา ไม่มีหรือจับคู่ไม่ได้ให้ส่ง []"
                                ),
                            },
                        },
                        "required": ["location_ids"],
                    },
                }
            },
            "required": ["reports"],
        },
    },
}
"""หน้าตาของ save_analyse ในสายตาโมเดล — ต้องเดินตาม Report/save_analyse เสมอ

ไม่มี session_id ในนี้ตั้งใจ โมเดลไม่ได้ถือ id ของอะไรทั้งนั้น run_tool_calls เติมให้เองตอนเรียกจริง
ให้มันกรอกมาเมื่อไหร่แปลว่าเราปล่อยให้มันเขียนทับ session ของคนอื่นได้ด้วยการเดา id
"""

SAVE_ANALYSE_PROTOCOL = """\
# กติกาการตอบ (ระบบกำหนด ห้ามละเว้น)
- ตอบด้วยการเรียก tool save_analyse หนึ่งครั้งเสมอ ทุกครั้งที่อ่านบทสนทนาจบ ไม่มีข้อยกเว้น
- มีกี่เรื่องใส่ให้ครบใน reports ของการเรียกครั้งนั้น
- ไม่มีเรื่องสภาพพื้นที่เลย ก็ยังต้องเรียก โดยส่ง {"reports": []} ห้ามสร้าง report เปล่ามากลบ
- ห้ามตอบเป็นข้อความเปล่าแทนการเรียก tool ระบบไม่อ่านข้อความ รับเฉพาะ tool call
- ป้าย [got location from user: location_id=...] มีรหัสพิกัดภายใน ให้ใส่รหัสที่ตรงกับแต่ละเรื่องใน location_ids
- ใช้ได้เฉพาะ location_id ที่ปรากฏในบทสนทนาและผูกกับเรื่องนั้นชัดเจน จับคู่ไม่ได้ให้ส่ง [] ห้ามสร้างรหัสเอง
- ช่องที่ชาวบ้านไม่ได้บอกให้ใส่ null ห้ามเดา และห้ามส่ง session_id, report_id, lat, lon หรือ status
- ไม่เรียก tool ถือว่าทำงานไม่สำเร็จ ระบบจะสั่งให้อ่านใหม่ทั้งรอบ
"""
"""กติกาที่ต้องมีเสมอ ไม่ว่า prompt ที่ใช้จริงจะมาจากไหน

prompt ของ analyzer มาจากแถว active ใน db ซึ่งอาจเป็นของเก่าที่เขียนไว้ก่อนมี tool calling
ปล่อยให้ prompt เป็นคนบอกกติกานี้ทางเดียว วันที่ db ถือ prompt เก่าอยู่ ระบบจะวนลองสามครั้งแล้วล้มทุก session
โค้ดเลยต้องเป็นคนเติมเอง ต่อท้าย prompt ที่โหลดมา ไม่ใช่แทนที่ — db ยังคุมน้ำเสียงกับวิธีแยกเรื่องได้ตามเดิม
ซ้ำกับที่เขียนไว้ใน ANALYZER_PROMPT โดยตั้งใจ ของใน default_value ปรับได้ ของตัวนี้ปรับไม่ได้
"""


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

ANALYZER_TOOLS = {
    "save_analyse": save_analyse,
}
"""ชื่อ tool ที่ analyzer เรียกได้จริง — ชื่อที่ไม่อยู่ในนี้คือเรียกไม่ได้

ตัวที่อยู่ในนี้ต้องรับ session_id เป็นตัวแรก และคืน SaveOutcome บอกว่าถูกสั่งมากี่เรื่องเก็บได้กี่เรื่อง
พังระหว่างทางให้โยน exception ออกมา run_tool_calls นับเป็นรอบที่ล้มให้เอง
"""


class ToolRunOutcome (NamedTuple):
    """ผลรวมของการทำตามคำสั่งทั้งชุดในหนึ่งตาของโมเดล

    มีสี่ตัวเลขเพราะคนเรียกต้องตอบคำถามเดียวให้ได้ — "รอบนี้ถือว่าวิเคราะห์เสร็จหรือต้องให้มันลองใหม่"
    นับแต่ saved ตอบไม่ได้ เพราะ 0 เกิดได้ทั้งจาก "ไม่มีเรื่องจะเก็บ" กับ "เก็บไม่ลง"
    อันแรกคือจบงาน อันหลังคือยังไม่ได้เริ่ม
    """

    executed: int    # tool call ที่เดินจนจบโดยไม่มี exception
    failed: int      # tool call ที่เรียกไม่ได้หรือพังกลางทาง
    requested: int   # เรื่องที่โมเดลสั่งให้เก็บ รวมทุก tool call
    saved: int       # เรื่องที่ลงฐานได้จริง

    @property
    def is_success (self) -> bool:
        """รอบนี้ถือว่าวิเคราะห์เสร็จแล้วไหม — เสร็จแล้วปิด session ไม่เสร็จก็ให้โมเดลอ่านใหม่ทั้งรอบ

        เสร็จคือ "เก็บได้ครบตามที่สั่งมา" ไม่ใช่ "เก็บได้บ้าง"
        สั่งมา 2 เก็บได้ 1 แล้วปิดไปเลย เรื่องที่ตกจะไม่มีใครกลับมาเก็บอีกตลอดกาล
        ลองใหม่แล้วได้เรื่องที่เก็บไปแล้วซ้ำ ยอมได้ ข้อมูลซ้ำมีคนมานั่งรวมทีหลังได้ ข้อมูลตกไม่มี

        ไม่มี tool ไหนเดินจนจบ = ยังไม่ได้ทำอะไรเลย ต้องลองใหม่
        มีตัวไหนพังปนมา = ทำได้ไม่ครบ ต้องลองใหม่ ถึงตัวอื่นจะผ่าน
        เดินจนจบครบแต่เก็บได้ไม่ครบที่สั่ง = โมเดลกรอกค่าผิดบางเรื่อง ต้องให้เขียนใหม่ทั้งชุด
        ถูกสั่งมา 0 เรื่องพอดี = อ่านแล้วไม่มีเรื่องจริง ๆ นับว่าครบ จบได้
        """
        if not self.executed or self.failed:
            return False
        return self.saved == self.requested


async def run_tool_calls (session_id: UUID, tool_calls: list) -> ToolRunOutcome:
    """ทำตามที่โมเดลสั่งมาทีละรายการ คืนผลรวมว่าทำได้แค่ไหน

    คนเรียกคือตัวปิด session ที่รันอยู่หลังบ้าน ไม่มีใครนั่งดู เลยต้องไม่มีทางโยน exception ออกไป
    รายการไหนอ่านไม่ออกก็ log แล้วนับเป็นรายการที่ล้ม ที่เหลือยังทำต่อ

    ตัวเลขที่คืนคือของที่เกิดขึ้นจริง ไม่ใช่คำพูดของโมเดล
    มันสั่งมาสามเรื่องแล้วผ่านสองก็คืน saved=2 requested=3
    """
    executed = failed = requested = saved = 0

    for call in tool_calls or []:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง tool มาในรูปที่อ่านไม่ออก {call}")
            failed += 1
            continue

        name = function.get("name")
        handler = ANALYZER_TOOLS.get(name)
        if handler is None:
            await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง tool ชื่อ {name} ที่ไม่มีสิทธิ์เรียก ข้ามไป")
            failed += 1
            continue

        # ส่วนใหญ่ arguments มาเป็นสตริง json ตามมาตรฐาน openai แต่บาง provider คืนเป็นก้อนมาเลย รับทั้งสองแบบ
        raw = function.get("arguments")
        if isinstance(raw, str):
            try:
                arguments = json.loads(raw)
            except (ValueError, TypeError) as error:
                await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง {name} มาด้วย arguments ที่ไม่ใช่ json {error}")
                failed += 1
                continue
        else:
            arguments = raw

        if not isinstance(arguments, dict):
            await psql.create_and_save_log(PROCESS, f"session {session_id} สั่ง {name} มาด้วย arguments ที่ไม่ใช่ก้อนข้อมูล {type(arguments).__name__}")
            failed += 1
            continue

        # id ของ session มาจากคนที่สั่งปิด ไม่ใช่จากโมเดล มันกรอกมาก็ทิ้ง ไม่ต้องบอกมันด้วยซ้ำ
        arguments.pop("session_id", None)

        # ฐานล่มมาลงตรงนี้เหมือนกัน นับเป็นรอบที่ล้มเพื่อให้คนเรียกพาไปลองใหม่ ไม่ใช่ปิดทิ้ง
        try:
            outcome = await handler(session_id, **arguments)
        except Exception as error:
            await psql.create_and_save_log(PROCESS, f"session {session_id} เรียก {name} แล้วพัง {type(error).__name__} {error}")
            failed += 1
            continue

        executed += 1
        requested += outcome.requested
        saved += len(outcome.saved)

    return ToolRunOutcome(executed=executed, failed=failed, requested=requested, saved=saved)
