from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from linebot.v3.messaging import AsyncMessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent
import app.models as models

async def handle_text_message(event: MessageEvent, db: AsyncSession, line_bot_api: AsyncMessagingApi):
    user_id = event.source.user_id
    user_text = event.message.text

    stmt = select(models.User).filter(models.User.lineuser_id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        user = models.User(lineuser_id=user_id, display_name="Unknown")
        db.add(user)
        await db.commit()

    stmt_log = select(models.AskLog).filter(
        models.AskLog.lineuser_id == user_id,
        models.AskLog.is_answered == False
    )
    result_log = await db.execute(stmt_log)
    pending_log = result_log.scalars().first()

    if pending_log:
        new_response = models.Response(
            lineuser_id=user_id,
            question_id=pending_log.question_id,
            response_type="text",
            response_text=user_text
        )
        db.add(new_response)
        pending_log.is_answered = True
        await db.commit()

    stmt_answered = select(models.AskLog.question_id).filter(models.AskLog.lineuser_id == user_id)
    result_answered = await db.execute(stmt_answered)
    answered_questions = result_answered.scalars().all()

    # We use a conditional filter here to avoid errors if answered_questions is empty
    stmt_next = select(models.Question).filter(
        models.Question.is_active == True,
        ~models.Question.question_id.in_(answered_questions) if answered_questions else True
    ).order_by(models.Question.question_id)
    
    result_next = await db.execute(stmt_next)
    next_question = result_next.scalars().first()

    # --- สเตป 4: เตรียมข้อความตอบกลับ ---
    if next_question:
        new_log = models.AskLog(lineuser_id=user_id, question_id=next_question.question_id)
        db.add(new_log)
        await db.commit()
        reply_text = next_question.question_text
    else:
        reply_text = "ขอบคุณที่ให้ข้อมูลครับ ตอนนี้ตอบครบทุกคำถามแล้ว! 🎉"

    # ยิงข้อความกลับ (Now using await for the async API call)
    await line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        )
    )