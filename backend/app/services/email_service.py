import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from ..config import settings


def generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def get_otp_expiry() -> datetime:
    return datetime.utcnow() + timedelta(minutes=10)


async def send_otp_email(email: str, otp_code: str) -> None:
    # In debug mode with no SMTP configured, print to console
    if settings.DEBUG and not settings.SMTP_USER:
        print(f"\n{'='*50}")
        print(f"  OTP for {email}:  {otp_code}")
        print(f"  (expires in 10 minutes)")
        print(f"{'='*50}\n")
        return

    subject = "Travel Diary – Your Verification Code"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px;border-radius:8px;background:#f8fafc">
      <h2 style="color:#4f46e5">Travel Diary</h2>
      <p>Your email verification code is:</p>
      <div style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#4f46e5;padding:16px 0">{otp_code}</div>
      <p style="color:#64748b">This code expires in <strong>10 minutes</strong>.</p>
      <p style="color:#64748b;font-size:12px">If you did not request this, ignore this email.</p>
    </div>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = email
    msg.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, email, msg.as_string())
        server.quit()
    except Exception as exc:
        print(f"[email] Failed to send to {email}: {exc}")
        if settings.DEBUG:
            print(f"[email] DEBUG OTP fallback → {otp_code}")
