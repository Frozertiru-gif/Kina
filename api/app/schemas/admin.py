from datetime import datetime

from pydantic import BaseModel


class AdminRead(BaseModel):
    id: int
    email: str
    created_at: datetime

    class Config:
        from_attributes = True
