import os
import app.config_loader
from pathlib import Path

# base direcroty and load from .env
BASE_DIR = Path(__file__).resolve().parent.parent

CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
LIFF_REPORT_URL = os.getenv("LIFF_REPORT_URL")
SURVEYS_DIR = BASE_DIR / "app" / "data" / "surveys"
IMAGES_DIR = BASE_DIR / "app" / "data" / "images"

#add question file path here
SURVEY_TRIGGER_MAP = {
    "เริ่มทำแบบสำรวจ": "community_report_v1",
    "devtest": "devtest",
    # อนาคตถ้ามีโปรเจกต์ใหม่ แค่มาเพิ่มตรงนี้ เช่น "รายงานน้ำท่วม": "flood_v2"
}

# Static Reply Messages
PROJECT_INFO_TEXT = (
    "🏢 โครงการ UCR Smart City Chatbot\n"
    "เราใช้ข้อมูลจากท่านเพื่อนำไปออกแบบผังเมืองและชุมชนให้มีคุณภาพชีวิตที่ดีขึ้น\n\n"
    "ขอบคุณที่เป็นส่วนหนึ่งในการพัฒนาเมืองของเราครับ!"
)

REPORT_DEVELOPMENT_TEXT = "📝 ระบบรายงานปัญหา (Report) กำลังอยู่ระหว่างการพัฒนาเป็นรูปแบบ Website (LIFF) ครับ"
SUMMARY_PLACEHOLDER_TEXT = "📊 ระบบสรุปผลกำลังอยู่ระหว่างการพัฒนา จะพร้อมให้ใช้งานเร็วๆ นี้ครับ"

#if forget add .env
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise ValueError("CHANNEL_SECRET or CHANNEL_ACCESS_TOKEN not found in .env")

if not DATABASE_URL:
    raise ValueError("ลืมใส่ DATABASE_URL ในไฟล์ .env")

if not LIFF_REPORT_URL:
    print("⚠️ Warning: LIFF_REPORT_URL not found in .env. Report button will not work.")
