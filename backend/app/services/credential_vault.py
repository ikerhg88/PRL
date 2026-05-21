from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

ENCRYPTED_CREDENTIAL_PREFIX = "enc:v1:"


@dataclass(frozen=True)
class DecryptedPlatformCredential:
    username: str
    password: str
    metadata: dict[str, Any]


def encrypt_platform_credentials(
    *,
    username: str,
    password: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    payload = {
        "u": username,
        "p": password,
        "m": {
            **(metadata or {}),
            "encrypted_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    encrypted = AESGCM(_key()).encrypt(nonce, raw, None)
    token = base64.urlsafe_b64encode(nonce + encrypted).rstrip(b"=").decode("ascii")
    return f"{ENCRYPTED_CREDENTIAL_PREFIX}{token}"


def decrypt_platform_credentials(secret_ref: str) -> DecryptedPlatformCredential:
    if not is_encrypted_credential_ref(secret_ref):
        raise ValueError("Unsupported encrypted credential reference.")
    token = secret_ref.removeprefix(ENCRYPTED_CREDENTIAL_PREFIX)
    padded = token + "=" * (-len(token) % 4)
    payload = base64.urlsafe_b64decode(padded.encode("ascii"))
    if len(payload) <= 28:
        raise ValueError("Encrypted credential payload is too short.")
    nonce = payload[:12]
    encrypted = payload[12:]
    raw = AESGCM(_key()).decrypt(nonce, encrypted, None)
    data = json.loads(raw.decode("utf-8"))
    username = data.get("u")
    password = data.get("p")
    metadata = data.get("m") or {}
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("Encrypted credential payload is invalid.")
    if not isinstance(metadata, dict):
        metadata = {}
    return DecryptedPlatformCredential(username=username, password=password, metadata=metadata)


def is_encrypted_credential_ref(secret_ref: str | None) -> bool:
    return bool(secret_ref and secret_ref.startswith(ENCRYPTED_CREDENTIAL_PREFIX))


def _key() -> bytes:
    settings = get_settings()
    return hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
