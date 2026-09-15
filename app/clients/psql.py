from uuid import UUID, uuid4

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
            close_when_ttl_under_seconds integer NOT NULL DEFAULT 600
                CHECK (close_when_ttl_under_seconds > 0), -- legacy, runtime ไม่อ่านแล้ว
            finished_grace_seconds integer   NOT NULL DEFAULT 60 CHECK (finished_grace_seconds > 0),
            inactive_session_seconds integer NOT NULL DEFAULT 600 CHECK (inactive_session_seconds > 0),
            sweep_interval_seconds       integer NOT NULL CHECK (sweep_interval_seconds > 0),
            broadcast_auto_enabled       boolean NOT NULL DEFAULT false
        )
    """)
    # อัปเกรดฐานเดิมที่สร้างก่อนแยกเวลารอของ "จบแล้ว" กับ "เงียบหาย" และก่อนมีสวิตช์บรอดแคสต์
    # ตารางที่มีอยู่แล้ว CREATE TABLE IF NOT EXISTS ข้ามไปเงียบ ๆ ไม่เติมช่องใหม่ให้
    # ช่องที่ขาดไม่ได้ทำให้ตอนเปิดแอปพัง แต่ไปพังตอน get_active_system_config เลือกช่องนั้น
    # เติมที่นี่ทุกช่องที่เพิ่มหลังตารางเกิดแล้ว ไม่งั้นฐานเก่ากับฐานใหม่จะเป็นคนละรูป
    # close_when_ttl_under_seconds เดิมปล่อยไว้เพื่อไม่ทำ migration แบบลบข้อมูล แต่โค้ดไม่อ่านแล้ว
    await get_pool().execute("""
        ALTER TABLE system_config
            ADD COLUMN IF NOT EXISTS finished_grace_seconds
                integer NOT NULL DEFAULT 60 CHECK (finished_grace_seconds > 0),
            ADD COLUMN IF NOT EXISTS inactive_session_seconds
                integer NOT NULL DEFAULT 600 CHECK (inactive_session_seconds > 0),
            ADD COLUMN IF NOT EXISTS broadcast_auto_enabled
                boolean NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS close_when_ttl_under_seconds
                integer NOT NULL DEFAULT 600 CHECK (close_when_ttl_under_seconds > 0),
            ADD COLUMN IF NOT EXISTS sweep_interval_seconds
                integer NOT NULL DEFAULT 120 CHECK (sweep_interval_seconds > 0)
    """)
    # แยกออกมาอีกคำสั่งเพราะใน ALTER TABLE ก้อนเดียว คำสั่งย่อยทุกอันถูกตีความกับรูปตารางก่อนแก้
    # ALTER COLUMN ที่อ้างช่องซึ่ง ADD COLUMN ข้างบนเพิ่งเติม จะยังมองไม่เห็นแล้วระเบิดทั้ง init_db
    # default ของ sweep ใส่ไว้เพื่อให้เติมช่องลงตารางที่มีแถวอยู่แล้วได้ ถอนทิ้งให้จบที่รูปเดียวกับฐานใหม่
    await get_pool().execute("""
        ALTER TABLE system_config
            ALTER COLUMN close_when_ttl_under_seconds SET DEFAULT 600,
            ALTER COLUMN sweep_interval_seconds DROP DEFAULT
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
    # อัปเกรดฐานเดิมที่สร้างก่อนมีธงจบ ขาดช่องนี้แล้วตัวกวาดพังทุกรอบที่อ่าน session
    # ต้องมี default ตอนเติมเพราะแถวเก่ายังไม่มีค่า แล้วถอนทิ้งให้จบที่รูปเดียวกับฐานที่สร้างใหม่
    await get_pool().execute("""
        ALTER TABLE sessions
            ADD COLUMN IF NOT EXISTS is_finished boolean NOT NULL DEFAULT false
    """)
    await get_pool().execute("ALTER TABLE sessions ALTER COLUMN is_finished DROP DEFAULT")

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
    # รูปหนึ่งใบอาจช่วยอธิบายได้มากกว่าหนึ่ง report และ report หนึ่งเรื่องมีได้หลายรูป
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS report_images (
            report_id uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            image_id  uuid NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            PRIMARY KEY (report_id, image_id)
        )
    """)
    await get_pool().execute("""
        CREATE INDEX IF NOT EXISTS report_images_image_id ON report_images (image_id)
    """)

    # หนึ่งแถว = ที่เกิดเรื่องหนึ่งจุด มาได้สองแบบ แชร์พิกัดในไลน์ หรือพิมพ์บอกเป็นคำพูด
    # ได้แบบไหนก็เก็บแบบนั้น อีกแบบว่างไว้ ไม่เดาเติมให้กัน — type บอกว่าแถวนี้ได้แบบไหนมา
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id         uuid    PRIMARY KEY,
            session_id uuid    NOT NULL,
            report_id  uuid    REFERENCES reports(id) ON DELETE SET NULL,
            number     integer NOT NULL,   -- ข้อความที่เท่าไหร่ใน session ที่พิกัดติดมาด้วย
            type       text    NOT NULL,   -- lat_lon | str
            lat        double precision,
            lon        double precision,
            address    text,
            created_at timestamptz NOT NULL
        )
    """)
    # ฐานเดิมมี locations ก่อนเริ่มผูกพิกัดเข้ากับ report จึงเติมคอลัมน์ให้ตอน startup
    await get_pool().execute("""
        ALTER TABLE locations
            ADD COLUMN IF NOT EXISTS report_id uuid REFERENCES reports(id) ON DELETE SET NULL
    """)
    await get_pool().execute("""
        CREATE INDEX IF NOT EXISTS locations_session_id ON locations (session_id)
    """)
    await get_pool().execute("""
        CREATE INDEX IF NOT EXISTS locations_report_id ON locations (report_id)
    """)

    # หนึ่งแถว = ข้อความหนึ่งฉบับที่แอดมินสั่งส่ง เก็บก่อนยิงเสมอ ล้มกลางทางจะได้รู้ว่าค้างตรงไหน
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id           uuid        PRIMARY KEY,
            text         text        NOT NULL CHECK (text <> ''),
            audience     text        NOT NULL CHECK (audience IN ('all', 'selected')),
            user_ids     uuid[]      NOT NULL DEFAULT '{}',
            status       text        NOT NULL DEFAULT 'sending'
                CHECK (status IN ('sending', 'completed')),
            created_at   timestamptz NOT NULL DEFAULT now(),
            started_at   timestamptz,
            completed_at timestamptz
        )
    """)
    # หนึ่งแถว = ชาวบ้านหนึ่งคนใน broadcast หนึ่งฉบับ retry_key คงที่ ยิงซ้ำด้วยคีย์เดิมไลน์ไม่ส่งซ้ำ
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS broadcast_deliveries (
            id              uuid PRIMARY KEY,
            broadcast_id    uuid NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
            user_id         uuid NOT NULL,
            line_user_id    text NOT NULL,
            retry_key       uuid NOT NULL UNIQUE,
            status          text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'skipped')),
            attempted_at    timestamptz,
            completed_at    timestamptz,
            response_status integer,
            error           text,
            UNIQUE (broadcast_id, user_id)
        )
    """)
    await get_pool().execute("""
        CREATE INDEX IF NOT EXISTS broadcast_deliveries_broadcast_status
        ON broadcast_deliveries (broadcast_id, status)
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
               finished_grace_seconds, inactive_session_seconds, sweep_interval_seconds,
               broadcast_auto_enabled
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
    """เขียนพิกัดที่รับจาก LINE — การรับซ้ำต้องไม่ถอน report ที่ analyzer ผูกไว้แล้ว"""
    await get_pool().execute("""
        INSERT INTO locations (id, session_id, report_id, number, type, lat, lon, address, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (id) DO UPDATE SET
            session_id = EXCLUDED.session_id,
            number     = EXCLUDED.number,
            type       = EXCLUDED.type,
            lat        = EXCLUDED.lat,
            lon        = EXCLUDED.lon,
            address    = EXCLUDED.address
    """, location.id, location.session_id, location.report_id, location.number, location.type,
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
    ตัวข้อความบอกอยู่แล้วด้วยป้าย [got image from user] / [got location from user: location_id=...]
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
async def _save_report(executor, report: Report) -> None:
    """คำสั่งเขียน report ที่ใช้ได้ทั้งกับ pool ปกติและ connection ใน transaction"""
    await executor.execute("""
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


async def save_report(
    report: Report,
    location_ids: list[UUID] | None = None,
    image_ids: list[UUID] | None = None,
) -> UUID | None:
    """เขียนหนึ่งเรื่องที่ analyzer สรุปได้ พร้อมผูกพิกัดและรูปใน transaction เดียว

    หนึ่ง session มีได้หลายแถว เพราะบทสนทนาเดียวชาวบ้านเล่าได้หลายเรื่อง
    ช่องเนื้อหาว่างได้หมด ว่าง = ยังไม่ได้ถาม ไม่ใช่ไม่มี — id ซ้ำก็เขียนทับ

    พิกัดกับรูปต้องอยู่ใน session ของ report รูปต้องมี image_key ยืนยันว่าโหลดลง storage แล้ว
    ล็อกแถวก่อนเขียนเพื่อไม่ให้ analyzer สองงานแย่งพิกัดกัน ของที่ตรวจไม่ผ่านคืน None ไม่เขียนอะไรเลย
    retry ที่พิกัดเดิมเคยผูกไว้แล้วจะใช้ report id เดิมและเขียนทับเนื้อหา
    รูปเป็น many-to-many จึงใช้ตัดสิน reuse ไม่ได้ คนละเรื่องอ้างรูปเดียวกันได้โดยตั้งใจ
    """
    location_ids = location_ids or []
    image_ids = image_ids or []
    if not location_ids and not image_ids:
        await _save_report(get_pool(), report)
        return report.id

    async with get_pool().acquire() as connection:
        async with connection.transaction():
            rows = []
            if location_ids:
                rows = await connection.fetch("""
                    SELECT location.id, location.report_id, report.session_id AS report_session_id
                    FROM locations AS location
                    LEFT JOIN reports AS report ON report.id = location.report_id
                    WHERE location.id = ANY($1::uuid[])
                      AND location.session_id = $2
                      AND location.lat IS NOT NULL
                      AND location.lon IS NOT NULL
                    FOR UPDATE OF location
                """, location_ids, report.session_id)
                if len(rows) != len(location_ids):
                    return None

            if image_ids:
                image_rows = await connection.fetch("""
                    SELECT id
                    FROM images
                    WHERE id = ANY($1::uuid[])
                      AND session_id = $2
                      AND image_key IS NOT NULL
                    FOR UPDATE
                """, image_ids, report.session_id)
                if len(image_rows) != len(image_ids):
                    return None

            existing_report_ids = {row["report_id"] for row in rows if row["report_id"] is not None}
            if len(existing_report_ids) > 1:
                return None
            if any(
                row["report_id"] is not None and row["report_session_id"] != report.session_id
                for row in rows
            ):
                return None

            report_id = next(iter(existing_report_ids), report.id)
            report_to_save = report if report_id == report.id else report.model_copy(update={"id": report_id})

            await _save_report(connection, report_to_save)
            if location_ids:
                result = await connection.execute("""
                    UPDATE locations
                    SET report_id = $1
                    WHERE id = ANY($2::uuid[])
                      AND session_id = $3
                      AND (report_id IS NULL OR report_id = $1)
                """, report_id, location_ids, report.session_id)
                if result != f"UPDATE {len(location_ids)}":
                    raise RuntimeError("จำนวน location ที่ผูกไม่ตรงกับจำนวนที่ตรวจไว้")
            if image_ids:
                await connection.execute("""
                    INSERT INTO report_images (report_id, image_id)
                    SELECT $1, unnest($2::uuid[])
                    ON CONFLICT (report_id, image_id) DO NOTHING
                """, report_id, image_ids)

    return report_id


## broadcast part ##
class UnknownBroadcastUsersError(ValueError):
    def __init__(self, user_ids: list[UUID]):
        self.user_ids = user_ids
        super().__init__("มี user_id ที่ไม่มีอยู่จริง")


_BROADCAST_SQL = """
SELECT b.id, b.text, b.audience, b.user_ids, b.status, b.created_at,
       count(d.id)::int AS recipient_count,
       count(d.id) FILTER (WHERE d.status = 'pending')::int AS pending,
       count(d.id) FILTER (WHERE d.status = 'sending')::int AS sending,
       count(d.id) FILTER (WHERE d.status = 'sent')::int AS sent,
       count(d.id) FILTER (WHERE d.status = 'failed')::int AS failed,
       count(d.id) FILTER (WHERE d.status = 'unknown')::int AS unknown,
       count(d.id) FILTER (WHERE d.status = 'skipped')::int AS skipped
FROM broadcasts b LEFT JOIN broadcast_deliveries d ON d.broadcast_id = b.id
WHERE ($1::uuid IS NULL OR b.id = $1)
GROUP BY b.id
"""


def _broadcast_row(row) -> dict:
    item = dict(row)
    item["user_ids"] = list(item.get("user_ids") or [])
    item["counts"] = {
        key: item.pop(key)
        for key in ("pending", "sending", "sent", "failed", "unknown", "skipped")
    }
    return item


async def save_broadcast(text: str, audience: str, user_ids: list[UUID]) -> UUID:
    """เขียนข้อความพร้อมตรึงรายชื่อผู้รับใน transaction เดียว ยังไม่ยิงอะไรทั้งนั้น

    audience=selected แล้วมี id ที่ไม่มีอยู่จริง = ทิ้งทั้งฉบับ ไม่ส่งบางส่วน
    """
    broadcast_id = uuid4()
    async with get_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute("""
                INSERT INTO broadcasts (id, text, audience, user_ids, status, started_at)
                VALUES ($1, $2, $3, $4, 'sending', now())
            """, broadcast_id, text, audience, user_ids)
            if audience == "all":
                users = await connection.fetch("SELECT id, line_user_id FROM users")
            else:
                users = await connection.fetch("""
                    SELECT id, line_user_id FROM users WHERE id = ANY($1::uuid[])
                """, user_ids)
                found_ids = {row["id"] for row in users}
                missing_ids = [user_id for user_id in user_ids if user_id not in found_ids]
                if missing_ids:
                    raise UnknownBroadcastUsersError(missing_ids)
            await connection.executemany("""
                INSERT INTO broadcast_deliveries (id, broadcast_id, user_id, line_user_id, retry_key)
                VALUES ($1, $2, $3, $4, $5)
            """, [(uuid4(), broadcast_id, row["id"], row["line_user_id"], uuid4()) for row in users])
    return broadcast_id


async def claim_broadcast_recipient(broadcast_id: UUID) -> dict | None:
    """หยิบผู้รับที่ยังไม่ได้ยิงมาหนึ่งคนแล้วปักว่ากำลังส่ง คนที่ถูกหยิบแล้วจะไม่ถูกหยิบซ้ำ"""
    row = await get_pool().fetchrow("""
        UPDATE broadcast_deliveries SET status = 'sending', attempted_at = now()
        WHERE id = (
            SELECT id FROM broadcast_deliveries
            WHERE broadcast_id = $1 AND status = 'pending'
            ORDER BY user_id FOR UPDATE SKIP LOCKED LIMIT 1
        )
        RETURNING id, user_id, line_user_id, retry_key
    """, broadcast_id)
    return dict(row) if row else None


async def finish_broadcast_recipient(
    delivery_id: UUID, status: str, response_status: int | None = None, error: str | None = None
) -> None:
    await get_pool().execute("""
        UPDATE broadcast_deliveries
        SET status = $2, response_status = $3, error = $4, completed_at = now()
        WHERE id = $1 AND status = 'sending'
    """, delivery_id, status, response_status, error)


async def complete_broadcast(broadcast_id: UUID) -> None:
    await get_pool().execute("""
        UPDATE broadcasts SET status = 'completed', completed_at = now()
        WHERE id = $1 AND status = 'sending'
          AND NOT EXISTS (
            SELECT 1 FROM broadcast_deliveries
            WHERE broadcast_id = $1 AND status IN ('pending', 'sending')
          )
    """, broadcast_id)


async def get_broadcast(broadcast_id: UUID, include_recipients: bool = False) -> dict | None:
    row = await get_pool().fetchrow(_BROADCAST_SQL, broadcast_id)
    if row is None:
        return None
    result = _broadcast_row(row)
    if include_recipients:
        rows = await get_pool().fetch("""
            SELECT user_id, status, attempted_at, completed_at, response_status, error
            FROM broadcast_deliveries WHERE broadcast_id = $1 ORDER BY user_id
        """, broadcast_id)
        result["recipients"] = [dict(item) for item in rows]
    return result


async def get_broadcasts(limit: int, offset: int) -> tuple[list[dict], int]:
    rows = await get_pool().fetch(
        _BROADCAST_SQL + " ORDER BY b.created_at DESC LIMIT $2 OFFSET $3", None, limit, offset
    )
    total = await get_pool().fetchval("SELECT count(*)::int FROM broadcasts")
    return [_broadcast_row(row) for row in rows], total


## dashboard part ##
_REPORT_COLUMNS = """
    id, created_at, status, session_id, title, type, threat, frequency,
    effect, is_has_image, is_has_location
"""
# นับวันตามเวลาไทย ไม่ใช่ UTC — ชาวบ้านส่งเรื่องตอนสี่ทุ่มต้องอยู่ในวันเดียวกับที่เขารู้สึก
_PERIOD_START = """
    ((now() AT TIME ZONE 'Asia/Bangkok')::date - ($1::int - 1)) AT TIME ZONE 'Asia/Bangkok'
"""
_REPORT_FILTER = """
    ($1::text IS NULL OR type = $1)
    AND ($2::int IS NULL OR created_at >= (
        ((now() AT TIME ZONE 'Asia/Bangkok')::date - ($2::int - 1)) AT TIME ZONE 'Asia/Bangkok'
    ))
"""


async def count_reports(report_type: str | None, days: int | None) -> int:
    return await get_pool().fetchval(
        f"SELECT count(*) FROM reports WHERE {_REPORT_FILTER}", report_type, days
    )


async def get_reports(
    limit: int, offset: int, report_type: str | None, days: int | None
) -> list[dict]:
    rows = await get_pool().fetch(
        f"""SELECT {_REPORT_COLUMNS} FROM reports
            WHERE {_REPORT_FILTER}
            ORDER BY created_at DESC, id LIMIT $3 OFFSET $4""",
        report_type, days, limit, offset,
    )
    return [dict(row) for row in rows]


async def get_report(report_id: UUID) -> dict | None:
    row = await get_pool().fetchrow(
        f"SELECT {_REPORT_COLUMNS} FROM reports WHERE id = $1", report_id
    )
    return dict(row) if row else None


async def get_locations_of_reports(report_ids: list[UUID]) -> list[dict]:
    rows = await get_pool().fetch("""
        SELECT id, report_id, lat, lon, address
        FROM locations
        WHERE report_id = ANY($1::uuid[])
        ORDER BY created_at, id
    """, report_ids)
    return [dict(row) for row in rows]


async def get_images_of_reports(report_ids: list[UUID]) -> list[dict]:
    rows = await get_pool().fetch("""
        SELECT image.id, relation.report_id, image."desc"
        FROM report_images AS relation
        JOIN images AS image ON image.id = relation.image_id
        WHERE relation.report_id = ANY($1::uuid[])
        ORDER BY image.created_at, image.id
    """, report_ids)
    return [dict(row) for row in rows]


async def get_entity_totals() -> dict:
    row = await get_pool().fetchrow("""
        SELECT (SELECT count(*) FROM users) AS users,
               (SELECT count(*) FROM sessions) AS sessions,
               (SELECT count(*) FROM images) AS images,
               (SELECT count(*) FROM locations) AS locations
    """)
    return dict(row)


async def get_session_status_counts() -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT status, count(*) AS count FROM sessions GROUP BY status ORDER BY status"
    )
    return [dict(row) for row in rows]


async def get_report_media_coverage(days: int) -> dict:
    """นับว่ากี่เรื่องมีรูป มีพิกัด มีทั้งคู่ หรือไม่มีเลย — รูปต้องโหลดลง storage สำเร็จจึงนับ"""
    row = await get_pool().fetchrow(f"""
        WITH period_reports AS (
            SELECT id FROM reports WHERE created_at >= ({_PERIOD_START})
        ), media AS (
            SELECT report.id,
                   EXISTS (
                       SELECT 1 FROM report_images ri
                       JOIN images image ON image.id = ri.image_id
                       WHERE ri.report_id = report.id
                         AND image.image_key IS NOT NULL
                         AND btrim(image.image_key) <> ''
                   ) AS has_image,
                   EXISTS (
                       SELECT 1 FROM locations loc
                       WHERE loc.report_id = report.id
                         AND loc.lat IS NOT NULL
                         AND loc.lon IS NOT NULL
                   ) AS has_location
            FROM period_reports report
        )
        SELECT count(*) AS total,
               count(*) FILTER (WHERE has_image) AS with_image,
               count(*) FILTER (WHERE has_location) AS with_location,
               count(*) FILTER (WHERE has_image AND has_location) AS with_both,
               count(*) FILTER (WHERE NOT has_image AND NOT has_location) AS without_media
        FROM media
    """, days)
    return dict(row)


async def get_report_type_counts(days: int) -> list[dict]:
    rows = await get_pool().fetch(f"""
        SELECT coalesce(type, 'unclassified') AS type, count(*) AS count
        FROM reports
        WHERE created_at >= ({_PERIOD_START})
        GROUP BY coalesce(type, 'unclassified')
        ORDER BY type
    """, days)
    return [dict(row) for row in rows]


async def get_report_daily_counts(days: int) -> list[dict]:
    """วันที่ไม่มีเรื่องเข้าต้องมีแถวเป็นศูนย์ด้วย กราฟจะได้ไม่กระโดดข้ามวัน"""
    rows = await get_pool().fetch(f"""
        WITH days AS (
            SELECT generate_series(
                (now() AT TIME ZONE 'Asia/Bangkok')::date - ($1::int - 1),
                (now() AT TIME ZONE 'Asia/Bangkok')::date,
                interval '1 day'
            )::date AS date
        ), report_counts AS (
            SELECT (created_at AT TIME ZONE 'Asia/Bangkok')::date AS date, count(*) AS count
            FROM reports
            WHERE created_at >= ({_PERIOD_START})
            GROUP BY (created_at AT TIME ZONE 'Asia/Bangkok')::date
        )
        SELECT days.date, coalesce(report_counts.count, 0) AS count
        FROM days LEFT JOIN report_counts USING (date)
        ORDER BY days.date
    """, days)
    return [dict(row) for row in rows]


async def count_users() -> int:
    return await get_pool().fetchval("SELECT count(*) FROM users")


async def get_users(limit: int, offset: int) -> list[dict]:
    rows = await get_pool().fetch("""
        SELECT id, line_user_id, name FROM users
        ORDER BY name NULLS LAST, id LIMIT $1 OFFSET $2
    """, limit, offset)
    return [dict(row) for row in rows]


async def get_image_key(image_id: UUID) -> str | None:
    return await get_pool().fetchval("SELECT image_key FROM images WHERE id = $1", image_id)
