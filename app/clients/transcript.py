"""บทสนทนาต้นฉบับ — ของดิบที่ AI สกัดมาเป็นรายงาน

ทำไมต้องเก็บ: รายงานที่ลง DB คือสิ่งที่ AI *สรุป* ให้ ถ้าวันหลังเราปรับวิธีสกัด
หรืออยากได้ช่องใหม่ย้อนหลัง ต้องมีต้นฉบับให้สกัดใหม่ ไม่งั้นข้อมูลที่เก็บไปแล้ว
กู้คืนไม่ได้ถาวร

**ตัวบทสนทนาไม่ลง Postgres** ลงแต่ key ที่ `reports.transcript_key` แบบเดียวกับรูป
ตอนนี้ไฟล์อยู่ใน storage/ ของจริงจะขึ้น S3 — วันย้ายแก้แค่ในไฟล์นี้

    s3://<bucket>/transcripts/YYYY/MM/<report_id>-<เวลา>.json

**ชื่อไฟล์มีเวลาต่อท้าย ไม่ได้มีแค่ report_id** เพราะ id เริ่มนับ 1 ใหม่ทุกครั้ง
ที่สร้างฐานใหม่ ตอนที่ชื่อเป็น `<report_id>.json` เฉย ๆ ต้นฉบับของใบเก่าถูกทับ
เงียบ ๆ ด้วยใบใหม่ที่บังเอิญได้ id เดียวกัน — เกิดขึ้นแล้วจริง 7 ส.ค. 69
ต้นฉบับที่ถูกทับได้เงียบ ๆ ทำหน้าที่ "ของดิบไว้สกัดใหม่" ไม่ได้เลย

(save เป็น async ตั้งแต่ตอนนี้ เพราะ boto3/aioboto3 เป็น I/O จริง คนเรียกจะได้ไม่ต้องแก้)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import BASE_DIR

# storage/ ไม่ใช่ local/ — เหตุผลเดียวกับ clients/media.py
STORE_DIR = BASE_DIR / "storage"


async def save(session_id: str, report_id: int, messages: list[dict]) -> str:
    """เก็บบทสนทนา 1 ชุด คืน key ที่เก็บไว้ (ทีหลังจะเป็น S3 key)

    key ต่อท้าย STORE_DIR แล้วได้ path ของไฟล์เลย กติกาเดียวกับ clients/media.py
    ไม่มีกฎแปลงชื่ออะไรคั่นกลาง เพราะสิ่งที่ลง DB คือ key ล้วน ๆ
    """
    now = datetime.now(timezone.utc)
    key = f"transcripts/{now:%Y/%m}/{report_id}-{now:%Y%m%d%H%M%S}.json"

    path = STORE_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            {
                "report_id": report_id,
                "session_id": session_id,
                "saved_at": now.isoformat(),
                "messages": messages,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return key


def local_file(key: str) -> Path | None:
    """key -> ไฟล์บนเครื่อง คืน None ถ้าไม่มีไฟล์นั้น

    **ที่เดียวในโปรเจกต์ที่แปลง key ของต้นฉบับเป็น path ได้** เหมือน media.py
    วันย้ายขึ้น S3 ฟังก์ชันนี้จะกลายเป็นตัวดึงจาก bucket แทน
    """
    path = (STORE_DIR / key).resolve()
    if not path.is_relative_to(STORE_DIR.resolve()):
        # key มาจากฐานข้อมูลของเราเอง ไม่ควรมีทางหลุดออกนอกโฟลเดอร์
        # แต่ตรงนี้เป็นทางที่เปิดไฟล์จากค่าที่รับมา ไม่ควรเชื่อใครทั้งนั้น
        return None
    return path if path.is_file() else None
