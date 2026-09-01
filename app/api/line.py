from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from app.services import auth, chatbot
from app.clients import psql

PROCESS = "api.line"

router = APIRouter()


@router.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    if (not await auth.verify_line_signature(request)) :
        # await ตรงนี้ ไม่ใช่ add_task — พอ raise แล้ว background task ไม่ได้ถูกรัน
        await psql.create_and_save_log(PROCESS, "signature ไม่ผ่าน ปัดคำขอทิ้ง")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # ของจริงเข้ามาแล้ว บันทึกทีหลังตอบ 200 ไปก่อน LINE รอไม่เกิน 1 วิ
    background_tasks.add_task(psql.create_and_save_log, PROCESS, "รับ callback เข้ามา")
    background_tasks.add_task(chatbot.handle, request)
    return "OK"