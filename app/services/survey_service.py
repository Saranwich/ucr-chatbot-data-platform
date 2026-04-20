from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    LocationAction,
    CameraAction
)

# Import โมเดล Database และตัวโหลด JSON ของเรา
from app.models import User, SurveySession, CompletedReport
from app.utils.survey_loader import survey_manager

async def start_survey_session(user_id: str, survey_version: str, reply_token: str, line_bot_api, db: AsyncSession):
    """เปิดโต๊ะ: ล้าง Session เก่า สร้างใหม่ แล้วยิงคำถามข้อแรก"""
    
    # 1. เช็ค User
    user_result = await db.execute(select(User).where(User.lineuser_id == user_id))
    user = user_result.scalars().first()
    if not user:
        user = User(lineuser_id=user_id)
        db.add(user)
        await db.flush()

    # 2. ล้างไพ่ (ถ้ามีงานค้างอยู่ให้ลบทิ้ง เริ่มใหม่)
    session_result = await db.execute(select(SurveySession).where(SurveySession.lineuser_id == user_id))
    active_session = session_result.scalars().first()

    if active_session:
        await db.delete(active_session)
        await db.flush()

    # 3. สร้าง Session ใหม่ (เริ่ม Step 0)
    new_session = SurveySession(
        lineuser_id=user_id,
        survey_version=survey_version,
        current_step=0,
        payload={}
    )
    db.add(new_session)
    await db.commit()

    # 4. งัดคำถามข้อแรกออกมาส่ง
    first_question = survey_manager.get_question_by_step(survey_version, 0)
    if first_question:
        await send_question(reply_token, first_question, line_bot_api)


async def process_survey_answer(user_id: str, answer_data, reply_token: str, line_bot_api, db: AsyncSession):
    """เครื่องจักร State Machine: รับคำตอบ -> บันทึก -> ถามข้อต่อไป หรือ จบงาน"""
    
    # 1. หา Session ปัจจุบัน
    session_result = await db.execute(select(SurveySession).where(SurveySession.lineuser_id == user_id))
    active_session = session_result.scalars().first()

    if not active_session:
        # ถ้าไม่ได้เปิดโต๊ะไว้ แต่พิมพ์ตอบมา ให้เงียบๆ ไว้ (หรือจะตอบกลับให้กดเมนูก็ได้)
        return

    survey_version = active_session.survey_version
    current_step = active_session.current_step

    # 2. เอาคำถามข้อที่เพิ่งตอบไปมาเป็น Key เพื่อบันทึกคำตอบ
    current_question = survey_manager.get_question_by_step(survey_version, current_step)
    if not current_question: return

    # บันทึกลง payload (ต้อง copy() ก่อนเพื่อให้ SQLAlchemy รู้ว่ามีการเปลี่ยนแปลง)
    payload = active_session.payload.copy() if active_session.payload else {}
    payload[current_question.id] = answer_data
    active_session.payload = payload

    # 3. เดินหน้า 1 ก้าว
    active_session.current_step += 1
    next_step = active_session.current_step
    
    # 4. ค้นหาคำถามข้อต่อไป
    next_question = survey_manager.get_question_by_step(survey_version, next_step)

    if next_question:
        # 🌟 ถ้ายังมีข้อต่อไป เซฟ DB แล้วส่งคำถาม
        await db.commit()
        await send_question(reply_token, next_question, line_bot_api)
    else:
        # 🎉 ถ้าไม่มีคำถามแล้ว (จบแบบสำรวจ)
        # แพ็คข้อมูลลงตาราง CompletedReport
        
        # สมมติว่าข้อแรกเราตั้ง id ว่า "q1_location" ตามที่คุณอาจจะวางแผนไว้
        loc_data = active_session.payload.get("q1_location")
        postgis_point = None
        if isinstance(loc_data, dict) and "lat" in loc_data and "lng" in loc_data:
            postgis_point = f"SRID=4326;POINT({loc_data['lng']} {loc_data['lat']})"

        completed_report = CompletedReport(
            lineuser_id=user_id,
            survey_version=survey_version,
            payload=active_session.payload,
            location_data=postgis_point
        )
        db.add(completed_report)
        
        # ลบกระดาษทด
        await db.delete(active_session)
        await db.commit()

        # ส่งข้อความขอบคุณ
        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="ขอบคุณที่ร่วมรายงานข้อมูลครับ")]
            )
        )

async def send_question(reply_token: str, question_obj, line_bot_api):
    """ฟังก์ชันผู้ช่วยสำหรับสร้างปุ่ม Quick Reply และส่งข้อความ"""
    quick_reply_items = []
    for opt in question_obj.options:
        action = None
        if opt.action_type == "message":
            action = MessageAction(label=opt.label, text=opt.value if opt.value else opt.label)
        elif opt.action_type == "location":
            action = LocationAction(label=opt.label)
        elif opt.action_type == "camera":
            action = CameraAction(label=opt.label)
        
        if action:
            quick_reply_items.append(QuickReplyItem(action=action))

    message = TextMessage(
        text=question_obj.text,
        quick_reply=QuickReply(items=quick_reply_items) if quick_reply_items else None
    )

    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[message]
        )
    )