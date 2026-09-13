import asyncpg
from app.core.config import DATABASE_URL
from app.schemas.logs import LogsRecord
from app.schemas.report import AiResponse, Image, Location, Message, Report, Session
from app.schemas.turn import Turn
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

    # หนึ่งแถว = prompt หนึ่งเวอร์ชัน ไม่ควรแก้แถวเก่าเพราะจะดู history prompt จะเปลี่ยนแปลง
    # ตัวที่ใช้อยู่คือตัวที่ ai_configuration แถว active ชี้มา — ประวัติ prompt ไปพร้อมประวัติ config
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id         bigserial   PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            note       text,
            content    text        NOT NULL CHECK (content <> '')
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
    # CHECK ตรงกับ Field ใน schemas/system_config.py
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS system_config (
            id                  bigserial   PRIMARY KEY,
            created_at          timestamptz NOT NULL DEFAULT now(),
            note                text,
            is_active           boolean     NOT NULL DEFAULT false,
            session_ttl_seconds integer     NOT NULL CHECK (session_ttl_seconds > 0),
            close_when_ttl_under_seconds integer NOT NULL CHECK (close_when_ttl_under_seconds > 0),
            sweep_interval_seconds       integer NOT NULL CHECK (sweep_interval_seconds > 0)
        )
    """)
    await get_pool().execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS system_config_one_active
            ON system_config (is_active) WHERE is_active
    """)

    # หนึ่งแถว = บทสนทนาหนึ่งรอบ เปิดตอนเขาทักมาแล้วไม่มีรอบไหนค้าง จบเองตอนเงียบจนหมดอายุ
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          uuid        PRIMARY KEY,
            user_id     uuid        NOT NULL,
            status      text        NOT NULL,   -- not_analyzed | pending | analyzed | analysis_failed
            is_finished boolean     NOT NULL,   -- ชาวบ้านบอกว่าเล่าจบแล้ว ตัวกวาดปิดได้เลยไม่ต้องรอเงียบ
            created_at  timestamptz NOT NULL
        )
    """)

    # หนึ่งแถว = ข้อความหนึ่งข้อที่ผู้ใช้ส่งเข้ามา number เริ่มที่ 1 ใหม่ทุก session
    # ไม่มีช่องบอกว่าใครพูด เก็บแต่ฝั่งผู้ใช้ คำตอบของบอทอยู่ใน logs
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         uuid        PRIMARY KEY,
            session_id uuid        NOT NULL,
            number     integer     NOT NULL,
            content    text        NOT NULL,
            created_at timestamptz NOT NULL
        )
    """)
    # อ่านบทสนทนา = หยิบทั้ง session แล้วเรียงตาม number ทางเดียว
    await get_pool().execute("""
        CREATE INDEX IF NOT EXISTS messages_session_number ON messages (session_id, number)
    """)

    # หนึ่งแถว = คำตอบหนึ่งครั้งของโมเดล เก็บว่าใช้ config ไหนเขียน จะได้ย้อนดูได้ว่าทำไมมันตอบแบบนั้น
    # ai_config_id ว่าง = ตอนนั้นไม่มีแถว active ในฐาน แอปใช้ค่า default จาก core/default_value.py
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS ai_responses (
            id           uuid        PRIMARY KEY,
            session_id   uuid        NOT NULL,
            agent        text        NOT NULL,   -- communicator | analyzer | resource_analyzer
            ai_config_id bigint,                 -- ชี้ไป ai_configuration.id แถวที่ใช้ตอนนั้น
            model_name   text        NOT NULL,
            content      text        NOT NULL,
            created_at   timestamptz NOT NULL
        )
    """)

    # หนึ่งแถว = หนึ่งเรื่องที่ analyzer สรุปได้ ยังไม่มีใครเขียนลง รอ analyzer
    # ทุกช่องเนื้อหาว่างได้ ตรงกับ schemas/report.py — เรื่องที่เล่ามาไม่ครบก็ต้องเก็บได้
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id              uuid        PRIMARY KEY,
            created_at      timestamptz NOT NULL,
            status          text        NOT NULL,   -- not_analyzed | pending | analyzed
            session_id      uuid        NOT NULL,
            title           text,
            type            text,                   -- flood | heat | light | other
            threat          text,                   -- not_relate | low | mid | high
            frequency       text,
            effect          text,
            is_has_image    boolean,
            is_has_location boolean
        )
    """)

    # หนึ่งแถว = รูปหนึ่งใบที่ชาวบ้านส่งเข้ามา ตัวไฟล์อยู่บนดิสก์ ในนี้เก็บแค่ที่อยู่ของมัน
    # image_key ว่างได้ = โหลดไฟล์จากไลน์ไม่ทัน แต่ line_image_url ยังพาไปตามเก็บใหม่ได้
    # desc ว่างไว้ก่อน รอ ai ที่อ่านภาพมาเติมทีหลัง
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS images (
            id             uuid    PRIMARY KEY,
            session_id     uuid    NOT NULL,
            number         integer NOT NULL,   -- ข้อความที่เท่าไหร่ใน session ที่รูปติดมาด้วย
            line_image_url text    NOT NULL,
            image_key      text,
            "desc"         text,                -- ต้องใส่ quote เพราะ desc เป็นคำสงวนของ sql
            created_at     timestamptz NOT NULL
        )
    """)

    # หนึ่งแถว = ที่เกิดเรื่องหนึ่งจุด มาได้สองแบบ แชร์พิกัดในไลน์ หรือพิมพ์บอกเป็นคำพูด
    # ได้แบบไหนก็เก็บแบบนั้น อีกแบบว่างไว้ ไม่เดาเติมให้กัน — type บอกว่าแถวนี้ได้แบบไหนมา
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id         uuid    PRIMARY KEY,
            session_id uuid    NOT NULL,
            number     integer NOT NULL,   -- ข้อความที่เท่าไหร่ใน session ที่พิกัดติดมาด้วย
            type       text    NOT NULL,   -- lat_lon | str
            lat        double precision,
            lon        double precision,
            address    text,
            created_at timestamptz NOT NULL
        )
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
    """แถวที่ is_active ของทุก agent พ่วงเนื้อ prompt ที่ชี้ไป — คืนเป็น dict ดิบ

    prompt เป็น None เมื่อ prompt_id ว่าง หรือชี้ไป id ที่ไม่มีในตาราง prompts

    ไม่แปลงเป็น AgentConfig ตรงนี้ เพราะแถวเพี้ยนแถวเดียวจะทำให้ agent ตัวอื่นโหลดไม่ขึ้นไปด้วย
    ให้ services.config.ai_config แปลงทีละแถวเอง
    """
    rows = await get_pool().fetch("""
        SELECT a.id, a.created_at, a.note, a.agent, a.provider, a.model_name,
               a.prompt_id, p.content AS prompt, a.temperature, a.max_output_tokens
        FROM ai_configuration a
        LEFT JOIN prompts p ON p.id = a.prompt_id
        WHERE a.is_active
    """)
    return [dict(row) for row in rows]


## system setting part ##
async def get_active_system_config() -> dict | None:
    """แถวที่ is_active — คืน dict ดิบให้ services.config.system_config ตรวจเอง ไม่มีก็คืน None"""
    row = await get_pool().fetchrow("""
        SELECT id, created_at, note, session_ttl_seconds,
               close_when_ttl_under_seconds, sweep_interval_seconds
        FROM system_config
        WHERE is_active
    """)
    return dict(row) if row else None


## image part ##
async def save_image(image: Image) -> None:
    """เขียนแถวรูปทั้งแถวตาม id — ยังไม่มีก็สร้างใหม่ (คนละตัวกับ storage.save_image ที่เขียนตัวไฟล์)"""
    await get_pool().execute("""
        INSERT INTO images (id, session_id, number, line_image_url, image_key, "desc", created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO UPDATE SET
            session_id     = EXCLUDED.session_id,
            number         = EXCLUDED.number,
            line_image_url = EXCLUDED.line_image_url,
            image_key      = EXCLUDED.image_key,
            "desc"         = EXCLUDED."desc"
    """, image.id, image.session_id, image.number,
         image.line_image_url, image.image_key, image.desc, image.created_at)


async def set_image_desc(image_id, desc: str) -> bool:
    """เติมคำบรรยายให้รูปที่มีอยู่แล้วหนึ่งใบ คืน False ถ้าไม่มีรูป id นี้

    ไม่ INSERT ให้ เพราะแถวรูปเกิดตอนรับมาจากไลน์ ที่นี่มีหน้าที่เติมของที่ ai อ่านได้เท่านั้น
    """
    result = await get_pool().execute(
        'UPDATE images SET "desc" = $2 WHERE id = $1', image_id, desc
    )
    return result != "UPDATE 0"


## location part ##
async def save_location(location: Location) -> None:
    """เขียนแถวพิกัดทั้งแถวตาม id — ยังไม่มีก็สร้างใหม่"""
    await get_pool().execute("""
        INSERT INTO locations (id, session_id, number, type, lat, lon, address, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (id) DO UPDATE SET
            session_id = EXCLUDED.session_id,
            number     = EXCLUDED.number,
            type       = EXCLUDED.type,
            lat        = EXCLUDED.lat,
            lon        = EXCLUDED.lon,
            address    = EXCLUDED.address
    """, location.id, location.session_id, location.number, location.type,
         location.lat, location.lon, location.address, location.created_at)


## session part ##
async def save_session(session: Session) -> None:
    """เปิดบทสนทนารอบใหม่ลงฐาน — id ซ้ำก็เขียนทับ"""
    await get_pool().execute("""
        INSERT INTO sessions (id, user_id, status, is_finished, created_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET user_id = EXCLUDED.user_id
    """, session.id, session.user_id, session.status, session.is_finished, session.created_at)


## message part ##
async def save_message(message: Message) -> None:
    """เก็บข้อความที่ผู้ใช้ส่งเข้ามาหนึ่งข้อ — id ซ้ำก็เขียนทับ"""
    await get_pool().execute("""
        INSERT INTO messages (id, session_id, number, content, created_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET
            session_id = EXCLUDED.session_id,
            number     = EXCLUDED.number,
            content    = EXCLUDED.content
    """, message.id, message.session_id, message.number, message.content, message.created_at)


## ai response part ##
async def save_ai_response(response: AiResponse) -> None:
    """เก็บคำตอบของโมเดลหนึ่งครั้ง"""
    await get_pool().execute("""
        INSERT INTO ai_responses (id, session_id, agent, ai_config_id, model_name, content, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO NOTHING
    """, response.id, response.session_id, response.agent,
         response.ai_config_id, response.model_name,
         response.content, response.created_at)


## conversation part ##
async def get_conversation(session_id) -> list[Turn]:
    """ประกอบบทสนทนาทั้งรอบคืนจากฐาน เรียงตามเวลาจริง ฝั่งผู้ใช้กับฝั่งบอทสลับกันตามที่เกิดขึ้น

    อ่านจากฐาน ไม่ใช่ redis เพราะ redis หายไปแล้วตอน analyzer ทำงาน
    content_type เป็น text หมดเพราะฐานไม่ได้เก็บว่าตาไหนมาจากรูปหรือพิกัด
    ตัวข้อความบอกอยู่แล้วด้วยป้าย [got image from user] / [got location from user]
    """
    rows = await get_pool().fetch("""
        SELECT created_at, 'user'      AS role, content FROM messages     WHERE session_id = $1
        UNION ALL
        SELECT created_at, 'assistant' AS role, content FROM ai_responses WHERE session_id = $1
        ORDER BY created_at
    """, session_id)
    return [Turn(role=row["role"], content_type="text", content=row["content"]) for row in rows]


async def get_session(session_id) -> Session | None:
    """หยิบ session หนึ่งรอบตาม id — ไม่มีก็คืน None"""
    row = await get_pool().fetchrow("""
        SELECT id, user_id, status, is_finished, created_at FROM sessions WHERE id = $1
    """, session_id)
    if row is None:
        return None
    return Session(**dict(row))


async def set_session_status(session_id, status: str) -> None:
    """เปลี่ยนสถานะ session — analyzed ตอนวิเคราะห์เสร็จ not_analyzed ตอนพังเพื่อให้ลองใหม่ได้"""
    await get_pool().execute("UPDATE sessions SET status = $2 WHERE id = $1", session_id, status)


async def set_session_finished(session_id, is_finished: bool) -> bool:
    """ปักหรือถอนธงว่าบทสนทนารอบนี้เล่าจบแล้ว คืน False ถ้าไม่มี session นี้ในฐาน

    ต้องถอนได้ ไม่ใช่ปักทางเดียว เพราะรอบก่อนอาจดูเหมือนจะจบแล้วเขาพูดต่อ
    เขียนค่าเดิมซ้ำก็ไม่เป็นไร ไม่ได้นับว่าปักกี่ครั้ง
    """
    result = await get_pool().execute(
        "UPDATE sessions SET is_finished = $2 WHERE id = $1", session_id, is_finished
    )
    return result != "UPDATE 0"


## report part ##
async def save_report(report: Report) -> None:
    """เขียนหนึ่งเรื่องที่ analyzer สรุปได้ — id ซ้ำก็เขียนทับ

    หนึ่ง session มีได้หลายแถว เพราะบทสนทนาเดียวชาวบ้านเล่าได้หลายเรื่อง
    ช่องเนื้อหาว่างได้หมด ว่าง = ยังไม่ได้ถาม ไม่ใช่ไม่มี
    """
    await get_pool().execute("""
        INSERT INTO reports (id, created_at, status, session_id, title, type,
                             threat, frequency, effect, is_has_image, is_has_location)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT (id) DO UPDATE SET
            status          = EXCLUDED.status,
            title           = EXCLUDED.title,
            type            = EXCLUDED.type,
            threat          = EXCLUDED.threat,
            frequency       = EXCLUDED.frequency,
            effect          = EXCLUDED.effect,
            is_has_image    = EXCLUDED.is_has_image,
            is_has_location = EXCLUDED.is_has_location
    """, report.id, report.created_at, report.status, report.session_id,
         report.title, report.type, report.threat, report.frequency,
         report.effect, report.is_has_image, report.is_has_location)
