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

# เก็บได้เฉพาะนามสกุลรูปจริง — กันคนอัปไฟล์ปลอม (เช่น .html ที่ซ่อนสคริปต์)
# มาให้เราเสิร์ฟกลับจาก origin เดียวกับหน้า LIFF
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def unique_image_name(original_filename):
    """A collision-proof stored filename: random uuid + a safe image extension.

    Only real image extensions are kept; anything else (or missing) becomes .jpg,
    so a disguised upload can never be stored and later served as itself.
    """
    ext = os.path.splitext(original_filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        ext = ".jpg"
    return f"{uuid.uuid4().hex}{ext}"


def save_blob(key: str, data: bytes) -> str:
    """เก็บ bytes ตาม storage key แล้วคืน key เดิม (generic: รูปหรือไฟล์ข้อความ)"""
    # ponytail: S3 seam สำหรับ text ด้วย — local uploads/ ตอนนี้, ย้ายขึ้น S3 ทีหลัง
    # ด้วยการเปลี่ยนไส้ในตรงนี้ที่เดียว key เดิมใช้ต่อได้เลย
    path = UPLOAD_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def save_image(key: str, data: bytes) -> str:
    """เก็บ bytes ของรูปตาม storage key แล้วคืน key เดิม — รูปก็คือ blob แบบหนึ่ง"""
    return save_blob(key, data)


def local_file(key: Optional[str]) -> Optional[Path]:
    """Path ของรูปที่เก็บไว้ หรือ None ถ้าไม่มี (ยังไม่เคยเก็บ/ไฟล์หาย)"""
    if not key:
        return None
    path = UPLOAD_DIR / key
    return path if path.exists() else None


def read_blob(key: Optional[str]) -> Optional[bytes]:
    """bytes ที่เก็บไว้ตาม key หรือ None ถ้าไม่มี (คู่กับ save_blob)"""
    path = local_file(key)
    return path.read_bytes() if path else None
