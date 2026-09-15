from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.default_value import DEFAULT_AGENT_CONFIG

AgentName = Literal["communicator", "analyzer", "resource_analyzer"]


class AgentConfig(BaseModel, frozen=True):
    """ค่าของ agent หนึ่งตัว = หนึ่งแถวใน ai_configuration พ่วงเนื้อ prompt ที่แถวนั้นชี้ไป

    frozen เพราะทั้งแอปถือก้อนเดียวกันอยู่ จะเปลี่ยนต้องผ่าน services.config.ai_config.reload() ทางเดียว
    ไม่มีค่า default ในนี้ ค่า default อยู่ core/default_value.py ที่เดียว
    """
    id: int | None = None
    created_at: datetime | None = None
    note: str | None = None
    agent: AgentName
    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    prompt_id: int | None = None
    prompt: str                                   # เนื้อจากตาราง prompts — ว่าง = ไม่ส่ง system prompt
    temperature: float = Field(ge=0, le=2) # 0-2
    max_output_tokens: int = Field(gt=0) # > 0


def default_agent_config(agent: AgentName) -> AgentConfig:
    return AgentConfig(agent=agent, **DEFAULT_AGENT_CONFIG[agent])


class AiConfig(BaseModel, frozen=True):
    """ค่าของ agent ทุกตัวที่แอปใช้อยู่ตอนนี้ — ตัวไหนไม่มีใน db ก็ใช้ default ของตัวนั้น"""

    communicator: AgentConfig = default_agent_config("communicator")
    analyzer: AgentConfig = default_agent_config("analyzer")
    resource_analyzer: AgentConfig = default_agent_config("resource_analyzer")
