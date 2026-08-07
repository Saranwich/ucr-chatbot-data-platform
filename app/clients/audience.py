"""ทะเบียนว่าใครอยู่ชุมชนไหน + สมุดบันทึกว่าเคยทักใครไปแล้ว

`storage.py` เก็บ**เรื่องที่เขาเล่า** ไฟล์นี้เก็บ**ตัวคน** แยกกันเพราะทางรับเรื่อง
ไม่ต้องรู้จักใครเลย มี session_id ก็พอ ส่วน broadcast เป็นเราเปิดเรื่องก่อน
เลยต้องรู้ล่วงหน้าว่าจะพูดกับใคร

ตารางอยู่ที่ `schema.sql` เหมือนกัน — communities / users / outreach

**ไฟล์นี้ไม่ตัดสินอะไรทั้งนั้น** cap กี่วัน ยิงซ้ำได้ไหม เป็นเรื่องของ
services/broadcast.py ตรงนี้ตอบแค่ว่า "ยิงล่าสุดเมื่อไหร่" แล้วจบ
"""

import asyncpg


async def communities(pool: asyncpg.Pool) -> list[dict]:
    """ชุมชนที่ยังเปิดอยู่ ทั้งชื่อและพิกัดกลาง (พิกัดยังว่างจนกว่าจะทำ forecast)"""
    rows = await pool.fetch(
        "SELECT id, name, lat, lon FROM communities WHERE is_active ORDER BY id"
    )
    return [dict(row) for row in rows]


async def community_names(pool: asyncpg.Pool) -> list[str]:
    """ชื่อล้วน ๆ — ตัวนี้ไปเป็นรายการค่าที่โมเดลเลือกได้ตอนถามว่าอยู่ชุมชนไหน"""
    return [row["name"] for row in await pool.fetch(
        "SELECT name FROM communities WHERE is_active ORDER BY id"
    )]


async def community_id(pool: asyncpg.Pool, name: str) -> int | None:
    """ชื่อ → เลข คืน None ถ้าไม่มีชุมชนชื่อนี้ (หรือปิดไปแล้ว)"""
    return await pool.fetchval(
        "SELECT id FROM communities WHERE name = $1 AND is_active", name
    )


async def community_of(pool: asyncpg.Pool, session_id: str) -> str | None:
    """คนนี้อยู่ชุมชนไหน คืน None ถ้ายังไม่เคยบอก

    ตัวนี้ถูกถามทุกตาของบทสนทนา เพื่อบอกโมเดลว่ายังต้องถามอยู่ไหม —
    ต้องถูกและเร็ว ไม่ใช่เดาจากที่อื่น
    """
    return await pool.fetchval(
        """
        SELECT c.name
          FROM users u
          JOIN communities c ON c.id = u.community_id
         WHERE u.session_id = $1
        """,
        session_id,
    )


async def set_community(pool: asyncpg.Pool, session_id: str, name: str) -> bool:
    """จำว่าคนนี้อยู่ชุมชนไหน คืน False ถ้าไม่รู้จักชื่อนี้ (ไม่เขียนอะไรเลย)

    **เขียนทับได้** เขาย้ายบ้านได้ และครั้งแรกอาจตอบผิด ค่าล่าสุดคือค่าที่ใช้
    """
    found = await community_id(pool, name)
    if found is None:
        return False

    await pool.execute(
        """
        INSERT INTO users (session_id, community_id) VALUES ($1, $2)
        ON CONFLICT (session_id)
        DO UPDATE SET community_id = $2, updated_at = now()
        """,
        session_id,
        found,
    )
    return True


async def members(pool: asyncpg.Pool, community_id: int) -> list[str]:
    """session_id ทุกคนในชุมชนนี้ — นี่คือรายชื่อผู้รับของรอบยิงหนึ่งรอบ"""
    return [row["session_id"] for row in await pool.fetch(
        "SELECT session_id FROM users WHERE community_id = $1 ORDER BY session_id",
        community_id,
    )]


# ------------------------------------------------------------ สมุดการยิง


