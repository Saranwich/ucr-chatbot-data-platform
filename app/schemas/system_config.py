from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.default_value import (
    DEFAULT_FINISHED_GRACE_SECONDS,
    DEFAULT_INACTIVE_SESSION_SECONDS,
    DEFAULT_SESSION_TTL_SECONDS,
    DEFAULT_SWEEP_INTERVAL_SECONDS,
)


class SystemConfig(BaseModel, frozen=True):
    """ค่าของระบบที่แอดมินปรับได้ระหว่างแอปรัน = หนึ่งแถวใน system_config

    frozen เพราะทั้งแอปถือก้อนเดียวกันอยู่ จะเปลี่ยนต้องผ่าน services.config.system_config.reload() ทางเดียว
    """

    # ข้อมูลของแถว — id None = ค่า default ในโค้ด ไม่ได้มาจาก db
    id: int | None = None
    created_at: datetime | None = None
    note: str | None = None                       # เปลี่ยนแถวนี้เพราะอะไร

    session_ttl_seconds: int = Field(DEFAULT_SESSION_TTL_SECONDS, gt=0)  # เงียบไปนานเท่านี้ บอทลืมบทสนทนา
    finished_grace_seconds: int = Field(DEFAULT_FINISHED_GRACE_SECONDS, gt=0)  # บอกว่าจบแล้ว ยังรอข้อความใหม่กี่วินาที
    inactive_session_seconds: int = Field(DEFAULT_INACTIVE_SESSION_SECONDS, gt=0)  # ยังไม่จบ ต้องเงียบกี่วินาทีจึงปิด
    sweep_interval_seconds: int = Field(DEFAULT_SWEEP_INTERVAL_SECONDS, gt=0)              # ตัวกวาดวนมาทุกกี่วินาที

    @model_validator(mode="after")
    def timeouts_must_finish_before_redis_expires(self):
        latest_safe_close = self.session_ttl_seconds - self.sweep_interval_seconds
        if self.finished_grace_seconds > latest_safe_close:
            raise ValueError("finished_grace_seconds ต้องเหลือเวลาก่อน Redis หมดอายุอย่างน้อยหนึ่งรอบกวาด")
        if self.inactive_session_seconds > latest_safe_close:
            raise ValueError("inactive_session_seconds ต้องเหลือเวลาก่อน Redis หมดอายุอย่างน้อยหนึ่งรอบกวาด")
        return self
