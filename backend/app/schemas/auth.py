import uuid

from pydantic import BaseModel, EmailStr

from app.models.users import RoleEnum


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: RoleEnum


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: RoleEnum = RoleEnum.KITCHEN


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: RoleEnum

    class Config:
        from_attributes = True
