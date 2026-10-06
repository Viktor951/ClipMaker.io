from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt só considera os primeiros 72 bytes: limitar evita truncamento silencioso
    password: str = Field(..., min_length=8, max_length=72)
    name: Optional[str] = Field(default=None, max_length=100)
