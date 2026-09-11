from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["communicator", "analyzer", "resource_analyzer"]


class AgentConfig(BaseModel, frozen=True):
    """ค่าของ agent หนึ่งตัว = หนึ่งแถวใน ai_configuration

    frozen เพราะทั้งแอปถือก้อนเดียวกันอยู่ จะเปลี่ยนต้องผ่าน services.config.ai_config.reload() ทางเดียว
    """
    id: int | None = None
    created_at: datetime | None = None
    note: str | None = None
    agent: AgentName
    provider: str = Field("typhoon", min_length=1)
    model_name: str = Field("typhoon-v2.5-30b-a3b-instruct", min_length=1)
    prompt_id: int | None = None                  # ยังไม่มีตาราง prompts
    temperature: float = Field(0.7, ge=0, le=2) # 0-2
    max_output_tokens: int = Field(1024, gt=0) # > 0


class AiConfig(BaseModel, frozen=True):
    """ค่าของ agent ทุกตัวที่แอปใช้อยู่ตอนนี้ — ตัวไหนไม่มีใน db ก็ใช้ default ของตัวนั้น"""

    communicator: AgentConfig = AgentConfig(agent="communicator")
    analyzer: AgentConfig = AgentConfig(agent="analyzer")
    resource_analyzer: AgentConfig = AgentConfig(agent="resource_analyzer")
