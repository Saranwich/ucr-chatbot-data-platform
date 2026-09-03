from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from app.services import auth, chatbot
from app.clients import psql

PROCESS = "api.line"

router = APIRouter()


@router.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    if (not await auth.verify_line_signature(request)) :
        await psql.create_and_save_log(PROCESS, "signature ไม่ผ่าน ปัดคำขอทิ้ง")
        raise HTTPException(status_code=400, detail="Invalid signature")

    background_tasks.add_task(psql.create_and_save_log, PROCESS, "รับ callback เข้ามา")
    background_tasks.add_task(chatbot.handle, request)
    return "OK"