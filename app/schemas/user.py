from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class User(BaseModel):
    """คนหนึ่งคนที่คุยกับบอท — id เป็นของเราเอง ไม่ผูกกับ LINE

    line_user_id เป็นแค่ทางเข้า ของอื่นในระบบให้อ้าง id
    """

    id: UUID
    line_user_id: str
    name: str | None = None
    age_group: Literal["children", "teenage", "mature", "elder"] | None = None
