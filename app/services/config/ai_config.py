from pydantic import ValidationError

from app.clients import psql
from app.core.default_value import DEFAULT_AGENT_CONFIG
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
    แถวไหน prompt_id ว่าง หรือชี้ไป prompt ที่ไม่มี = ใช้ prompt default ของ agent นั้น
    """
    global _current
    loaded: dict[str, AgentConfig] = {}
    broken: set[str] = set()

    for row in await psql.get_active_ai_configs():
        if row["prompt"] is None:
            if row["prompt_id"] is not None:
                await psql.create_and_save_log(PROCESS, f"ai_configuration id {row['id']} ชี้ไป prompt id {row['prompt_id']} ที่ไม่มี ใช้ prompt default")
            row["prompt"] = DEFAULT_AGENT_CONFIG.get(row["agent"], {}).get("prompt", "")
            # ล้าง prompt_id ให้ตรงกับของที่ใช้จริง — ชี้ค้างไว้แล้วล็อกจะรายงานว่าใช้ prompt แถวนั้นทั้งที่ไม่ได้ใช้
            row["prompt_id"] = None
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
    summary = ", ".join(
        f"{name}=id {cfg.id if cfg.id is not None else 'default'} prompt {_prompt_label(cfg)}"
        for name, cfg in _current
    )
    await psql.create_and_save_log(PROCESS, f"โหลด ai config {summary}")
    print("[config.ai]")
    for name, cfg in _current:
        config_id = cfg.id if cfg.id is not None else "default"
        print(f"  {name:<18} id={str(config_id):<8} prompt={_prompt_label(cfg)}")
    return _current


def _prompt_label(config: AgentConfig) -> str:
    """prompt มาจากแถวไหน — ว่าง = ไม่ได้มาจากฐาน ใช้ default ใน core/default_value.py

    ห้ามตัดสินจากเนื้อ prompt เพราะแอดมินยก default ขึ้นฐานแล้วเนื้อจะตรงกัน ทั้งที่มาจากฐานจริง
    """
    return "default" if config.prompt_id is None else str(config.prompt_id)
