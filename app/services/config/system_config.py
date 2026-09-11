from pydantic import ValidationError

from app.clients import psql
from app.schemas.system_config import SystemConfig

PROCESS = "services.config.system_config"

# ทั้งแอปอ่านจากตัวนี้ผ่าน get() — ห้าม from ... import _current เพราะจะได้ก้อนเก่าค้างไว้
_current = SystemConfig()


def get() -> SystemConfig:
    """อ่านจาก memory ไม่แตะ db"""
    return _current


async def reload() -> SystemConfig:
    """ดึงแถวที่ is_active มาแทนก้อนเดิม

    ไม่มีแถว active = ใช้ค่า default ในโค้ด
    แถว active ค่าเพี้ยน = ถือก้อนเดิมต่อ (ตอนเปิดแอปก้อนเดิมก็คือ default)
    """
    global _current
    row = await psql.get_active_system_config()

    if row is None:
        _current = SystemConfig()
        await psql.create_and_save_log(PROCESS, "system_config ไม่มีแถว active ใช้ค่า default")
        print("system_config: ไม่มีแถว active ใช้ค่า default", _current)
        return _current

    try:
        _current = SystemConfig(**row)
    except ValidationError as e:
        await psql.create_and_save_log(PROCESS, f"system_config id {row['id']} ค่าเพี้ยน ถือก้อนเดิมต่อ {e}")
        print("system_config: ค่าเพี้ยน ถือก้อนเดิมต่อ", _current)
        return _current

    await psql.create_and_save_log(PROCESS, f"โหลด system_config id {_current.id}")
    print("system_config:", _current)
    return _current
