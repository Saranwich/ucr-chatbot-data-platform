"""ตัวกวาดที่เดินอยู่ในแอป คอยปิดบทสนทนาที่ใกล้หมดอายุแล้วส่งให้ analyzer

ถ้าปล่อยให้ redis หมดอายุเอง ตัวบทสนทนาจะหายไปก่อนมีใครได้อ่าน เลยต้องชิงปิดก่อนมันหมดอายุ
ปิดได้สองเหตุ เงียบนานจนใกล้หมดอายุ หรือ session ถูกปักธง is_finished ว่าเล่าจบแล้ว
ธงมาถึงก่อนก็ไม่ต้องรอเงียบ ไม่มีธงก็ยังปิดด้วยความเงียบเหมือนเดิม ไม่มีใครกดจบเองได้
"""

import asyncio

from app.clients import psql, redis
from app.services import chatbot
from app.services.config import system_config

PROCESS = "services.runtime"

_task: asyncio.Task | None = None


async def sweep_once() -> int:
    """กวาดหนึ่งรอบ คืนจำนวน session ที่ปิดไป"""
    closed = 0
    close_under = system_config.get().close_when_ttl_under_seconds

    for redis_key in await redis.scan_session_keys():
        ttl = await redis.get_ttl(redis_key)

        # -2 คือหายไปแล้วระหว่างที่กำลังกวาด ไม่มีอะไรให้ปิด ถามต่อก็เปลือง
        if ttl == -2:
            continue

        # -1 คือไม่ได้ตั้งอายุไว้ ไม่มีทางรู้ว่าเงียบมานานแค่ไหน ปล่อยไว้ดีกว่าปิดมั่ว
        # ยังไม่ถึงคิวด้วยความเงียบ แต่ถ้าชาวบ้านบอกว่าเล่าจบแล้ว ปิดเลยไม่ต้องรอ
        if ttl < 0 or ttl >= close_under:
            if not await chatbot.is_session_finished(redis_key):
                continue

        if await chatbot.close_session(redis_key) is not None:
            closed += 1

    return closed


async def run_forever() -> None:
    """วนกวาดไปเรื่อย ๆ — รอบไหนพังก็ log แล้วไปต่อ ห้ามตายทั้งตัวเพราะ session เดียวมีปัญหา"""
    while True:
        try:
            closed = await sweep_once()
            if closed:
                await psql.create_and_save_log(PROCESS, f"กวาดรอบนี้ปิดไป {closed} session")
        except Exception as error:
            await psql.create_and_save_log(PROCESS, f"กวาดรอบนี้พัง {type(error).__name__} {error}")
            print("runtime: กวาดรอบนี้พัง", error)

        # อ่านใหม่ทุกรอบ แอดมินแก้ค่าแล้ว reload() รอบถัดไปได้จังหวะใหม่เลย ไม่ต้องรีสตาร์ตแอป
        await asyncio.sleep(system_config.get().sweep_interval_seconds)


def start() -> None:
    """เปิดตัวกวาดตอนแอปสตาร์ท"""
    global _task
    if _task is None:
        _task = asyncio.create_task(run_forever())
        print("runtime: เปิดตัวกวาดแล้ว กวาดทุก", system_config.get().sweep_interval_seconds, "วินาที")


async def stop() -> None:
    """หยุดตัวกวาดตอนแอปปิด"""
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        print("runtime: ปิดตัวกวาดแล้ว")
