from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Tenant
from app.db.session import get_session
from app.services.sso import decode_local_access_token


DbSession = Annotated[Session, Depends(get_session)]


def get_tenant_id(
    x_tenant_id: Annotated[int | None, Header(alias="X-Tenant-ID")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> int:
    claims = _claims_from_authorization(authorization)
    token_tenant_id = _claim_int(claims, "tenant_id")
    if token_tenant_id is not None:
        if x_tenant_id is not None and token_tenant_id != x_tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant header does not match token.")
        return token_tenant_id
    if x_tenant_id is not None and _trusted_header_auth_enabled():
        return x_tenant_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Bearer token is required for tenant-scoped operations.",
    )


def get_public_tenant_id(
    x_tenant_id: Annotated[int | None, Header(alias="X-Tenant-ID")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> int:
    claims = _claims_from_authorization(authorization)
    token_tenant_id = _claim_int(claims, "tenant_id")
    if token_tenant_id is not None:
        if x_tenant_id is not None and token_tenant_id != x_tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant header does not match token.")
        return token_tenant_id
    if x_tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Tenant-ID header is required.")
    return x_tenant_id


TenantId = Annotated[int, Depends(get_tenant_id)]
PublicTenantId = Annotated[int, Depends(get_public_tenant_id)]


def get_actor_user_id(
    x_user_id: Annotated[int | None, Header(alias="X-User-ID")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> int | None:
    claims = _claims_from_authorization(authorization)
    token_user_id = _claim_int(claims, "sub")
    if token_user_id is not None:
        if x_user_id is not None and token_user_id != x_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor header does not match token.")
        return token_user_id
    if x_user_id is not None and _trusted_header_auth_enabled():
        return x_user_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Bearer token is required for tenant-scoped operations.",
    )


ActorUserId = Annotated[int | None, Depends(get_actor_user_id)]


def require_tenant(session: Session, tenant_id: int) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return tenant


def bearer_token_from_authorization(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header.")
    return token.strip()


def _claims_from_authorization(authorization: str | None) -> dict[str, object] | None:
    token = bearer_token_from_authorization(authorization)
    if token is None:
        return None
    return decode_local_access_token(token, settings=get_settings())


def _claim_int(claims: dict[str, object] | None, key: str) -> int | None:
    if claims is None:
        return None
    value = claims.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claim.")
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claim.") from exc


def _trusted_header_auth_enabled() -> bool:
    settings = get_settings()
    return settings.trusted_header_auth_enabled and settings.environment in {"local", "test"}
