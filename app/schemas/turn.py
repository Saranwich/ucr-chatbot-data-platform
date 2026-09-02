from pydantic import BaseModel


class Turn(BaseModel):
    """หนึ่งตาในบทสนทนา พร้อมต่อท้าย session และพร้อมให้โมเดลอ่าน

    ไม่มี reply token กับ user id ในนี้ สองอย่างนั้นเป็นซองจดหมาย
    chatbot ถือไว้เองระหว่างรอบ ไม่ได้เป็นเนื้อหาของบทสนทนา
    """

    role: str          # user | assistant | system
    content_type: str  # text | image | location | follow
    content: str       # เนื้อที่โมเดลอ่านรู้เรื่อง — ยกเว้น image ที่ยังเป็น message id
