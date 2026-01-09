from datetime import datetime

from pydantic import BaseModel


class UserBase(BaseModel):
    email: str
    full_name: str | None = None


class UserRead(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
