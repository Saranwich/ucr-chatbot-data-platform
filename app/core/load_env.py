import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# ชื่อ -> เอาไว้ทำอะไร (โชว์ตอนขาด ให้คนตั้งเครื่องรู้ว่าต้องไปหาค่าจากไหน)
REQUIRED = {
    "DATABASE_URL": "postgres ที่เก็บ users / logs / ai_configuration / system_setting",
    "REDIS_URL": "redis ที่เก็บบทสนทนาที่ยังคุยค้าง",
    "LINE_CHANNEL_SECRET": "ตรวจลายเซ็น webhook ของ LINE",
    "LINE_CHANNEL_ACCESS_TOKEN": "ยิงข้อความตอบกลับทาง LINE",
    "TYPHOON_API_KEY": "เรียกโมเดลของ typhoon",
}

_missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
if _missing:
    width = max(len(name) for name in _missing)
    lines = "\n".join(f"  - {name.ljust(width)}  {REQUIRED[name]}" for name in _missing)
    print(
        f"\n.env ขาด {len(_missing)} ค่าที่แอปขาดไม่ได้ เปิดแอปไม่ได้:\n{lines}\n\nดูชื่อได้ที่ .env.example\n",
        file=sys.stderr,
    )
    raise SystemExit(1)

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
TYPHOON_API_KEY = os.environ["TYPHOON_API_KEY"]

# from load_env import * ส่งออกแค่ของลับ ไม่ลาก os / sys / ตัวช่วยไปด้วย
__all__ = list(REQUIRED)
