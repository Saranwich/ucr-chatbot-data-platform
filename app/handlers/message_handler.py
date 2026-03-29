from sqlalchemy.orm import Session
from linebot.v3.messaging import MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent
import app.models as models

def handle_text_message(event: MessageEvent, db: Session, line_bot_api: MessagingApi):
    user_id = event.source.user_id
    user_text = event.message.text

    # --- สเตป 1: เช็ค User ---
    user = db.query(models.User).filter(models.User.lineuser_id == user_id).first()
    if not user:
        user = models.User(lineuser_id=user_id, display_name="Unknown")
        db.add(user)
        db.commit()

    # --- สเตป 2: เซฟคำตอบ (ถ้ามีคำถามค้างอยู่) ---
    pending_log = db.query(models.AskLog).filter(
        models.AskLog.lineuser_id == user_id,
        models.AskLog.is_answered == False
    ).first()

    if pending_log:
        new_response = models.Response(
            lineuser_id=user_id,
            question_id=pending_log.question_id,
            response_type="text",
            response_text=user_text
        )
        db.add(new_response)
        pending_log.is_answered = True
        db.commit()

    # --- สเตป 3: หาคำถามข้อถัดไป ---
    answered_questions = db.query(models.AskLog.question_id).filter(models.AskLog.lineuser_id == user_id)
    next_question = db.query(models.Question).filter(
        models.Question.is_active == True,
        ~models.Question.question_id.in_(answered_questions)
    ).order_by(models.Question.question_id).first()

    # --- สเตป 4: เตรียมข้อความตอบกลับ ---
    if next_question:
        new_log = models.AskLog(lineuser_id=user_id, question_id=next_question.question_id)
        db.add(new_log)
        db.commit()
        reply_text = next_question.question_text
    else:
        reply_text = "ขอบคุณที่ให้ข้อมูลครับ ตอนนี้ตอบครบทุกคำถามแล้ว! 🎉"

    # ยิงข้อความกลับ
    line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        )
    )