async def log_push(
    pool: asyncpg.Pool,
    session_id: str,
    topic: str,
    community_id: int | None,
    message: str,
) -> int:
    """ทัก 1 ครั้ง = 1 แถว คืน id ไว้ผูกกับคำตอบทีหลัง

    เก็บตัวข้อความไปด้วยเพราะ **AI แต่งใหม่ทุกครั้ง** ไม่เก็บก็ไม่มีวันรู้ว่า
    ที่เขาตอบมานั้นเขากำลังตอบอะไรอยู่
    """
    return await pool.fetchval(
        """
        INSERT INTO outreach (session_id, topic, community_id, message)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        session_id,
        topic,
        community_id,
        message,
    )


async def last_push_at(pool: asyncpg.Pool, session_id: str):
    """ยิงหาคนนี้ล่าสุดเมื่อไหร่ คืน None ถ้าไม่เคยยิง (คนที่เพิ่งเข้ามา)"""
    return await pool.fetchval(
        "SELECT max(sent_at) FROM outreach WHERE session_id = $1", session_id
    )


async def community_last_push_at(pool: asyncpg.Pool, community_id: int):
    """ยิงเข้าชุมชนนี้ล่าสุดเมื่อไหร่ ไม่ว่าจะเป็นคนไหน

    ของเดิมมี cap แค่ระดับคน ผลคือวันนี้ยิงกลุ่ม A พรุ่งนี้ยิงกลุ่ม B
    คนในชุมชนเดียวกันโดนทักทุกวันได้ แค่เป็นคนละคน — ต้องกันที่ระดับนี้ด้วย
    """
    return await pool.fetchval(
        "SELECT max(sent_at) FROM outreach WHERE community_id = $1", community_id
    )


async def recent_pushes(pool: asyncpg.Pool, limit: int = 30) -> list[dict]:
    """ทักใครไปบ้างล่าสุด เขาตอบไหม ได้เรื่องกลับมาไหม — หน้าเว็บเอาไปแสดง"""
    rows = await pool.fetch(
        """
        SELECT o.id, o.session_id, o.topic, o.message, o.sent_at,
               o.response, o.responded_at, o.report_id, c.name AS community
          FROM outreach o
          LEFT JOIN communities c ON c.id = o.community_id
      ORDER BY o.sent_at DESC
         LIMIT $1
        """,
        limit,
    )
    return [dict(row) for row in rows]


async def known(pool: asyncpg.Pool) -> list[dict]:
    """ทุกคนที่เคยคุยกับเรา พร้อมชุมชนและวันที่ทักล่าสุด — ไว้ให้หน้าเว็บเลือกคน

    เอามาจาก reports ด้วย ไม่ใช่แค่ users **เพราะคนที่ยังไม่บอกชุมชนก็ทักได้**
    ถ้าเอาแต่ users คนที่เล่าเรื่องมาแล้วแต่ไม่ยอมบอกชุมชนจะหายไปจากสายตา
    """
    rows = await pool.fetch(
        """
        WITH seen AS (
            SELECT session_id FROM users
            UNION
            SELECT DISTINCT session_id FROM reports
        )
        SELECT s.session_id,
               c.name                    AS community,
               count(r.id)               AS reports,
               max(r.created_at)         AS last_report,
               (SELECT max(sent_at) FROM outreach o
                 WHERE o.session_id = s.session_id) AS last_push
          FROM seen s
          LEFT JOIN users u      ON u.session_id = s.session_id
          LEFT JOIN communities c ON c.id = u.community_id
          LEFT JOIN reports r     ON r.session_id = s.session_id
      GROUP BY s.session_id, c.name
      ORDER BY max(r.created_at) DESC NULLS LAST
        """
    )
    return [dict(row) for row in rows]


async def mark_response(
    pool: asyncpg.Pool, outreach_id: int, response: str, report_id: int | None = None
) -> bool:
    """บันทึกคำตอบ คืน False ถ้าแถวนี้ตอบไปแล้ว

    `response IS NULL` ใน WHERE ไม่ใช่ของประดับ — **ปุ่มบนการ์ดค้างอยู่ในแชท
    ตลอดไป กดซ้ำได้ เลื่อนขึ้นไปกดกลับได้ และฝั่ง LINE สั่ง disable ไม่ได้**
    ด่านเดียวที่มีคือตรงนี้ คำตอบแรกเท่านั้นที่นับ
    """
    done = await pool.execute(
        """
        UPDATE outreach
           SET response = $2, responded_at = now(),
               report_id = COALESCE($3, report_id)
         WHERE id = $1 AND response IS NULL
        """,
        outreach_id,
        response,
        report_id,
    )
    return done != "UPDATE 0"


async def attach_report(pool: asyncpg.Pool, outreach_id: int, report_id: int) -> None:
    """ผูกใบที่เกิดจากการทักครั้งนั้นเข้ากับแถวการทัก

    แยกจาก mark_response เพราะคนละจังหวะกัน: เขากดปุ่มตอบทันที ส่วนใบ
    กว่าจะปิดคืออีกหลายตาถัดไป — และหลายบทสนทนาก็ไม่มีวันปิดใบเลย
    """
    await pool.execute(
        "UPDATE outreach SET report_id = $2 WHERE id = $1 AND report_id IS NULL",
        outreach_id,
        report_id,
    )
