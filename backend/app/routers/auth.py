import re
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx

from ..database import get_db
from ..models.user import User
from ..models.otp import EmailOTP
from ..schemas.auth import (
    RegisterRequest,
    VerifyOTPRequest,
    ResendOTPRequest,
    LoginRequest,
    GoogleLoginRequest,
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


def _unusable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


async def _verify_google_credential(credential: str) -> dict:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": credential},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to verify Google login") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    payload = response.json()
    audience = str(payload.get("aud") or "").strip()
    if audience != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Google credential was issued for a different client")
    if str(payload.get("email_verified")).lower() != "true":
        raise HTTPException(status_code=403, detail="Google account email is not verified")
    return payload


def _mark_successful_login(user: User, db: Session) -> TokenResponse:
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    user.last_login_at = datetime.utcnow()
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


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
        auth_provider="local",
        is_verified=False,
        is_admin=False,
        is_active=True,
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
    if not user:
        raise HTTPException(401, "Invalid email or password")
    if user.auth_provider == "google":
        raise HTTPException(400, "This account uses Google sign-in. Continue with Google instead.")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_verified:
        raise HTTPException(403, "Please verify your email first")
    return _mark_successful_login(user, db)


@router.post("/google", response_model=TokenResponse)
async def google_login(data: GoogleLoginRequest, db: Session = Depends(get_db)):
    payload = await _verify_google_credential(data.credential)
    google_sub = str(payload.get("sub") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    if not google_sub or not email:
        raise HTTPException(status_code=400, detail="Google account did not provide a valid email")

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            if user.google_sub and user.google_sub != google_sub:
                raise HTTPException(status_code=409, detail="This email is already linked to a different Google account")
            user.google_sub = google_sub
            user.avatar_url = str(payload.get("picture") or "").strip() or user.avatar_url
            user.is_verified = True
            user.auth_provider = "hybrid" if user.auth_provider == "local" else "google"
        else:
            user = User(
                email=email,
                username=_auto_username(email, db),
                password_hash=_unusable_password_hash(),
                auth_provider="google",
                google_sub=google_sub,
                avatar_url=str(payload.get("picture") or "").strip() or None,
                is_verified=True,
                is_admin=False,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")

    db.add(user)
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
