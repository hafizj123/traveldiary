import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.otp import EmailOTP
from ..schemas.auth import (
    RegisterRequest,
    VerifyOTPRequest,
    ResendOTPRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)
from ..utils.security import hash_password, verify_password, create_access_token
from ..utils.deps import get_current_user
from ..services.email_service import generate_otp, get_otp_expiry, send_otp_email
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _auto_username(email: str, db: Session) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]", "", email.split("@")[0]) or "user"
    username, n = base, 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base}{n}"
        n += 1
    return username


@router.post("/register", status_code=201)
async def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")
    if len(data.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    username = data.username
    if not username:
        username = _auto_username(data.email, db)
    elif db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "Username already taken")

    user = User(
        email=data.email,
        username=username,
        password_hash=hash_password(data.password),
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    otp_code = generate_otp()
    db.add(EmailOTP(user_id=user.id, otp_code=otp_code, expires_at=get_otp_expiry()))
    db.commit()

    await send_otp_email(user.email, otp_code)

    resp = {
        "message": "Registration successful. Check your email (or server console) for the OTP.",
        "email": user.email,
    }
    if settings.DEBUG and not settings.SMTP_USER:
        resp["debug_otp"] = otp_code
    return resp


@router.post("/verify-otp")
def verify_otp(data: VerifyOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(404, "User not found")

    otp = (
        db.query(EmailOTP)
        .filter(
            EmailOTP.user_id == user.id,
            EmailOTP.otp_code == data.otp_code,
            EmailOTP.is_used == False,
            EmailOTP.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not otp:
        raise HTTPException(400, "Invalid or expired OTP")

    otp.is_used = True
    user.is_verified = True
    db.commit()
    return {"message": "Email verified. You can now log in."}


@router.post("/resend-otp")
async def resend_otp(data: ResendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.is_verified:
        raise HTTPException(400, "Email already verified")

    db.query(EmailOTP).filter(EmailOTP.user_id == user.id).update({"is_used": True})

    otp_code = generate_otp()
    db.add(EmailOTP(user_id=user.id, otp_code=otp_code, expires_at=get_otp_expiry()))
    db.commit()

    await send_otp_email(user.email, otp_code)

    resp = {"message": "OTP resent."}
    if settings.DEBUG and not settings.SMTP_USER:
        resp["debug_otp"] = otp_code
    return resp


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_verified:
        raise HTTPException(403, "Please verify your email first")

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
