import os
from dotenv import load_dotenv
from pathlib import Path

# base direcroty and load from .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()

CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
SURVEYS_DIR = BASE_DIR / "app" / "data" / "surveys"
IMAGES_DIR = BASE_DIR / "app" / "data" / "images"

#add question file path here
SURVEY_TRIGGER_MAP = {
    "เริ่มทำแบบสำรวจ": "devtest_message_01",
    "devtest": "devtest_message_02"
    # อนาคตถ้ามีโปรเจกต์ใหม่ แค่มาเพิ่มตรงนี้ เช่น "รายงานน้ำท่วม": "flood_v2"
}

#if forget add .env
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise ValueError("CHANNEL_SECRET or CHANNEL_ACCESS_TOKEN not found in .env")

if not DATABASE_URL:
    raise ValueError("ลืมใส่ DATABASE_URL ในไฟล์ .env")
