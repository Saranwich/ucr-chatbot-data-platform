from pydantic import ValidationError

from app.clients import psql
from app.schemas.system_config import SystemConfig

PROCESS = "services.config.system_config"

# ทั้งแอปอ่านจากตัวนี้ผ่าน get() — ห้าม from ... import _current เพราะจะได้ก้อนเก่าค้างไว้
_current = SystemConfig()


def _duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if not hours and not minutes:
        return f"{seconds}s"
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if remaining_seconds:
        parts.append(f"{remaining_seconds}s")
    return f"{seconds}s ({' '.join(parts)})"


def _print_config(config: SystemConfig, source: str) -> None:
    print("[config.system]")
    print(f"  source             {source}")
    print(f"  note               {config.note or '-'}")
    print(f"  session TTL        {_duration(config.session_ttl_seconds)}")
    print(f"  finished grace     {_duration(config.finished_grace_seconds)}")
    print(f"  inactive timeout   {_duration(config.inactive_session_seconds)}")
    print(f"  sweep interval     {_duration(config.sweep_interval_seconds)}")


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
        _print_config(_current, "default")
        return _current

    try:
        _current = SystemConfig(**row)
    except ValidationError as e:
        await psql.create_and_save_log(PROCESS, f"system_config id {row['id']} ค่าเพี้ยน ถือก้อนเดิมต่อ {e}")
        _print_config(_current, "previous (active row invalid)")
        return _current

    await psql.create_and_save_log(PROCESS, f"โหลด system_config id {_current.id}")
    _print_config(_current, f"database id={_current.id}")
    return _current
