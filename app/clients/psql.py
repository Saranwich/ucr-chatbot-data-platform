import asyncpg
from app.core.config import DATABASE_URL
from app.schemas.logs import LogsRecord
from app.schemas.user import User

_pool: asyncpg.Pool | None = None

## app part ##
async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        await init_db()
    return _pool


async def init_db() -> None:
    """ตั้งตารางให้ครบ — ตารางไหนมีอยู่แล้วก็ข้ามไปเงียบ ๆ เรียกจาก init_pool()"""
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id           uuid        PRIMARY KEY,
            time         timestamptz NOT NULL,
            process_name text        NOT NULL,
            log_message  text        NOT NULL
        )
    """)
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           uuid PRIMARY KEY,
            line_user_id text NOT NULL UNIQUE,
            name         text,
            age_group    text              -- children | teenage | mature | elder
        )
    """)
    # หนึ่งแถว = ค่าหนึ่งเวอร์ชันของ agent หนึ่งตัว ห้ามแก้แถวเก่า
    # เปลี่ยนค่า = เพิ่มแถวใหม่แล้วย้าย is_active มา / ย้อนกลับ = ย้าย is_active กลับไปแถวเก่า
    # CHECK ตรงกับ Field ใน schemas/ai_config.py กันแอดมินพิมพ์ค่าเพี้ยนใน DBeaver
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS ai_configuration (
            id                bigserial        PRIMARY KEY,
            created_at        timestamptz      NOT NULL DEFAULT now(),
            note              text,
            is_active         boolean          NOT NULL DEFAULT false,
            agent             text             NOT NULL,   -- communicator | analyzer | resource_analyzer
            provider          text             NOT NULL,
            model_name        text             NOT NULL CHECK (model_name <> ''),
            prompt_id         bigint,                      -- ชี้ไป prompts.id วันที่มีตาราง prompts
            temperature       double precision NOT NULL CHECK (temperature BETWEEN 0 AND 2),
            max_output_tokens integer          NOT NULL CHECK (max_output_tokens > 0)
        )
    """)
    # agent หนึ่งตัว active ได้แถวเดียว — db ปฏิเสธแถวที่สองเอง ไม่ต้องรอใครมาเจอ
    await get_pool().execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ai_configuration_one_active_per_agent
            ON ai_configuration (agent) WHERE is_active
    """)
    # กติกาเดียวกับ ai_configuration แต่ทั้งระบบมีชุดเดียว เลย active ได้แถวเดียวทั้งตาราง
    # CHECK ตรงกับ Field ใน schemas/system_setting.py
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS system_setting (
            id                  bigserial   PRIMARY KEY,
            created_at          timestamptz NOT NULL DEFAULT now(),
            note                text,
            is_active           boolean     NOT NULL DEFAULT false,
            session_ttl_seconds integer     NOT NULL CHECK (session_ttl_seconds > 0)
        )
    """)
    await get_pool().execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS system_setting_one_active
            ON system_setting (is_active) WHERE is_active
    """)


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("ยังไม่ได้เปิด pool — เรียก init_pool() ตอน startup ก่อน")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


_INSERT_LOG = """
INSERT INTO logs (id, time, process_name, log_message)
VALUES ($1, $2, $3, $4)
"""


async def create_and_save_log(process_name: str, log_message: str) -> None:
    """เรียกด้วยสองสตริงพอ — id กับ time ให้ LogsRecord เติมเอง"""
    log = LogsRecord(process_name=process_name, log_message=log_message)
    await get_pool().execute(
        _INSERT_LOG, log.id, log.time, log.process_name, log.log_message
    )


## user part ##
async def get_user_by_line_user_id(line_user_id: str) -> User | None:
    """หา user จาก LINE id — ยังไม่เคยมีก็คืน None"""
    row = await get_pool().fetchrow("""
        SELECT id, line_user_id, name, age_group FROM users
        WHERE line_user_id = $1
    """, line_user_id)
    if row is None:
        return None
    return User(**dict(row))


async def save_user(user: User) -> None:
    """เขียนทับ user ทั้งแถวตาม id — ยังไม่มีก็สร้างใหม่"""
    await get_pool().execute("""
        INSERT INTO users (id, line_user_id, name, age_group)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (id) DO UPDATE SET
            line_user_id = EXCLUDED.line_user_id,
            name         = EXCLUDED.name,
            age_group    = EXCLUDED.age_group
    """, user.id, user.line_user_id, user.name, user.age_group)


## ai config part ##
async def get_active_ai_configs() -> list[dict]:
    """แถวที่ is_active ของทุก agent — คืนเป็น dict ดิบ

    ไม่แปลงเป็น AgentConfig ตรงนี้ เพราะแถวเพี้ยนแถวเดียวจะทำให้ agent ตัวอื่นโหลดไม่ขึ้นไปด้วย
    ให้ services.ai_config แปลงทีละแถวเอง
    """
    rows = await get_pool().fetch("""
        SELECT id, created_at, note, agent, provider, model_name,
               prompt_id, temperature, max_output_tokens
        FROM ai_configuration
        WHERE is_active
    """)
    return [dict(row) for row in rows]


## system setting part ##
async def get_active_system_setting() -> dict | None:
    """แถวที่ is_active — คืน dict ดิบให้ services.system_setting ตรวจเอง ไม่มีก็คืน None"""
    row = await get_pool().fetchrow("""
        SELECT id, created_at, note, session_ttl_seconds
        FROM system_setting
        WHERE is_active
    """)
    return dict(row) if row else None
