"""ที่เก็บรูปกลาง — ทุกโมดูลเซฟ/อ่านรูปผ่านที่นี่ ห้ามเขียนไฟล์เอง

ตอนนี้มี backend เดียว: local (เขียนใต้ uploads/ ตาม storage key เช่น
'survey/<image_id>.jpg', 'reports/<uuid>.jpg') — เมื่อย้ายขึ้น S3
จะเปลี่ยนไส้ของ save_image/local_file ที่นี่ที่เดียว ส่วน key เดิมใช้ต่อได้เลย
"""
import os
import uuid
from pathlib import Path
from typing import Optional

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def unique_image_name(original_filename):
    """A collision-proof stored filename: random uuid + the original extension (default .jpg)."""
    ext = os.path.splitext(original_filename or "")[1] or ".jpg"
    return f"{uuid.uuid4().hex}{ext}"


def save_image(key: str, data: bytes) -> str:
    """เก็บ bytes ของรูปตาม storage key แล้วคืน key เดิม"""
    path = UPLOAD_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def local_file(key: Optional[str]) -> Optional[Path]:
    """Path ของรูปที่เก็บไว้ หรือ None ถ้าไม่มี (ยังไม่เคยเก็บ/ไฟล์หาย)"""
    if not key:
        return None
    path = UPLOAD_DIR / key
    return path if path.exists() else None
