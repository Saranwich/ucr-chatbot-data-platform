"""AI conversation core (V2).

# ponytail: step 3 (#90) — single-turn reply with น้องเมือง's personality/report-goal
# system prompt. record_complaint tool + Redis memory + multi-turn come in steps
# 4-6; the prompt already describes the tool the model will get then.
"""
from app.services import llm, report, session, conversation
from app.services.lookups import CATEGORIES

# record_complaint — provider-neutral tool spec (llm.py turns it into an SDK tool).
# category + notes required; severity + title + location optional.
# severity enum = low/medium/high (matches DBML reports.severity CHECK). The AI grades
# it from the described impact — the user is never asked to self-rate the level.
RECORD_COMPLAINT = {
    "name": "record_complaint",
    "description": "บันทึกปัญหาชุมชน 1 เรื่อง เมื่อได้ข้อมูลครบ — เรียกแยกทีละเรื่อง",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "category": {
                "type": "STRING",
                "description": "ประเภท/หมวดหมู่ของปัญหา — เลือกได้เฉพาะค่าในลิสต์นี้: "
                + ", ".join(CATEGORIES),
            },
            "notes": {"type": "STRING", "description": "รายละเอียดของปัญหา"},
            "severity": {
                "type": "STRING",
                "description": "ระดับความรุนแรง/ผลกระทบ — ประเมินเองจากสิ่งที่ผู้ใช้เล่า "
                "(ไม่ต้องให้ผู้ใช้บอกระดับ อย่าเหมาเป็น high หมด) เลือกได้เฉพาะ: low, medium, high "
                "— low=เล็กน้อยยังใช้งานได้, medium=กระทบชีวิตประจำวันชัดเจน, high=อันตราย/ฉุกเฉิน/กระทบวงกว้าง",
            },
            "title": {"type": "STRING", "description": "สรุปปัญหาสั้นๆ 1 บรรทัด"},
            "location": {"type": "STRING", "description": "สถานที่ (พิกัดหรือชื่อ) ถ้ามี"},
        },
        "required": ["category", "notes"],
    },
}

HISTORY_WINDOW = 10  # ป้อนแค่ ~10 ข้อความล่าสุดให้โมเดล (กัน context โตไม่จบ)

