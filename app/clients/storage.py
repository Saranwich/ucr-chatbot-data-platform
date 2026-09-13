from uuid import uuid4

from app.core.config import UPLOAD_DIR

PROCESS = "clients.storage"

# ไลน์ส่งรูปมาเป็น jpeg เกือบทั้งหมด ชนิดอื่นที่ไม่รู้จักก็ยังเก็บไว้ ดีกว่าทิ้ง
EXTENSION = {"image/jpeg": ".jpg", "image/png": ".png"}


def save_image(data: bytes, content_type: str) -> str:
    """เขียนไฟล์ลงดิสก์ คืน path ที่เก็บลง db — วันหน้าย้ายไป s3 แก้ที่ฟังก์ชันนี้ที่เดียว"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4()}{EXTENSION.get(content_type.split(';')[0].strip(), '.jpg')}"
    (UPLOAD_DIR / name).write_bytes(data)
    return f"uploads/{name}"
