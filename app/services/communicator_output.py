"""สัญญาคำตอบของ communicator — ข้อความที่ยื่นให้โมเดล กับตัวแกะที่รับของกลับมา

สองครึ่งนี้อยู่ไฟล์เดียวกันโดยตั้งใจ ถ้าแยกกันแล้วแก้ข้างเดียวเมื่อไหร่ ตัวแกะจะรอรับของที่ไม่มีใครสั่ง
communicator ไม่ได้รอผลจากข้างนอกอะไรเลย มันแค่ต้องคายสามอย่างพร้อมกัน — ข้อความ ธงจบ ปุ่ม
งานแบบนี้คือ structured output ไม่ใช่ tool calling การยิงรอบสองเพื่อ "รับผล" ที่เราปั้นเองจึงหายไปทั้งเส้น

หลักที่ยึดตลอดไฟล์นี้: ยอมเสียธงกับปุ่ม ดีกว่าเสียข้อความ
ธงหายแค่ทำให้ปิดบทสนทนาช้าลงสิบนาที ปุ่มหายแค่ต้องพิมพ์เอง แต่ข้อความหายคือชาวบ้านโดนเงียบใส่
ที่วัดมา typhoon คาย JSON ถูกรูป 70/72 และสองครั้งที่เหลือคายร้อยแก้วที่ใช้ตอบได้เลย
ชั้นสำรองข้างล่างจึงไม่ใช่ของประดับ มันคือส่วนที่ทำให้ 97% กลายเป็น 100%
"""

import json
import re

from app.clients import psql
from app.schemas.communicator import CommunicatorReply, QuickReplyItem

PROCESS = "services.communicator_output"

QUICK_REPLY_MAX_ITEMS = 5
QUICK_REPLY_MAX_LABEL_UNITS = 20
QUICK_REPLY_MAX_TEXT_UNITS = 300

COMMUNICATOR_OUTPUT_CONTRACT = """\
# ป้ายจากระบบ
- ป้าย [got image from user: image_id=...] แปลว่าเขาส่งรูป รหัสเป็นของระบบ คุณมองเนื้อหารูปไม่เห็น ห้ามพูดรหัสกลับไป
- ป้าย [image download failed] แปลว่าได้รับรูปแต่ระบบโหลดไฟล์ไม่ได้ จึงไม่มี image_id ที่ใช้อ้างอิง ห้ามอ้างว่าเห็นรูป
- ป้าย [got location from user: location_id=...] แปลว่าเขาแชร์พิกัดมา รหัสเป็นของระบบ ห้ามพูดรหัสกลับไป
- ตาที่ชาวบ้านส่งมาแต่ป้าย ไม่มีคำพิมพ์มาด้วย ก็ตอบเป็น JSON เหมือนตาอื่นทุกประการ

# รูปแบบคำตอบ
ตอบกลับเป็น JSON ก้อนเดียวเท่านั้น ห้ามมีข้อความอื่นนอกวงเล็บปีกกา ห้ามครอบด้วยรั้วโค้ด
{"reply_text": "...", "is_finished": false, "quick_replies": []}

- reply_text: ข้อความที่ชาวบ้านจะเห็น ต้องมีทุกตาไม่มีข้อยกเว้น ขึ้นบรรทัดใหม่ใช้ \\n
- is_finished: บอกว่าเขาเล่าจบรอบนี้แล้วหรือยัง
  - true เมื่อเขาบอกว่าไม่มีเรื่องจะเล่าต่อ ขอหยุด ไม่ว่าง หรือกล่าวลา
  - false ทุกกรณีที่เหลือ รวมถึงตาที่เขาตอบสั้นห้วนอย่าง "ok" "ครับ" "555" "อือ" "โอเค" \
คำรับสั้นแบบนี้ไม่ใช่การบอกลา เขายังอยู่ ให้ถามต่อสั้น ๆ หนึ่งคำถาม
  - ไม่แน่ใจให้ใส่ false ระบบปิดบทสนทนาเองอยู่แล้วเมื่อเงียบครบสิบนาที \
แต่การปักว่าจบทั้งที่เขายังไม่จบ ทำให้บทสนทนาถูกตัดกลางคันและเขาต้องเล่าใหม่ตั้งแต่ต้น
- quick_replies: ปุ่มใต้ข้อความ ใส่ 0 ปุ่ม หรือ 2-5 ปุ่ม ไม่มีปุ่มก็ส่งลิสต์ว่าง
  - ปุ่มข้อความ {"type":"message","label":"บางครั้ง","text":"บางครั้ง"}
  - ปุ่มขอพิกัด {"type":"location","label":"แชร์พิกัด","text":null} ใส่ปุ่มเดียวได้ และ text ต้องเป็น null
  - label ยาวไม่เกิน 20 ตัวอักษรโดยเด็ดขาด ห้ามใส่คำถามหรือประโยคอธิบายในปุ่ม
"""

