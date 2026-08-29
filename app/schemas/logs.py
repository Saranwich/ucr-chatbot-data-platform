from typing import Literal

from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4

class LogsRecord (BaseModel):
    id: UUID = Field(default_factory=uuid4)
    time: datetime = Field(default_factory=datetime.now)
    process_name: str
    log_message: str

    
