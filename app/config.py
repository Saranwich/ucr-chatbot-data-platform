import os
import app.config_loader
from pathlib import Path

# base direcroty and load from .env
BASE_DIR = Path(__file__).resolve().parent.parent

CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
LIFF_REPORT_URL = os.getenv("LIFF_REPORT_URL")
LIFF_ID = os.getenv("LIFF_ID")  # LIFF app id (from a LINE Login channel, same provider as the bot)
LIFF_USERDATA_ID = os.getenv("LIFF_USERDATA_ID")  # LIFF app id ของหน้าแก้ไขข้อมูลส่วนตัว (channel เดียวกัน คนละ app)
SURVEYS_DIR = BASE_DIR / "app" / "data" / "surveys"
IMAGES_DIR = BASE_DIR / "app" / "data" / "images"

#add question file path here
SURVEY_TRIGGER_MAP = {
    "เริ่มทำแบบสำรวจ": "socratic_community_report_v3",
    "devtest": "devtest",
    "d2":"community_report_v1",
    "flex": "flex_devtest"
    # อนาคตถ้ามีโปรเจกต์ใหม่ แค่มาเพิ่มตรงนี้ เช่น "รายงานน้ำท่วม": "flood_v2"
}

# Control keywords ที่ปุ่ม quick-reply ส่งกลับมา (และรับได้เมื่อผู้ใช้พิมพ์เอง)
# ⚠️ ชั่วคราว: ดู docs/adr/0001-rename-sentinels-to-action-words.md
# ปลายทางคือย้ายไปเป็น PostbackAction data token (issue #18)
GO_BACK_KEYWORD = "ย้อนกลับ"
CONFIRM_KEYWORD = "ยืนยัน"

# Static Reply Messages
PROJECT_INFO_TEXT = (
    "🏢 โครงการ UCR Smart City Chatbot\n"
    "เราใช้ข้อมูลจากท่านเพื่อนำไปออกแบบผังเมืองและชุมชนให้มีคุณภาพชีวิตที่ดีขึ้น\n\n"
    "ขอบคุณที่เป็นส่วนหนึ่งในการพัฒนาเมืองของเราครับ!"
)

REPORT_DEVELOPMENT_TEXT = "📝 ระบบรายงานปัญหา (Report) กำลังอยู่ระหว่างการพัฒนาเป็นรูปแบบ Website (LIFF) ครับ"
SUMMARY_PLACEHOLDER_TEXT = "📊 ระบบสรุปผลกำลังอยู่ระหว่างการพัฒนา จะพร้อมให้ใช้งานเร็วๆ นี้ครับ"

MANUAL_TEXT = (
    "📖 คู่มือการใช้งาน\n\n"
    "วิธีใช้งาน UCR Smart City Chatbot:\n\n"
    "1️⃣ กดปุ่ม 'สำรวจ' เพื่อเริ่มทำแบบสอบถามชุมชน\n"
    "2️⃣ ตอบคำถามแต่ละข้อตามที่ระบบถาม\n"
    "3️⃣ กดปุ่ม 'แจ้งปัญหา' หากพบปัญหาในพื้นที่\n"
    "4️⃣ กดปุ่ม 'แก้ไขข้อมูล' เพื่อแก้ไขข้อมูลส่วนตัว\n\n"
    "💡 พิมพ์ 'ย้อนกลับ' หากต้องการยกเลิกแบบสอบถาม\n\n"
    "* เนื้อหาคู่มือฉบับเต็มจะอัปเดตเร็วๆ นี้"
)

#if forget add .env
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise ValueError("CHANNEL_SECRET or CHANNEL_ACCESS_TOKEN not found in .env")

if not DATABASE_URL:
    raise ValueError("ลืมใส่ DATABASE_URL ในไฟล์ .env")

if not LIFF_REPORT_URL:
    print("⚠️ Warning: LIFF_REPORT_URL not found in .env. Report button will not work.")
