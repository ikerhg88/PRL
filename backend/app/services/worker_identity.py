from __future__ import annotations

import hashlib
import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Worker


def normalize_worker_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]+", "", value).upper()
    return normalized or None


def worker_identifier_hash(identifier_value: str | None) -> str | None:
    normalized = normalize_worker_identifier(identifier_value)
    if normalized is None:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def apply_identifier_identity_fields(data: dict[str, object]) -> dict[str, object]:
    if "identifier_value" not in data:
        return data
    raw_identifier = data.get("identifier_value")
    normalized = normalize_worker_identifier(raw_identifier if isinstance(raw_identifier, str) else None)
    data["identifier_value"] = normalized
    data["identifier_hash"] = worker_identifier_hash(normalized)
    if normalized:
        data["identifier_type"] = data.get("identifier_type") or "dni"
        data["identifier_last4"] = data.get("identifier_last4") or normalized[-4:]
    elif not data.get("identifier_hash"):
        data["identifier_hash"] = None
    return data


def find_worker_by_identifier_hash(
    session: Session,
    *,
    tenant_id: int,
    company_id: int,
    identifier_hash: str | None,
    exclude_worker_id: int | None = None,
) -> Worker | None:
    if not identifier_hash:
        return None
    statement = select(Worker).where(
        Worker.tenant_id == tenant_id,
        Worker.company_id == company_id,
        Worker.identifier_hash == identifier_hash,
        Worker.status != "deleted",
    )
    if exclude_worker_id is not None:
        statement = statement.where(Worker.id != exclude_worker_id)
    return session.scalar(statement)


def ensure_worker_identifier_is_unique(
    session: Session,
    *,
    tenant_id: int,
    company_id: int,
    identifier_hash: str | None,
    exclude_worker_id: int | None = None,
) -> None:
    conflict = find_worker_by_identifier_hash(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        identifier_hash=identifier_hash,
        exclude_worker_id=exclude_worker_id,
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ya existe un trabajador con ese DNI/NIE en esta empresa. "
                "El DNI/NIE es el dato unico de trabajador."
            ),
        )
