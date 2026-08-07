-- ตารางของ Postgres — รันมือครั้งเดียวตอนตั้งเครื่องใหม่
--
--     psql "$DATABASE_URL" -f schema.sql
--
-- แอปไม่สร้างตารางให้เองตอนเปิด ตั้งใจให้เป็นแบบนั้น เพราะโค้ดที่แก้ schema ได้
-- ระหว่างรันคือโค้ดที่ทำ schema พังได้ระหว่างรันเหมือนกัน
--
-- ไม่มี IF NOT EXISTS เพราะรันซ้ำควรพังให้เห็น ดีกว่าเงียบแล้วปล่อยให้ตารางเก่า
-- ที่หน้าตาไม่ตรงกับไฟล์นี้อยู่ต่อไป

CREATE EXTENSION IF NOT EXISTS postgis;


CREATE TABLE reports (
    id            bigserial   PRIMARY KEY,
    session_id    text        NOT NULL,               -- LINE user id
    source        text        NOT NULL DEFAULT 'user', -- user | rescued | broadcast
    created_at    timestamptz NOT NULL DEFAULT now(),

    -- สองช่องนี้เท่านั้นที่บังคับ ตรงกับ missing() ใน services/survey.py
    --
    -- categories ติดได้หลายอันต่อหนึ่งใบ เพราะเรื่องเดียวกันในจุดเดียวมักมีหลายอย่าง
    -- ("น้ำท่วมแล้วกลางคืนไฟก็มืด") **ตัวแรกคือเรื่องหลัก** หมุดบนแผนที่มีสีเดียว
    -- จึงต้องมีกฎว่าใครได้สี — ดู CATEGORIES ใน services/survey.py
    categories    text[]      NOT NULL,               -- heat|flood|access|lighting|waste|other
    notes         text        NOT NULL,               -- ฉบับเรียบเรียงให้ทีมอ่าน

    title         text,                               -- พาดหัวบนหมุด
    severity      text,                               -- low | medium | high
    affect_desc   text,
    affect_tags   text[],                             -- health safety mobility property income daily_life
    frequency     text,                               -- once | occasional | recurring
    time_of_day   text[],                             -- morning afternoon evening night

    -- คำพูดของชาวบ้านตรง ๆ รวมภาษาถิ่น **ห้าม normalize** ฉบับเรียบเรียงอยู่ที่ notes แล้ว
    cause_said    text,
    occurred_said text,

    -- geom มาจาก ST_MakePoint(longitude, latitude) — longitude มาก่อน
    -- แถวที่ไม่มี geom ไม่ขึ้นเป็นหมุด แต่ยังนับสถิติได้ ทีมปักมือทีหลังได้
    geom          geography(Point, 4326),
    location_text text,                               -- ที่อยู่แบบพูด ตอนแชร์พิกัดไม่ได้

    -- แยก "เขาปฏิเสธเอง" ออกจาก "คุยค้างแล้วหายไป" — คนละเรื่องกันสำหรับทีมออกแบบ
    no_location   boolean     NOT NULL DEFAULT false,
    no_photo      boolean     NOT NULL DEFAULT false,

    -- บทสนทนาต้นฉบับที่ AI สกัดใบนี้ออกมา **เก็บแต่ key ตัวบทไม่ลงตารางนี้**
    -- กติกาเดียวกับ report_images.image_key — ห้ามใครนอก clients/transcript.py
    -- เอาไปต่อกับชื่อโฟลเดอร์ นั่นคือทั้งหมดของแผนย้ายขึ้น S3
    -- null ได้: ใบเก่าที่ปิดก่อนมีช่องนี้ และใบที่เก็บต้นฉบับไม่สำเร็จ
    transcript_key text                               -- transcripts/YYYY/MM/<id>-<เวลา>.json
);

-- ไม่มี CHECK constraint ที่ categories / severity / frequency ทั้งที่ใส่ได้
-- เพราะ _sanitize() ใน services/survey.py กรองค่านอกรายการทิ้งก่อนถึงตรงนี้แล้ว
-- ถ้าใส่ CHECK ค่าเพี้ยนช่องเดียวจะทำ INSERT ล้มทั้งแถว = เสียเรื่องที่เขาอุตส่าห์เล่าทั้งใบ
-- ชั้นแอปกรอง ชั้นนี้รับ

CREATE INDEX reports_geom_idx    ON reports USING GIST (geom);
CREATE INDEX reports_session_idx ON reports (session_id, created_at DESC);


