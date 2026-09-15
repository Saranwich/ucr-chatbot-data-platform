from app.core.load_env import *  # noqa: F403 — DATABASE_URL, REDIS_URL, LINE_*, TYPHOON_API_KEY
from app.core.load_env import BASE_DIR

# --- endpoint ---
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"
LINE_LOADING_URL = "https://api.line.me/v2/bot/chat/loading/start"
TYPHOON_API_ENDPOINT = "https://api.opentyphoon.ai/v1"
# หน้า openai-compatible ของ google ai studio ไม่ใช่ทางเดิมของกูเกิล — path /openai/ คือตัวแยก
GOOGLE_AI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai"

# --- ที่เก็บไฟล์ ---
# อยู่ใต้ storage/ ที่ .gitignore กันไว้แล้ว รูปของชาวบ้านจะได้ไม่ขึ้น git
# save_image() คืน path ที่ตัดถึงแค่ "uploads/..." วันย้ายขึ้น s3 คีย์เดิมใช้ต่อได้
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
