from pydantic import ValidationError

from app.clients import psql
from app.schemas.system_setting import SystemSetting

PROCESS = "services.system_setting"

# ทั้งแอปอ่านจากตัวนี้ผ่าน get() — ห้าม from ... import _current เพราะจะได้ก้อนเก่าค้างไว้
_current = SystemSetting()


def get() -> SystemSetting:
    """อ่านจาก memory ไม่แตะ db"""
    return _current


async def reload() -> SystemSetting:
    """ดึงแถวที่ is_active มาแทนก้อนเดิม

    ไม่มีแถว active = ใช้ค่า default ในโค้ด
    แถว active ค่าเพี้ยน = ถือก้อนเดิมต่อ (ตอนเปิดแอปก้อนเดิมก็คือ default)
    """
    global _current
    row = await psql.get_active_system_setting()

    if row is None:
        _current = SystemSetting()
        await psql.create_and_save_log(PROCESS, "system_setting ไม่มีแถว active ใช้ค่า default")
        print("system_setting: ไม่มีแถว active ใช้ค่า default", _current)
        return _current

    try:
        _current = SystemSetting(**row)
    except ValidationError as e:
        await psql.create_and_save_log(PROCESS, f"system_setting id {row['id']} ค่าเพี้ยน ถือก้อนเดิมต่อ {e}")
        print("system_setting: ค่าเพี้ยน ถือก้อนเดิมต่อ", _current)
        return _current

    await psql.create_and_save_log(PROCESS, f"โหลด system_setting id {_current.id}")
    print("system_setting:", _current)
    return _current