CREATE TABLE report_images (
    id         bigserial   PRIMARY KEY,
    report_id  bigint      NOT NULL REFERENCES reports(id) ON DELETE CASCADE,

    -- key ไม่ใช่ path — ห้ามใครนอก clients/media.py เอาไปต่อกับชื่อโฟลเดอร์
    -- นั่นคือทั้งหมดของแผนย้ายขึ้น S3
    image_key  text        NOT NULL,                  -- images/YYYY/MM/xxx.jpg
    descr      text,                                  -- เรื่องที่คุยกันอยู่ตอนรูปมาถึง
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX report_images_report_idx ON report_images (report_id);


-- ================================================================ broadcast
--
-- สามตารางล่างนี้มีไว้ตอบคำถามเดียว: **จะยิงข้อความไปหาใคร**
--
-- ทางฝั่งรับเรื่อง (reports) ไม่ต้องรู้จักใครเลย session_id พอแล้ว แต่ broadcast
-- เป็นเราเป็นฝ่ายเปิดเรื่องก่อน เลยต้องรู้ล่วงหน้าว่าใครอยู่ตรงไหน
--
-- **แถวใน users เกิดจากบทสนทนา ไม่ได้เกิดจากฟอร์ม** บอทถามเองว่าอยู่ชุมชนไหน
-- ระหว่างที่คุยเรื่องตำแหน่ง แล้ว survey.py เอามาลงให้ตอนปิดใบ — ไม่มีหน้ากรอกโปรไฟล์
-- และ **ไม่รู้ชุมชนก็ปิดใบได้ตามปกติ** ช่องนี้ไม่ได้อยู่ใน missing()


CREATE TABLE communities (
    id        bigserial PRIMARY KEY,
    name      text      NOT NULL UNIQUE,     -- ชื่อที่ใช้จริง สะกดแบบนี้ที่เดียว

    -- พิกัดกลางชุมชน ยังว่างอยู่ทั้ง 14 แถว — **ต้องเติมก่อนทำ forecast**
    -- เฟสแรกคนกดเลือกชุมชนเอง ยังไม่ต้องใช้ แต่วันที่ให้พยากรณ์เป็นคนเลือก
    -- มันต้องจับคู่จุดในไฟล์ forecast กับชุมชนด้วยระยะทาง ตรงนั้นถึงจะขาดไม่ได้
    lat       double precision,
    lon       double precision,

    -- ชุมชนที่เลิกยิงแล้ว ไม่ลบทิ้ง เพราะ outreach เก่ายังอ้างถึงอยู่
    is_active boolean   NOT NULL DEFAULT true
);


CREATE TABLE users (
    session_id   text        PRIMARY KEY,    -- ตัวเดียวกับ reports.session_id
    community_id bigint,                     -- ชี้ไป communities.id — null = ยังไม่รู้

    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- คำถามเดียวที่ตารางนี้ต้องตอบให้เร็ว: "ชุมชนนี้มีใครบ้าง"
CREATE INDEX users_community_idx ON users (community_id);


-- 1 ครั้งที่ทักไป = 1 แถว **ตอบให้ได้ว่าทักไปกี่คน มีใครตอบกลับบ้าง**
--
-- ของเดิม V2 มีตารางนี้แต่ไม่เคยเขียนช่อง response เลยสักครั้ง ผลคือตอบคำถาม
-- พื้นฐานที่สุดไม่ได้ — ทักไป 100 คน มีคนตอบกี่คน — ซึ่งเป็นตัวเลขเดียวที่ใช้เคาะ
-- เรื่องความถี่ได้อย่างมีหลักฐาน คราวนี้เขียนตั้งแต่วันแรก
CREATE TABLE outreach (
    id           bigserial   PRIMARY KEY,
    session_id   text        NOT NULL,
    community_id bigint,
    topic        text        NOT NULL,       -- flood | heat | both
    sent_at      timestamptz NOT NULL DEFAULT now(),

    -- ตัวข้อความที่ส่งไปจริง — **AI แต่งใหม่ทุกครั้ง ไม่มีสองรอบที่เหมือนกัน**
    -- ไม่เก็บไว้ก็ไม่มีวันรู้ว่าที่เขาตอบมานั้นเขาตอบอะไรอยู่
    message      text,

    -- null = เมินเงียบ (คำตอบที่พบบ่อยที่สุด และเป็นคำตอบที่มีความหมาย)
    -- ไม่มีปุ่มให้กด เลยไม่มี "รับ/ปฏิเสธ" — ตอบมาก็คือตอบ
    -- ส่วนคำถามว่าได้เรื่องกลับมาไหม ดูที่ report_id
    response     text,                       -- replied
    responded_at timestamptz,
    report_id    bigint                      -- ใบที่งอกจากการตอบครั้งนี้ ถ้ามี
);

-- ไม่มี FK ทั้งสามตาราง ด้วยเหตุผลเดียวกับ reports:
-- outreach เป็นสมุดบันทึกว่าเรายิงอะไรไปแล้ว **แถวที่เขียนไม่ลงคือแถวที่หายไปเลย**
-- ลบชุมชนทิ้งแล้วประวัติการยิงล้มตามทั้งก้อน เสียมากกว่าได้
-- ส่วน users.community_id แอปหาเลขมาจากตาราง communities อยู่แล้ว ค่าเพี้ยนไม่ได้

-- cap กันสแปม: "ยิงหาคนนี้ล่าสุดเมื่อไหร่" ต้องตอบได้ก่อนยิงทุกครั้ง
CREATE INDEX outreach_session_idx   ON outreach (session_id, sent_at DESC);
CREATE INDEX outreach_community_idx ON outreach (community_id, sent_at DESC);


-- 14 ชุมชนหลักสี่ ยกมาจาก lookups.COMMUNITIES ของ V2 ซึ่งยกมาจาก dropdown
-- ในหน้าโปรไฟล์อีกที — เคยสะกดกันคนละแบบสามที่ ตอนนี้เหลือที่เดียวคือแถวพวกนี้
INSERT INTO communities (name) VALUES
    ('ชุมชนคนรักถิ่น'),
    ('ชุมชนหลังแฟลตร่วมพัฒนา'),
    ('ชุมชนหลักสี่พัฒนา 99'),
    ('ชุมชนคลองเปรมประชาพัฒนา'),
    ('ชุมชนศิษย์หลวงปู่ขาว'),
    ('ชุมชนตลาดหลักสี่'),
    ('ชุมชนแจ้งวัฒนะซอย 5'),
    ('ชุมชนมิตรประชาพัฒนา'),
    ('ชุมชนอยู่แล้วรวย'),
    ('ชุมชนอยู่ดีมีสุขร่วมใจ'),
    ('ชุมชนเทวสุนทร'),
    ('ชุมชนสามัคคีเทวสุนทร'),
    ('ชุมชนประชาร่วมใจ 1'),
    ('ชุมชนประชาร่วมใจ 2');
