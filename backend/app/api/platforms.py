from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import (
    ExternalPlatform,
    PlatformAccount,
    PlatformAccountUserAccess,
    PlatformConnectionMethod,
    User,
)
from app.platforms.catalog import PlatformCatalogItem, default_platform_catalog
from app.schemas import (
    ErpConnectorRead,
    PlatformAccountCreate,
    PlatformAccountRead,
    PlatformAccountUserAccessCreate,
    PlatformAccountUserAccessDetail,
    PlatformAccountUserAccessRead,
    PlatformAdminAccountRead,
    PlatformAdminOverviewRead,
    PlatformConnectionMethodRead,
)
from app.services.audit import public_state, record_audit
from app.services.access_control import require_tenant_wide_access
from app.services.erp import erp_connector_catalog

router = APIRouter(prefix="/platforms", tags=["platforms"])
tenant_router = APIRouter(prefix="/tenant-platforms", tags=["tenant-platforms"])


@router.get("/catalog", response_model=list[PlatformCatalogItem])
def list_platform_catalog() -> list[PlatformCatalogItem]:
    return default_platform_catalog()


@tenant_router.get("/erp-connectors", response_model=list[ErpConnectorRead])
def list_tenant_erp_connectors(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[ErpConnectorRead]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return erp_connector_catalog()


@tenant_router.get("/accounts", response_model=list[PlatformAccountRead])
@router.get("/accounts", response_model=list[PlatformAccountRead])
def list_platform_accounts(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[PlatformAccount]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(
        session.scalars(
            select(PlatformAccount)
            .join(ExternalPlatform, ExternalPlatform.id == PlatformAccount.external_platform_id)
            .where(PlatformAccount.tenant_id == tenant_id)
            .where(ExternalPlatform.status != "removed")
            .order_by(PlatformAccount.id)
        )
    )


@tenant_router.post("/accounts", response_model=PlatformAccountRead, status_code=201)
@router.post("/accounts", response_model=PlatformAccountRead, status_code=201)
def create_platform_account(
    payload: PlatformAccountCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> PlatformAccount:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    platform = session.get(ExternalPlatform, payload.external_platform_id)
    if platform is None or platform.status == "removed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found.")
    account = PlatformAccount(tenant_id=tenant_id, **payload.model_dump())
    session.add(account)
    session.flush()
    audit_payload = payload.model_dump()
    audit_payload["encrypted_secret_ref"] = "***" if payload.encrypted_secret_ref else None
    record_audit(
        session,
        tenant_id=tenant_id,
        action="platform_account.create",
        entity_type="platform_account",
        entity_id=account.id,
        after=public_state(audit_payload | {"id": account.id}),
    )
    session.commit()
    session.refresh(account)
    return account


@tenant_router.get("/access", response_model=list[PlatformAdminOverviewRead])
@router.get("/admin/access", response_model=list[PlatformAdminOverviewRead])
def list_platform_admin_access(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[PlatformAdminOverviewRead]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    platforms = list(
        session.scalars(
            select(ExternalPlatform)
            .where(ExternalPlatform.status != "removed")
            .order_by(ExternalPlatform.name)
        )
    )
    methods = list(
        session.scalars(
            select(PlatformConnectionMethod).order_by(
                PlatformConnectionMethod.external_platform_id,
                PlatformConnectionMethod.method_key,
            )
        )
    )
    accounts = list(
        session.scalars(
            select(PlatformAccount)
            .where(PlatformAccount.tenant_id == tenant_id)
            .order_by(PlatformAccount.external_platform_id, PlatformAccount.display_name)
        )
    )
    access_rows = session.execute(
        select(PlatformAccountUserAccess, User)
        .join(User, User.id == PlatformAccountUserAccess.user_id)
        .where(PlatformAccountUserAccess.tenant_id == tenant_id)
        .order_by(User.email)
    ).all()

    methods_by_platform: dict[int, list[PlatformConnectionMethodRead]] = {}
    for method in methods:
        methods_by_platform.setdefault(method.external_platform_id, []).append(
            PlatformConnectionMethodRead.model_validate(method)
        )

    access_by_account: dict[int, list[PlatformAccountUserAccessDetail]] = {}
    for access, user in access_rows:
        access_by_account.setdefault(access.platform_account_id, []).append(
            _access_detail(access, user)
        )

    accounts_by_platform: dict[int, list[PlatformAdminAccountRead]] = {}
    for account in accounts:
        account_read = PlatformAccountRead.model_validate(account)
        accounts_by_platform.setdefault(account.external_platform_id, []).append(
            PlatformAdminAccountRead(
                **account_read.model_dump(),
                assigned_users=access_by_account.get(account.id, []),
            )
        )

    return [
        PlatformAdminOverviewRead(
            id=platform.id,
            platform_key=platform.platform_key,
            name=platform.name,
            status=platform.status,
            is_commercial=platform.is_commercial,
            notes=platform.notes,
            methods=methods_by_platform.get(platform.id, []),
            accounts=accounts_by_platform.get(platform.id, []),
        )
        for platform in platforms
    ]


@tenant_router.get(
    "/accounts/{account_id}/user-access",
    response_model=list[PlatformAccountUserAccessDetail],
)
@router.get(
    "/accounts/{account_id}/user-access",
    response_model=list[PlatformAccountUserAccessDetail],
)
def list_platform_account_user_access(
    account_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[PlatformAccountUserAccessDetail]:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    _require_platform_account(session, tenant_id, account_id)
    rows = session.execute(
        select(PlatformAccountUserAccess, User)
        .join(User, User.id == PlatformAccountUserAccess.user_id)
        .where(
            PlatformAccountUserAccess.tenant_id == tenant_id,
            PlatformAccountUserAccess.platform_account_id == account_id,
        )
        .order_by(User.email)
    ).all()
    return [_access_detail(access, user) for access, user in rows]


@tenant_router.post(
    "/accounts/{account_id}/user-access",
    response_model=PlatformAccountUserAccessRead,
    status_code=201,
)
@router.post(
    "/accounts/{account_id}/user-access",
    response_model=PlatformAccountUserAccessRead,
    status_code=201,
)
def grant_platform_account_user_access(
    account_id: int,
    payload: PlatformAccountUserAccessCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> PlatformAccountUserAccess:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    account = _require_platform_account(session, tenant_id, account_id)
    user = session.scalar(select(User).where(User.tenant_id == tenant_id, User.id == payload.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    access = session.scalar(
        select(PlatformAccountUserAccess).where(
            PlatformAccountUserAccess.tenant_id == tenant_id,
            PlatformAccountUserAccess.platform_account_id == account.id,
            PlatformAccountUserAccess.user_id == user.id,
        )
    )
    before = _access_public_state(access) if access is not None else None
    if access is None:
        access = PlatformAccountUserAccess(
            tenant_id=tenant_id,
            platform_account_id=account.id,
            user_id=user.id,
            **payload.model_dump(exclude={"user_id"}),
        )
        session.add(access)
    else:
        access.access_level = payload.access_level
        access.permissions = payload.permissions
        access.allowed_operations = payload.allowed_operations
        access.status = payload.status
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_account_user_access.upsert",
        entity_type="platform_account_user_access",
        entity_id=access.id,
        before=before,
        after=public_state(
            {
                "id": access.id,
                "platform_account_id": account.id,
                "external_platform_id": account.external_platform_id,
                "user_id": user.id,
                "access_level": access.access_level,
                "permissions": access.permissions,
                "allowed_operations": access.allowed_operations,
                "status": access.status,
            }
        ),
    )
    session.commit()
    session.refresh(access)
    return access


@tenant_router.delete("/accounts/{account_id}/user-access/{user_id}", status_code=204)
@router.delete("/accounts/{account_id}/user-access/{user_id}", status_code=204)
def revoke_platform_account_user_access(
    account_id: int,
    user_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    _require_platform_account(session, tenant_id, account_id)
    access = session.scalar(
        select(PlatformAccountUserAccess).where(
            PlatformAccountUserAccess.tenant_id == tenant_id,
            PlatformAccountUserAccess.platform_account_id == account_id,
            PlatformAccountUserAccess.user_id == user_id,
        )
    )
    if access is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform user access not found.")
    before = _access_public_state(access)
    access.status = "revoked"
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_account_user_access.revoke",
        entity_type="platform_account_user_access",
        entity_id=access.id,
        before=before,
        after=public_state(
            {
                "id": access.id,
                "platform_account_id": account_id,
                "user_id": user_id,
                "status": "revoked",
            }
        ),
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _require_platform_account(session: DbSession, tenant_id: int, account_id: int) -> PlatformAccount:
    account = session.scalar(
        select(PlatformAccount).where(
            PlatformAccount.tenant_id == tenant_id,
            PlatformAccount.id == account_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found.")
    return account


def _access_detail(access: PlatformAccountUserAccess, user: User) -> PlatformAccountUserAccessDetail:
    return PlatformAccountUserAccessDetail(
        id=access.id,
        tenant_id=access.tenant_id,
        platform_account_id=access.platform_account_id,
        user_id=access.user_id,
        access_level=access.access_level,
        permissions=access.permissions,
        allowed_operations=access.allowed_operations,
        status=access.status,
        user_name=user.name,
        user_email=user.email,
    )


def _access_public_state(access: PlatformAccountUserAccess) -> dict[str, Any]:
    return public_state(
        {
            "id": access.id,
            "tenant_id": access.tenant_id,
            "platform_account_id": access.platform_account_id,
            "user_id": access.user_id,
            "access_level": access.access_level,
            "permissions": access.permissions,
            "allowed_operations": access.allowed_operations,
            "status": access.status,
        }
    )
