from typing import Literal

from pydantic import BaseModel


class QuickReplyItem (BaseModel, frozen=True):
    """ปุ่มหนึ่งปุ่มใต้ข้อความที่บอทตอบ — ผ่านการตรวจแล้วเท่านั้นถึงมาอยู่ในรูปนี้

    frozen เพราะปั้นเสร็จแล้วไม่มีใครควรมาแก้ระหว่างทาง คนปั้นคือ communicator_output ที่เดียว
    text เป็น None เมื่อ type=location — ปุ่มพิกัดไม่ได้ส่งข้อความ มันเปิดหน้าแชร์ตำแหน่งของ LINE
    """

    type: Literal["message", "location"]
    label: str
    text: str | None = None


class CommunicatorReply (BaseModel, frozen=True):
    """คำตอบหนึ่งตาของ communicator ที่ผ่านการตรวจแล้ว พร้อมส่งออกไลน์

    reply_text ไม่มีค่าตั้งต้น เพราะตาที่ไม่มีข้อความคือตาที่ใช้ไม่ได้ ต้องคืน None ทั้งก้อนไปเลย
    อีกสองช่องมีค่าตั้งต้น ขาดมาก็ยังตอบชาวบ้านได้ เสียแค่ธงกับปุ่มของตานั้น

    is_finished ตั้งต้นเป็น False ตรงกับที่ระบบถืออยู่แล้ว — ไม่ได้ยินอะไรจากโมเดล = ยังไม่จบ
    """

    reply_text: str
    is_finished: bool = False
    quick_replies: list[QuickReplyItem] = []