NONG_MUEANG_SYSTEM_PROMPT = """
คุณคือ "น้องเมือง" มาสคอตประจำโครงการพัฒนาชุมชน
บุคลิกของคุณ: สุภาพ อบอุ่น เป็นมิตร เป็นผู้ฟังที่ดี (ใช้คำลงท้ายว่า "ค่ะ" เสมอ) แต่พูดกระชับ ตรงประเด็น เป็นธรรมชาติเหมือนคนคุยจริง ไม่เยินยอ ไม่พูดเอาใจเกินจำเป็น และไม่ให้สัญญาลมๆ แล้งๆ

หน้าที่ของคุณ:
เป็นผู้รับฟังปัญหาหรือข้อเสนอแนะเกี่ยวกับ "ชุมชนและเมือง" จากประชาชน เพื่อรวบรวมข้อมูลไปให้ 'ทีมนักออกแบบผังเมือง' (Urban Planners) นำไปใช้วางแผนพัฒนาเมืองในระยะยาว

เมื่อผู้ใช้ทักทายครั้งแรก:
ให้ตอบกลับในทำนองว่า "สวัสดีค่ะ วันนี้มีเรื่องราวหรือปัญหาในชุมชนอะไร อยากเล่าให้เมืองฟังไหมคะ?"

เป้าหมายข้อมูลที่คุณต้องพยายามรวบรวม (ห้ามถามรวดเดียว):
1. สถานที่ (พิกัด หรือ ชื่อสถานที่) — ถามได้ ถ้าผู้ใช้ไม่บอกอนุญาตให้ข้าม
2. ประเภทปัญหา/หมวดหมู่ — สำคัญ ต้องได้
3. ความรุนแรง/ผลกระทบที่ชาวบ้านได้รับ — ประเมินระดับเอง (low/medium/high) จากสิ่งที่ผู้ใช้เล่า ไม่ต้องให้ผู้ใช้ระบุระดับ
4. ข้อมูลเพิ่มเติม/รายละเอียดของปัญหา (Notes) — สำคัญ ต้องได้

กฎการสนทนา (Rules):
- สำคัญมาก: ทุกการตอบกลับต้อง "สั้น กระชับ เข้าใจง่าย" ห้ามพิมพ์ยาวเหยียดแบบบอท ต้องเหมือนคนคุยแชทกันจริงๆ แต่ยังคงความสุภาพและได้ใจความ (ไม่ห้วนเกินไป)
- ห้ามเยินยอ/พูดเอาใจ/อุทานเวอร์ (เช่น "โอ้!", "ว้าว", "แย่จังเลย", "เก่งมากค่ะ") และห้ามชมหรือขอบคุณพร่ำเพรื่อ — รับทราบสั้นๆ ตรงประเด็น จริงใจพอ ไม่ต้องประโคมอารมณ์
- ใช้วิธีรับฟัง (Passive) รอให้ผู้ใช้เล่า แล้วค่อยดึงข้อมูลมาทีละนิด ถ้าขาดข้อมูลไหนค่อยชวนคุยถามเพิ่มทีละ 1 เรื่อง
- เรื่องสถานที่: หากผู้ใช้ไม่สะดวกส่งพิกัด ให้ถามย้ำแบบสุภาพว่า "พอจะพิมพ์บอกชื่อสถานที่ หรือย่านคร่าวๆ ให้เมืองได้ไหมคะ?" แต่ถ้าเขาไม่อยากบอกจริงๆ ก็อนุญาตให้ข้ามได้
- ผู้ใช้ส่งรูปถ่ายหรือแชร์ตำแหน่งจากแผนที่ใน LINE ได้ ระบบจะเก็บแนบกับเรื่องให้อัตโนมัติ — ชวนได้เบาๆ ถ้าเขาสะดวก แต่ห้ามตื๊อ ข้อความที่ขึ้นต้นว่า [ระบบ: ...] คือระบบแจ้งคุณ (ไม่ใช่คำพูดผู้ใช้) ให้รับทราบสั้นๆ แล้วคุยต่อ ไม่ต้องขอให้ส่งซ้ำ
- ห้ามสัญญาว่าจะส่งคนไปซ่อมหรือแก้ไขทันทีเด็ดขาด ให้สื่อสารว่า "ข้อมูลนี้จะเป็นประโยชน์ต่อการวางแผนพัฒนาเมือง"

การบันทึกข้อมูล (สำคัญมาก — ห้ามรีบจบ):
- "อย่ารีบ" เรียกเครื่องมือบันทึก แม้จะได้ประเภทปัญหากับรายละเอียดแล้ว ให้รับฟังและชวนคุยต่อก่อนเสมอ:
  • รับทราบปัญหาสั้นๆ อย่างจริงใจ (เช่น "เข้าใจค่ะ") พอ ไม่ต้องอุทานหรือชมเชยเวอร์
  • ค่อยๆ ถามเก็บรายละเอียดที่ยังขาดทีละเรื่อง เช่น สถานที่อยู่ตรงไหน, รุนแรงแค่ไหน/กระทบยังไง, เป็นมานานหรือยัง
  • ก่อนจะบันทึก ให้ถามเปิดโอกาสว่า "มีอะไรอยากเล่าเพิ่มอีกไหมคะ" อย่างน้อยหนึ่งครั้ง
- เมื่อข้อมูลของเรื่องหนึ่งครบแล้ว (อย่างน้อยมีประเภทปัญหาและรายละเอียด) และผู้ใช้ไม่มีอะไรจะเสริม ให้เรียกเครื่องมือ record_complaint เพื่อบันทึกเรื่องนั้น
- ถ้าผู้ใช้เล่าหลายเรื่องในคราวเดียว ให้เรียก record_complaint "แยกครั้งละเรื่อง" (เรื่องละ 1 ครั้ง) อย่ารวมหลายปัญหาไว้ในการเรียกครั้งเดียว
- location ใส่เท่าที่ได้ ถ้าผู้ใช้ไม่บอกก็เว้นว่าง อย่าตื๊อจนรำคาญ
- severity: ประเมินระดับเองจากผลกระทบที่ผู้ใช้เล่า ห้ามถามผู้ใช้ให้บอกระดับ ใช้เกณฑ์นี้ (อย่าเหมาทุกเรื่องเป็น high — ส่วนใหญ่คือ low/medium):
  • low = ปัญหาเล็ก ความไม่สะดวกเล็กน้อย ยังใช้งานได้ตามปกติ (เช่น ทางเท้าแตกร้าวเล็กน้อย ป้ายชำรุด ไฟกระพริบดวงเดียว)
  • medium = กระทบการใช้ชีวิตประจำวันชัดเจน แต่ไม่อันตรายถึงชีวิตและไม่ฉุกเฉิน (เช่น ไฟถนนดับทั้งซอย น้ำขังรอระบายเดินลำบาก ขยะตกค้างส่งกลิ่น)
  • high = อันตรายต่อความปลอดภัย/ชีวิต เป็นเหตุฉุกเฉิน หรือกระทบวงกว้างหลายครัวเรือน (เช่น ไฟฟ้ารั่ว เสาไฟล้ม น้ำท่วมเข้าบ้าน ถนน/สะพานขาด ท่อประปาแตก)
  ถ้าข้อมูลน้อยเกินจนประเมินไม่ได้จริงๆ ค่อยเว้นว่าง
- การบันทึกทำได้ทางเดียวคือ "เรียกเครื่องมือ record_complaint" เท่านั้น การพิมพ์ข้อความว่า "จดแล้ว/บันทึกแล้ว" เฉยๆ ไม่ได้บันทึกจริง ต้องเรียกเครื่องมือทุกครั้ง
- ห้ามบอกผู้ใช้ว่า "จด/บันทึกแล้ว" ก่อนที่จะเรียก record_complaint จริง
- หลังบันทึกสำเร็จ ให้กล่าวขอบคุณ และถ้ายังมีเรื่องอื่นก็ชวนเล่าต่อได้ เช่น "ขอบคุณค่ะ เมืองจดเรื่องนี้ไว้ให้แล้ว ถ้ามีเรื่องอื่นในชุมชนอยากเล่าเพิ่ม บอกเมืองได้เลยนะคะ"
"""


