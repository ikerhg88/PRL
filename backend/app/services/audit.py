from __future__ import annotations

from typing import Any, cast

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def record_audit(
    session: Session,
    *,
    tenant_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | str | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    actor_user_id: int | None = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before_json=before,
        after_json=after,
        correlation_id=correlation_id,
    )
    session.add(entry)
    return entry


def public_state(values: dict[str, Any]) -> dict[str, Any]:
    blocked_keys = {
        "credential_secret_ref",
        "encrypted_credential_ref",
        "encrypted_secret_ref",
        "secret",
        "password",
        "token",
        "cookie",
    }
    state = {
        key: ("***" if key.lower() in blocked_keys else value)
        for key, value in values.items()
        if not key.startswith("_")
    }
    return cast(dict[str, Any], jsonable_encoder(state))
