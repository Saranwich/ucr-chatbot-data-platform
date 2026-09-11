from datetime import datetime

from pydantic import BaseModel, Field


class SystemConfig(BaseModel, frozen=True):
    """ค่าของระบบที่แอดมินปรับได้ระหว่างแอปรัน = หนึ่งแถวใน system_config

    frozen เพราะทั้งแอปถือก้อนเดียวกันอยู่ จะเปลี่ยนต้องผ่าน services.config.system_config.reload() ทางเดียว
    """

    # ข้อมูลของแถว — id None = ค่า default ในโค้ด ไม่ได้มาจาก db
    id: int | None = None
    created_at: datetime | None = None
    note: str | None = None                       # เปลี่ยนแถวนี้เพราะอะไร

    session_ttl_seconds: int = Field(3600, gt=0)  # เงียบไปนานเท่านี้ บอทลืมบทสนทนา