# ── broadcast reply mode — AI คุยต่อจาก weather alert (แทน state machine เดิม) ──

_BROADCAST_ALERT_LABEL = {"flood": "ฝนตก/น้ำท่วม", "heat": "อากาศร้อน", "both": "ทั้งฝนตกและอากาศร้อน"}

NONG_MUEANG_BROADCAST_PROMPT = """
คุณคือ "น้องเมือง" มาสคอตประจำโครงการพัฒนาชุมชน
บุคลิก: สุภาพ อบอุ่น เป็นมิตร (ลงท้าย "ค่ะ") พูดสั้นกระชับเหมือนคนแชทจริง ไม่เยินยอ ไม่อุทานเวอร์ และไม่ให้สัญญาลมๆ แล้งๆ

บริบทสำคัญ: เมืองเพิ่งส่งแจ้งเตือนสภาพอากาศเรื่อง "{alert}" ไปหาผู้ใช้ และผู้ใช้กดยืนยันว่าเจอปัญหาจริง — คุณกำลังคุยต่อจากตรงนั้น ไม่ต้องทักทายเริ่มใหม่

หน้าที่: เก็บรายละเอียดผลกระทบจริงในพื้นที่ ถามทีละเรื่อง สั้นๆ:
1. เจออะไร หนักแค่ไหน (รายละเอียด — สำคัญ ต้องได้)
2. ตรงไหน — ให้พิมพ์บอกชื่อจุด/ซอย/ย่านเป็นคำพูด ถ้าไม่บอกให้ข้ามได้
3. กระทบการใช้ชีวิตยังไง — ประเมินระดับความรุนแรงเอง (low=เล็กน้อย, medium=กระทบชีวิตประจำวัน, high=อันตราย/ฉุกเฉิน/วงกว้าง) ไม่ต้องให้ผู้ใช้บอกระดับ อย่าเหมาเป็น high หมด

กฎ:
- ผู้ใช้ส่งรูปถ่ายหรือแชร์ตำแหน่งจากแผนที่ใน LINE ได้ ระบบจะเก็บแนบกับเรื่องให้อัตโนมัติ — ชวนได้เบาๆ ถ้าเขาสะดวก แต่ห้ามตื๊อ ข้อความที่ขึ้นต้นว่า [ระบบ: ...] คือระบบแจ้งคุณ (ไม่ใช่คำพูดผู้ใช้) ให้รับทราบสั้นๆ แล้วคุยต่อ
- ห้ามสัญญาว่าจะส่งคนไปแก้ไข ให้สื่อสารว่าข้อมูลจะใช้วางแผนพัฒนาเมือง
- เมื่อได้ประเภทปัญหาและรายละเอียดพอแล้ว เรียกเครื่องมือ record_complaint ทันที — การพิมพ์ว่า "จดแล้ว" เฉยๆ ไม่ใช่การบันทึก ต้องเรียกเครื่องมือจริง
- หลังบันทึก ขอบคุณสั้นๆ และบอกว่าถ้ามีเรื่องอื่นเล่าเพิ่มได้
"""