# ยื่นไปทุกครั้งแม้รู้ว่า typhoon ทิ้งช่องนี้เงียบ ๆ (วัดแล้ว ส่ง type มั่วไปมันยังไม่ฟ้อง)
# google บังคับตามจริง วันที่สลับไปใช้ จุดที่โมเดลหลุดเป็นร้อยแก้วจะหายไปเชิงโครงสร้าง ไม่ใช่เชิงขอร้อง
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "communicator_reply",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reply_text": {"type": "string"},
                "is_finished": {"type": "boolean"},
                "quick_replies": {
                    "type": "array",
                    "maxItems": QUICK_REPLY_MAX_ITEMS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["message", "location"]},
                            "label": {"type": "string", "maxLength": QUICK_REPLY_MAX_LABEL_UNITS},
                            "text": {"type": ["string", "null"], "maxLength": QUICK_REPLY_MAX_TEXT_UNITS},
                        },
                        "required": ["type", "label", "text"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["reply_text", "is_finished", "quick_replies"],
            "additionalProperties": False,
        },
    },
}

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
# ชั้นสุดท้ายก่อนยอมแพ้ ใช้ตอน json พังแต่ยังเห็นช่อง reply_text อยู่ในข้อความ
_REPLY_TEXT = re.compile(r'"reply_text"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)


def _utf16_units (value: str) -> int:
    """LINE นับความยาว label เป็น UTF-16 code units ไม่ใช่จำนวนตัวอักษรของ Python"""
    return len(value.encode("utf-16-le")) // 2


def _loads (text: str) -> dict | None:
    """ลองแกะ json สามชั้น — ตรง ๆ / ลอกรั้วโค้ด / คว้าเฉพาะช่วงปีกกา"""
    for candidate in (text, _FENCE.sub("", text.strip())):
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            return data

    stripped = _FENCE.sub("", text.strip())
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(stripped[start : end + 1])
        except (ValueError, TypeError):
            return None
        if isinstance(data, dict):
            return data
    return None


def _clean_quick_replies (raw) -> list[QuickReplyItem]:
    """ตัดปุ่มที่ LINE รับไม่ได้ทิ้งทีละอัน — ปุ่มเสียหนึ่งอันต้องไม่ทำให้คำตอบทั้งตาเสีย

    กติกาทั้งหมดในนี้เป็นของ LINE ไม่ใช่ของเรา ยกมาจากตอนที่ปุ่มยังเดินมาทาง tool call ครบทุกข้อ
    """
    if not isinstance(raw, list):
        return []

    items: list[QuickReplyItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        action_type = entry.get("type")
        raw_label = entry.get("label")
        if not isinstance(raw_label, str):
            continue
        label = raw_label.strip()
        if not label or "\n" in label or _utf16_units(label) > QUICK_REPLY_MAX_LABEL_UNITS:
            continue

        if action_type == "message":
            raw_text = entry.get("text")
            if not isinstance(raw_text, str):
                continue
            text = raw_text.strip()
            if not text or _utf16_units(text) > QUICK_REPLY_MAX_TEXT_UNITS:
                continue
            item = QuickReplyItem(type="message", label=label, text=text)
        elif action_type == "location":
            if entry.get("text") is not None:
                continue
            item = QuickReplyItem(type="location", label=label, text=None)
        else:
            continue

        if item not in items:
            items.append(item)
        if len(items) == QUICK_REPLY_MAX_ITEMS:
            break

    # ตัวเลือกข้อความปุ่มเดียวไม่มีประโยชน์ แต่ location ปุ่มเดียวคือคำสั่งเปิดหน้าแชร์พิกัดที่สมบูรณ์
    if len(items) == 1 and items[0].type != "location":
        return []
    return items


def _coerce_finished (raw) -> bool:
    """true เมื่อมันตั้งใจบอกว่าจบเท่านั้น รูปอื่นทั้งหมดแปลว่ายังไม่จบ

    รับ "true" ที่เป็นสตริงด้วย เพราะโมเดลพิมพ์ boolean เป็นสตริงบ่อยพอที่จะเสียธงฟรี ๆ
    อย่างอื่นไม่เดาให้ ธงที่ปักผิดว่าจบ ตัดบทสนทนาของชาวบ้านทิ้งกลางคัน
    """
    if isinstance(raw, bool):
        return raw
    return isinstance(raw, str) and raw.strip().lower() == "true"


def past_reply_as_json (reply_text: str) -> str:
    """เขียนคำตอบเก่าของบอทกลับเป็นรูปตามสัญญา ไว้ใส่กลับเข้าประวัติตอนถามตาถัดไป

    โมเดลลอกรูปคำตอบจากตาเก่าของตัวเองเป็นหลัก หนักกว่าที่ system prompt สั่งเสียอีก
    เห็นร้อยแก้วในประวัติเมื่อไหร่มันเขียนร้อยแก้วต่อ แล้วเราก็เสียธงกับปุ่มทั้งตา
    วัดบนบทสนทนาจริงเส้นเดียวกัน: ประวัติเป็นร้อยแก้วได้ JSON 4/24 ประวัติเป็น JSON ได้ 24/24

    is_finished เป็น false เสมอ เพราะตาเก่าที่ยังมีตาต่อจากมัน แปลว่าตอนนั้นยังไม่จบจริง
    quick_replies ว่างเพราะเราไม่ได้เก็บปุ่มของตาเก่าไว้ ไม่ใช่เพราะตอนนั้นไม่มีปุ่ม
    ถ้าวันหน้าอยากให้มันจำว่าเคยยื่นปุ่มอะไรไป ต้องเก็บปุ่มลง Turn ก่อน
    """
    return json.dumps(
        {"reply_text": reply_text, "is_finished": False, "quick_replies": []},
        ensure_ascii=False,
    )


async def parse_communicator_reply (raw: str | None) -> CommunicatorReply | None:
    """แปลงคำตอบดิบจากโมเดลเป็นก้อนที่ส่งออกไลน์ได้ คืน None เมื่อไม่มีอะไรให้ส่งจริง ๆ

    ไล่ลงมาทีละชั้น ชั้นล่างยิ่งเสียของมากขึ้น แต่ทุกชั้นพยายามรักษาข้อความไว้ก่อนเสมอ:
    1. JSON ครบรูป            — ได้ครบทั้งข้อความ ธง ปุ่ม
    2. JSON พัง แต่เห็น reply_text — กู้เฉพาะข้อความ ทิ้งธงกับปุ่ม
    3. ร้อยแก้วล้วน            — เอาทั้งก้อนไปเป็นข้อความ ทิ้งธงกับปุ่ม
    4. ไม่มีอะไรใช้ได้          — None ให้คนเรียกเงียบไปตานั้น

    ชั้น 3 ไม่ยอมส่ง JSON ที่แกะไม่ออกออกไปดื้อ ๆ เพราะชาวบ้านจะเห็นวงเล็บปีกกาเต็มหน้าจอ
    เงียบยังดูดีกว่าส่งขยะไปให้ — แต่ชั้น 2 มีไว้เพื่อให้แทบไม่มีวันต้องไปถึงตรงนั้น
    """
    if not isinstance(raw, str) or not raw.strip():
        await psql.create_and_save_log(PROCESS, "communicator ไม่คืนข้อความสำหรับตอบผู้ใช้")
        return None

    data = _loads(raw)
    if data is not None:
        reply_text = data.get("reply_text")
        if isinstance(reply_text, str) and reply_text.strip():
            return CommunicatorReply(
                reply_text=reply_text.strip(),
                is_finished=_coerce_finished(data.get("is_finished")),
                quick_replies=_clean_quick_replies(data.get("quick_replies")),
            )
        await psql.create_and_save_log(PROCESS, f"communicator คืน JSON ที่ไม่มี reply_text ใช้ได้ {raw[:200]!r}")
        return None

    stripped = _FENCE.sub("", raw.strip()).strip()

    # ขึ้นต้นด้วยปีกกาแปลว่ามันตั้งใจเขียน JSON แล้วเขียนพัง ห้ามส่งก้อนนี้ไปให้ชาวบ้านเห็น
    if stripped.startswith("{"):
        found = _REPLY_TEXT.search(stripped)
        if found is None:
            await psql.create_and_save_log(PROCESS, f"communicator คืน JSON ที่แกะไม่ออกและหา reply_text ไม่เจอ {raw[:200]!r}")
            return None
        await psql.create_and_save_log(PROCESS, "communicator คืน JSON ที่แกะไม่ออก กู้เฉพาะ reply_text ทิ้งธงกับปุ่มรอบนี้")
        return CommunicatorReply(reply_text=_unescape(found.group(1)))

    # ร้อยแก้วล้วน — มันลืมรูปแบบ แต่ของที่ชาวบ้านรอคือข้อความ ซึ่งอยู่ตรงหน้าแล้ว
    await psql.create_and_save_log(PROCESS, "communicator ตอบเป็นข้อความเปล่าแทน JSON ใช้ข้อความนั้นตอบไปเลย ทิ้งธงกับปุ่มรอบนี้")
    return CommunicatorReply(reply_text=stripped)


def _unescape (value: str) -> str:
    """คืนค่าที่อ่านได้จากเนื้อในของสตริง json ที่ตัวห่อมันพังไปแล้ว

    ต้องห่อกลับเป็นสตริง json ก่อนถึงจะแปลง \\n กับ \\" ได้ถูก
    ขึ้นบรรทัดจริงที่หลุดมาในเนื้อคือสาเหตุหลักที่ก้อนเดิมพัง ต้องแปลงกลับเป็น escape ก่อนไม่งั้นพังซ้ำ
    """
    try:
        return json.loads('"' + value.replace("\r", "").replace("\n", "\\n") + '"').strip()
    except ValueError:
        return value.strip()
