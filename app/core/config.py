from dotenv import load_dotenv
import os
from pathlib import Path



# app/core/config.py -> app/core -> app -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

# **ต้องเป็น base ของช่องทางที่พูดภาษา OpenAI ไม่ใช่ URL ของ endpoint ตัวเดียว**
# ของ Gemini คือ .../v1beta/openai/ ไม่ใช่ .../v1beta/models/<model>:generateContent
# (อันหลังเป็น REST ดั้งเดิมของ Google คนละภาษากับที่ไลบรารีนี้พูด)
# ตั้ง default ไว้ให้ เพราะเป็นค่าที่ถูกอยู่แล้ว ไม่ต้องให้ทุกคนไปจำเอง
API_ENDPOINT = os.getenv(
    "API_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/openai/"
)