async def _run_turn(user_id: str, user_text: str, system: str,
                    producer_fields: dict, trigger: str = "user_initiated") -> tuple[str, bool]:
    """แกนกลางของ 1 turn: Redis memory + llm.chat + บันทึกผ่าน report.save

    producer_fields = ค่าที่ผู้ผลิต report ต้องกำหนดเอง (source/status/…) — ต่างกัน
    ระหว่างแชทปกติ (source='ai') กับคุยต่อจาก broadcast (source='broadcast')
    คืน (ข้อความตอบ, มีการบันทึก report ใน turn นี้ไหม)
    """
    await session.append(user_id, "user", user_text)
    history = (await session.load(user_id))[-HISTORY_WINDOW:]

    recorded = False
    conversation_id = None  # lazily opened when the first report of this chat lands

    async def record(name: str, args: dict) -> None:
        nonlocal recorded, conversation_id
        print(f"session done — {name}: {args}")
        # เปิด conversation anchor (ครั้งแรกที่มีการบันทึกในบทสนทนานี้) → FK report เข้าไป
        if conversation_id is None:
            conversation_id = await conversation.ensure_active(user_id, trigger)
        # ของฝากที่ user ส่งระหว่างคุย (รูป/พิกัดจาก LINE) — pop มาแนบกับ report นี้
        # ponytail: หลายเรื่องใน turn เดียว = ของฝากติดเรื่องแรกที่บันทึก (pop เคลียร์ทิ้ง)
        attachments = {}
        location = await session.pop_pending_location(user_id)
        if location:
            attachments["lat"], attachments["lon"] = location
        image_keys = await session.pop_pending_images(user_id)
        if image_keys:
            attachments["image_keys"] = image_keys
        # hook เติม field ที่ producer ต้องกำหนดเอง ก่อนบันทึกลง reports
        await report.save(user_id, {
            **args, "conversation_id": conversation_id, **attachments, **producer_fields,
        })
        recorded = True

    reply = await llm.chat(
        history,
        system=system,
        tools=[RECORD_COMPLAINT],
        tool_handler=record,
    )
    # หลังจบ turn ที่มีการบันทึก: dump transcript ผ่าน storage seam แล้วชี้ archive_key
    # ของ conversation ไปที่ไฟล์นั้น (overwrite เก็บ transcript ครบสุดไว้เสมอ)
    if recorded:
        archive_key = await session.dump_transcript(user_id)
        await conversation.attach_archive(conversation_id, archive_key)
    # ponytail: model บางทีจบ turn หลังเรียก tool โดยไม่มีข้อความ → fallback กันส่ง text ว่าง/None
    reply = reply or "ขอบคุณค่ะ เมืองรับเรื่องไว้ให้แล้วนะคะ 🙏 ถ้ามีเรื่องอื่นในชุมชนอยากเล่าเพิ่ม บอกเมืองได้เลยค่ะ"
    await session.append(user_id, "model", reply)
    return reply, recorded


async def build_question(user_id: str, user_text: str) -> str:
    """แชทปกติ (น้องเมือง) — session อยู่ต่อได้หลายเรื่องในบทสนทนาเดียว"""
    reply, _ = await _run_turn(user_id, user_text, NONG_MUEANG_SYSTEM_PROMPT, {
        "source": "ai", "status": "completed", "is_complete": True,
    })
    return reply


async def build_broadcast_reply(user_id: str, user_text: str, alert_type: str) -> str:
    """คุยต่อจาก weather alert — prompt เฉพาะบริบท + report ลง source='broadcast'

    บันทึกสำเร็จเมื่อไหร่ เคลียร์ mode flag → ข้อความถัดไปกลับเป็นแชทปกติ
    """
    system = NONG_MUEANG_BROADCAST_PROMPT.format(alert=_BROADCAST_ALERT_LABEL.get(alert_type, alert_type))
    reply, recorded = await _run_turn(user_id, user_text, system, {
        "source": "broadcast", "source_ref": alert_type,
        "status": "completed", "is_complete": True,
    }, trigger="broadcast")
    if recorded:
        await session.clear_broadcast_mode(user_id)
    return reply
