"""Broadcast push service — "ยิงส่ง" อย่างเดียว (ข้อ ④ ของ flow broadcast)

รับ list ของ lineuser_id + messages ที่คนอื่นเตรียมมาแล้ว → ยิง LINE push ทีละคน
ไม่สร้างข้อความ ไม่เลือกคน ไม่แตะ DB — ความฉลาดพวกนั้นเป็นของ caller:
ข้อความมาจาก message service (ข้อ ②), รายชื่อมาจาก user service (ข้อ ③)

สัญญากับ caller:
- ยิงทีละคนเป็นอันๆ ไป — คนไหนพลาด (บล็อกบอท / id ใช้ไม่ได้ / เน็ตสะดุด)
  log แล้วไปต่อคนถัดไป ทั้งรอบไม่มีวันล้มเพราะ user คนเดียว
- คืนสรุป {"sent": [...], "failed": [...]} ให้ caller ตัดสินใจต่อเอง
  (เช่น retry เฉพาะ failed หรือจดผลลง log/DB — ไม่ใช่หน้าที่ของไฟล์นี้)
"""
from linebot.v3.messaging import (
    Configuration, AsyncApiClient, AsyncMessagingApi, PushMessageRequest,
)

from app.config import CHANNEL_ACCESS_TOKEN


async def push_to_users(user_ids: list, messages: list) -> dict:
    """ยิง messages ชุดเดียวกันให้ทุกคนใน user_ids ทีละคน แล้วสรุปว่าถึงใคร/พลาดใคร"""
    result = {"sent": [], "failed": []}
    if not user_ids:
        return result

    configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        for user_id in user_ids:
            try:
                await api.push_message(PushMessageRequest(to=user_id, messages=messages))
                result["sent"].append(user_id)
            except Exception as e:
                # user เดียวพลาดต้องไม่ทำให้คนที่เหลือไม่ได้รับแจ้งเตือน
                print(f"⚠️ broadcast push to {user_id} failed: {e}")
                result["failed"].append(user_id)
    return result
