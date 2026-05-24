from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import openpyxl

from app.services.credential_vault import decrypt_platform_credentials, is_encrypted_credential_ref


@dataclass(frozen=True)
class PlatformCredentials:
    username: str
    password: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CredentialResolution:
    credentials: PlatformCredentials | None
    expected_env_vars: list[str]


def resolve_platform_credentials(
    *,
    secret_ref: str | None,
    platform_account_id: str,
) -> CredentialResolution:
    expected = _expected_env_vars(secret_ref=secret_ref, platform_account_id=platform_account_id)
    if is_encrypted_credential_ref(secret_ref):
        try:
            decrypted = decrypt_platform_credentials(secret_ref or "")
        except Exception:
            return CredentialResolution(credentials=None, expected_env_vars=expected)
        return CredentialResolution(
            credentials=PlatformCredentials(
                username=decrypted.username,
                password=decrypted.password,
                metadata=decrypted.metadata,
            ),
            expected_env_vars=expected,
        )
    for base_name in expected:
        raw = os.getenv(base_name)
        if raw:
            credentials = _credentials_from_json(raw)
            if credentials is not None:
                return CredentialResolution(credentials=credentials, expected_env_vars=expected)
        username = os.getenv(f"{base_name}_USERNAME")
        password = os.getenv(f"{base_name}_PASSWORD")
        if username and password:
            return CredentialResolution(
                credentials=PlatformCredentials(username=username, password=password),
                expected_env_vars=expected,
            )
    local_credentials = _credentials_from_local_excel(platform_account_id)
    if local_credentials is not None:
        return CredentialResolution(credentials=local_credentials, expected_env_vars=expected)
    return CredentialResolution(credentials=None, expected_env_vars=expected)


def _credentials_from_json(raw: str) -> PlatformCredentials | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    username = payload.get("username") or payload.get("user") or payload.get("login")
    password = payload.get("password") or payload.get("pass")
    if isinstance(username, str) and isinstance(password, str) and username and password:
        metadata = _metadata_from_payload(payload)
        return PlatformCredentials(username=username, password=password, metadata=metadata)
    return None


def _metadata_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = payload.get("metadata")
    metadata: dict[str, Any] = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    raw_login_hints = payload.get("login_hints")
    login_hints: dict[str, Any] = dict(raw_login_hints) if isinstance(raw_login_hints, dict) else {}
    merged_hints: dict[str, Any] = dict(login_hints)
    for key in ("client", "customer", "tenant"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            merged_hints[key] = value.strip()
    if merged_hints:
        raw_existing_hints = metadata.get("login_hints")
        existing_hints = dict(raw_existing_hints) if isinstance(raw_existing_hints, dict) else {}
        metadata = {**metadata, "login_hints": {**existing_hints, **merged_hints}}
    return metadata


def _expected_env_vars(*, secret_ref: str | None, platform_account_id: str) -> list[str]:
    names = [f"IPRL_CAE_PLATFORM_CREDENTIALS_{_env_suffix(platform_account_id)}"]
    if secret_ref:
        if secret_ref.startswith("env:"):
            names.insert(0, secret_ref.removeprefix("env:"))
        elif secret_ref.startswith("vault://"):
            names.append(f"IPRL_CAE_SECRET_{_env_suffix(secret_ref)}")
        elif is_encrypted_credential_ref(secret_ref):
            names.append("encrypted_db_secret")
    return list(dict.fromkeys(names))


def _env_suffix(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def _credentials_from_local_excel(platform_account_id: str) -> PlatformCredentials | None:
    if os.getenv("IPRL_CAE_ENABLE_LOCAL_EXCEL_CREDENTIALS", "true").strip().lower() not in {"1", "true", "yes"}:
        return None
    match = re.search(r"_(arm|elca|loyola)_r(\d+)(?:_|$)", platform_account_id, flags=re.I)
    if match is None:
        return None
    sheet_name = match.group(1).upper()
    row_number = int(match.group(2))
    workbook_path = Path(
        os.getenv(
            "IPRL_CAE_LOCAL_PLATFORM_CREDENTIALS_XLSX",
            str(Path(__file__).resolve().parents[3] / "requisitos" / "USUARIOS Y CONTRASEÑAS PLATAFORMASulo.xlsx"),
        )
    )
    if not workbook_path.exists():
        return None
    wb = openpyxl.load_workbook(workbook_path, data_only=True, read_only=True)
    if sheet_name not in wb.sheetnames:
        return None
    values: list[Any] = [cell.value for cell in wb[sheet_name][row_number]]
    username = str(values[2] or "").strip() if len(values) > 2 else ""
    password = str(values[3] or "").strip() if len(values) > 3 else ""
    if not username or not password:
        return None
    return PlatformCredentials(username=username, password=password)
