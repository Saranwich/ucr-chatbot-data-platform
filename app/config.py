import os
from dotenv import load_dotenv
from pathlib import Path

# base direcroty
BASE_DIR = Path(__file__).resolve().parent.parent
# load from .env
load_dotenv()

CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

#if forget add .env
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise ValueError("CHANNEL_SECRET or CHANNEL_ACCESS_TOKEN not found in .env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("ลืมใส่ DATABASE_URL ในไฟล์ .env")

raw_survey_path = os.getenv("SURVEY_QUESTIONS")
if not raw_survey_path:
    raise ValueError("ลืมใส่ SURVEY_QUESTIONS ในไฟล์ .env")
#safe_relative_path = raw_survey_path.lstrip('/') # ป้องกันกรณีใส่ path แบบ /app/data/survey.json ที่มี / ข้างหน้า
SURVEY_QUESTIONS = str(BASE_DIR / raw_survey_path).lstrip('/') # รวมกับ BASE_DIR และป้องกันกรณีใส่ path แบบ /app/data/survey.json ที่มี / ข้างหน้า

print(SURVEY_QUESTIONS)