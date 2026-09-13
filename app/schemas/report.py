"""หน้าตาของ "เรื่อง" ที่ analyzer สรุปได้จากบทสนทนา พร้อมรูปกับพิกัดที่เก็บไว้ระหว่างคุย

ทุกช่องเนื้อหาเป็น None ได้ และ None แปลว่า "ยังไม่ได้ถาม / ยังไม่รู้" ไม่ใช่ "ไม่มี"
เช่น is_has_image=None คือยังไม่ได้คุยเรื่องรูป ส่วน False คือถามแล้วเขาไม่มีหรือไม่อยากให้
ไม่มี Field(min_length) หรือ CHECK ที่นี่ เพราะเรื่องที่เล่ามาไม่ครบก็ยังต้องเก็บได้
"""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.schemas.ai_config import AgentName

Status = Literal["not_analyzed", "pending", "analyzed"]
ProblemType = Literal["flood", "heat", "light", "other"]
Threat = Literal["not_relate", "low", "mid", "high"]
Frequency = Literal["always", "usually", "often", "subtle", "first_time", "dont_know"]
LocationType = Literal["lat_lon", "str"]


class Report(BaseModel):
    """หนึ่งเรื่องที่ชาวบ้านเล่า หลัง analyzer อ่านบทสนทนาจบแล้ว

    ในนี้เก็บแต่บทสรุป ตัวรูปกับพิกัดอยู่คนละที่ (Image / Location)
    ต้อง query กลับมาแปะเอง ช่อง is_has_* เป็นแค่ป้ายบอกว่ามีให้ไปหยิบไหม
    """

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    status: Status = "not_analyzed"
    session_id: UUID                    # บทสนทนารอบที่เรื่องนี้โผล่ขึ้นมา
    title: str | None = None
    type: ProblemType | None = None
    threat: Threat | None = None        # โน้ตเขียน treat — ระดับความน่ากังวลของเรื่อง
    frequency: Frequency | None = None  # subtle = นาน ๆ ที (subtel ในโน้ต)
    effect: str | None = None           # ผลกระทบ เล่าเป็นคำพูดของเขา — "-" คือถามแล้วเขาบอกว่าไม่กระทบ
    is_has_image: bool | None = None
    is_has_location: bool | None = None


class Image(BaseModel):
    """รูปหนึ่งใบที่รับมาจากไลน์ระหว่าง session"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    number: int                    # ข้อความที่เท่าไหร่ใน session ที่รูปใบนี้ติดมาด้วย
    line_image_url: str            # ที่อยู่ฝั่งไลน์ ดึงซ้ำได้จนกว่าไลน์จะลบ
    image_key: str | None = None   # path ฝั่งเราจาก clients.storage.save_image — ยังไม่ได้ดึงลงมาก็ว่าง
    desc: str | None = None        # คำบรรยายจาก ai ที่อ่านภาพ — ยังไม่ได้อ่านก็ว่าง
    created_at: datetime = Field(default_factory=datetime.now)


class Location(BaseModel):
    """ที่เกิดเรื่อง มาได้สองแบบ แชร์พิกัดในไลน์ หรือพิมพ์บอกเป็นคำพูด

    type บอกว่ารอบนั้นได้แบบไหนมา อีกแบบก็ว่างไว้ ไม่เดาเติมให้กัน
    """

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    number: int                    # ข้อความที่เท่าไหร่ใน session ที่พิกัดนี้ติดมาด้วย
    type: LocationType
    lat: float | None = None
    lon: float | None = None
    address: str | None = None     # ช่อง "str" ในโน้ต — เลี่ยงชื่อ str เพราะชนกับชนิดข้อมูลของ python
    created_at: datetime = Field(default_factory=datetime.now)


class Session(BaseModel):
    """บทสนทนาหนึ่งรอบของคนหนึ่งคน

    เปิดตอนเขาทักเข้ามาแล้วไม่มีรอบไหนค้างอยู่ จบเองด้วยการเงียบจนหมดอายุ
    ของที่เก็บระหว่างคุย (ข้อความ รูป พิกัด) อ้าง id ของรอบนี้กันหมด

    status กันตัวกวาดหยิบรอบเดียวกันไปวิเคราะห์ซ้อนกัน
    pending = มีคนกำลังวิเคราะห์อยู่ ใครมาเจอทีหลังให้ข้ามไป
    วิเคราะห์พังกลับไปเป็น not_analyzed เพื่อให้รอบกวาดถัดไปลองใหม่ได้

    is_finished คนละเรื่องกับ status — status บอกว่าวิเคราะห์ไปถึงไหน
    is_finished บอกว่าชาวบ้านเล่าจบแล้ว ตัวกวาดจะปิดให้เลยไม่ต้องรอเงียบครบเวลา
    ยัดรวมกันเป็นค่าเดียวไม่ได้ เพราะรอบที่เล่าจบแล้วก็ยังต้องวิเคราะห์อยู่
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    status: Status = "not_analyzed"
    is_finished: bool = False   # ai_tools.set_finished_flag ปัก/ถอนตามที่ communicator อ่านได้
    created_at: datetime = Field(default_factory=datetime.now)


class Message(BaseModel):
    """ข้อความหนึ่งข้อที่ผู้ใช้ส่งเข้ามา เรียงตาม number ตั้งแต่ 1 ในแต่ละ session

    ไม่มีช่องบอกว่าใครพูด เพราะตารางนี้เก็บแต่ฝั่งผู้ใช้ คำตอบของบอทอยู่ใน AiResponse
    content เป็นข้อความเดียวกับที่โมเดลเห็น รูปกับพิกัดจึงเป็นป้ายสั้น ๆ ไม่ใช่ตัวไฟล์หรือตัวเลข
    ตัวจริงไปตามเอาจาก images/locations ที่ชี้กลับมาด้วย session_id คู่กับ number
    """

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    number: int
    content: str
    created_at: datetime = Field(default_factory=datetime.now)

class AiResponse(BaseModel):
    """คำตอบหนึ่งครั้งที่โมเดลเขียนออกมา

    บอกว่าใช้ config ไหนเขียน จะได้ย้อนดูได้ว่าทำไมมันตอบแบบนั้น
    ไม่เก็บ AgentConfig ทั้งก้อนเพราะเนื้อ prompt จะซ้ำทุกแถว — ai_config_id พาไปหาของจริงได้อยู่แล้ว
    ai_config_id ว่าง = ตอนนั้นฐานไม่มีแถว active แอปใช้ค่า default จาก core/default_value.py
    ไม่มี number เพราะไม่ใช่ข้อความของผู้ใช้ เรียงตาม created_at เอา
    """

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    agent: AgentName
    ai_config_id: int | None = None
    model_name: str
    content: str
    created_at: datetime = Field(default_factory=datetime.now)
