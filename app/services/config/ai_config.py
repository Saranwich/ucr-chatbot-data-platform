from pydantic import ValidationError

from app.clients import psql
from app.schemas.ai_config import AgentConfig, AiConfig, default_agent_config

PROCESS = "services.config.ai_config"

# ทั้งแอปอ่านจากตัวนี้ผ่าน get() — ห้าม from ... import _current เพราะจะได้ก้อนเก่าค้างไว้
_current = AiConfig()


def get() -> AiConfig:
    """อ่านจาก memory ไม่แตะ db — เรียกครั้งเดียวต้นรอบแล้วถือก้อนนั้นไปทั้งรอบ"""
    return _current


async def reload() -> AiConfig:
    """ดึงแถวที่ is_active ของทุก agent มาแทนก้อนเดิม แต่ละ agent ไม่ลากกัน

    agent ไหนไม่มีแถว active = ใช้ default ของตัวนั้น
    agent ไหนแถว active ค่าเพี้ยน = ถือค่าเดิมของตัวนั้นต่อ (ตอนเปิดแอปค่าเดิมก็คือ default)
    """
    global _current
    loaded: dict[str, AgentConfig] = {}
    broken: set[str] = set()

    for row in await psql.get_active_ai_configs():
        try:
            config = AgentConfig(**row)
        except ValidationError as e:
            broken.add(row["agent"])
            await psql.create_and_save_log(PROCESS, f"ai_configuration id {row['id']} ({row['agent']}) ค่าเพี้ยน ข้ามแถวนี้ {e}")
            continue
        loaded[config.agent] = config

    for agent in AiConfig.model_fields:
        if agent in loaded:
            continue
        if agent in broken:
            loaded[agent] = getattr(_current, agent)
            continue
        loaded[agent] = default_agent_config(agent)
        await psql.create_and_save_log(PROCESS, f"{agent} ไม่มีแถว active ใช้ค่า default")

    _current = AiConfig(**loaded)
    await psql.create_and_save_log(
        PROCESS,
        "โหลด ai config " + ", ".join(f"{name}=id {cfg.id}" for name, cfg in _current),
    )
    print("ai_config:", _current)
    return _current
