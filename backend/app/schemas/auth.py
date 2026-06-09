from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str


class ResendOTPRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    username: Optional[str] = None
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
