from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Final

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import EmailVerificationToken, User

PASSWORD_SCHEME: Final[str] = "pbkdf2_sha256"
PASSWORD_ITERATIONS: Final[int] = 210_000
MIN_PASSWORD_LENGTH: Final[int] = 10


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email is not valid.")
    return normalized


def assert_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if password.strip() != password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password cannot start or end with whitespace.",
        )


def hash_password(password: str) -> str:
    assert_password_policy(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        [
            PASSWORD_SCHEME,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        ]
    )


def verify_password(password: str, encoded_hash: str | None) -> bool:
    if not encoded_hash:
        return False
    try:
        scheme, iterations_raw, salt_raw, digest_raw = encoded_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_raw)
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def issue_email_verification_token(
    session: Session,
    *,
    user: User,
    settings: Settings,
) -> str:
    raw_token = secrets.token_urlsafe(32)
    token = EmailVerificationToken(
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.email_verification_ttl_minutes),
    )
    session.add(token)
    session.flush()
    return raw_token


def consume_email_verification_token(session: Session, *, raw_token: str) -> User:
    token = session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hash_token(raw_token.strip()))
    )
    if token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email verification token.")
    now = datetime.now(timezone.utc)
    expires_at = _aware_utc(token.expires_at)
    if token.consumed_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired email verification token.")
    user = session.get(User, token.user_id)
    if user is None or user.tenant_id != token.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email verification token.")
    token.consumed_at = now
    user.email_verified_at = now
    user.status = "active"
    return user


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
