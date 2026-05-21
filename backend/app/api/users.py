from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import Company, PlatformAccount, Role, User, UserCompanyAccess, UserPermissionGrant
from app.schemas import (
    CompanyRead,
    EffectiveCompanyPermissions,
    RoleCreate,
    RoleRead,
    UserCompanyAccessCreate,
    UserCompanyAccessDetail,
    UserCompanyAccessRead,
    UserCreate,
    UserEffectivePermissions,
    UserPermissionGrantCreate,
    UserPermissionGrantRead,
    UserRead,
)
from app.services.audit import public_state, record_audit
from app.services.access_control import (
    accessible_company_ids,
    company_permission_sets,
    require_actor_user,
    require_tenant_wide_access,
    tenant_permission_sets,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[User]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(session.scalars(select(User).where(User.tenant_id == tenant_id).order_by(User.email)))


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> User:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    if payload.role_id is not None:
        role = session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.id == payload.role_id))
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")
    user = User(tenant_id=tenant_id, **payload.model_dump())
    session.add(user)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        after=public_state(payload.model_dump() | {"id": user.id}),
    )
    session.commit()
    session.refresh(user)
    return user


@router.get("/roles", response_model=list[RoleRead])
def list_roles(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[Role]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(session.scalars(select(Role).where(Role.tenant_id == tenant_id).order_by(Role.name)))


@router.post("/roles", response_model=RoleRead, status_code=201)
def create_role(
    payload: RoleCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Role:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    role = Role(tenant_id=tenant_id, **payload.model_dump())
    session.add(role)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        action="role.create",
        entity_type="role",
        entity_id=role.id,
        after=public_state(payload.model_dump() | {"id": role.id}),
    )
    session.commit()
    session.refresh(role)
    return role


@router.post("/{user_id}/company-access", response_model=UserCompanyAccessRead, status_code=201)
def grant_company_access(
    user_id: int,
    payload: UserCompanyAccessCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> UserCompanyAccess:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    user = _require_user(session, tenant_id, user_id)
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.id == payload.company_id)
    )
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    access = session.scalar(
        select(UserCompanyAccess).where(
            UserCompanyAccess.tenant_id == tenant_id,
            UserCompanyAccess.user_id == user.id,
            UserCompanyAccess.company_id == company.id,
        )
    )
    if access is None:
        access = UserCompanyAccess(tenant_id=tenant_id, user_id=user.id, **payload.model_dump())
        session.add(access)
    else:
        access.access_level = payload.access_level
        access.role_name = payload.role_name
        access.permissions = payload.permissions
        access.status = payload.status
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        action="user_company_access.upsert",
        entity_type="user_company_access",
        entity_id=access.id,
        after=public_state(payload.model_dump() | {"id": access.id, "user_id": user.id}),
    )
    session.commit()
    session.refresh(access)
    return access


@router.get("/{user_id}/company-access", response_model=list[UserCompanyAccessDetail])
def list_company_access(
    user_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[UserCompanyAccessDetail]:
    _require_user_management_or_self(session, tenant_id, actor_user_id, user_id)
    _require_user(session, tenant_id, user_id)
    rows = session.execute(
        select(UserCompanyAccess, Company)
        .join(Company, Company.id == UserCompanyAccess.company_id)
        .where(UserCompanyAccess.tenant_id == tenant_id, UserCompanyAccess.user_id == user_id)
        .order_by(Company.name)
    ).all()
    return [
        UserCompanyAccessDetail(
            id=access.id,
            tenant_id=access.tenant_id,
            user_id=access.user_id,
            company_id=access.company_id,
            access_level=access.access_level,
            role_name=access.role_name,
            permissions=access.permissions,
            status=access.status,
            company_name=company.name,
            company_type=company.company_type,
        )
        for access, company in rows
    ]


@router.post("/{user_id}/permission-grants", response_model=UserPermissionGrantRead, status_code=201)
def grant_user_permission(
    user_id: int,
    payload: UserPermissionGrantCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> UserPermissionGrant:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    user = _require_user(session, tenant_id, user_id)
    _validate_permission_scope(session, tenant_id=tenant_id, payload=payload)
    grant = UserPermissionGrant(
        tenant_id=tenant_id,
        user_id=user.id,
        created_by=actor_user_id,
        **payload.model_dump(),
    )
    session.add(grant)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user_permission_grant.create",
        entity_type="user_permission_grant",
        entity_id=grant.id,
        after=public_state(_permission_grant_state(grant)),
    )
    session.commit()
    session.refresh(grant)
    return grant


@router.get("/{user_id}/permission-grants", response_model=list[UserPermissionGrantRead])
def list_user_permission_grants(
    user_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    include_revoked: bool = False,
) -> list[UserPermissionGrant]:
    _require_user_management_or_self(session, tenant_id, actor_user_id, user_id)
    _require_user(session, tenant_id, user_id)
    clauses = [
        UserPermissionGrant.tenant_id == tenant_id,
        UserPermissionGrant.user_id == user_id,
    ]
    if not include_revoked:
        clauses.append(UserPermissionGrant.status == "active")
    return list(
        session.scalars(
            select(UserPermissionGrant).where(*clauses).order_by(
                UserPermissionGrant.scope_type,
                UserPermissionGrant.scope_id,
                UserPermissionGrant.permission,
                UserPermissionGrant.id,
            )
        )
    )


@router.delete("/{user_id}/permission-grants/{grant_id}", status_code=204)
def revoke_user_permission_grant(
    user_id: int,
    grant_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    _require_user(session, tenant_id, user_id)
    grant = session.scalar(
        select(UserPermissionGrant).where(
            UserPermissionGrant.tenant_id == tenant_id,
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.id == grant_id,
        )
    )
    if grant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission grant not found.")
    before = _permission_grant_state(grant)
    grant.status = "revoked"
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user_permission_grant.revoke",
        entity_type="user_permission_grant",
        entity_id=grant.id,
        before=public_state(before),
        after=public_state(_permission_grant_state(grant)),
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/effective-permissions", response_model=UserEffectivePermissions)
def get_user_effective_permissions(
    user_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
) -> UserEffectivePermissions:
    _require_user_management_or_self(session, tenant_id, actor_user_id, user_id)
    user = _require_user(session, tenant_id, user_id)
    role_permissions = _role_permissions(session, tenant_id=tenant_id, user=user)
    tenant_permissions, tenant_denied = tenant_permission_sets(session, tenant_id=tenant_id, user=user)
    companies = _companies_for_effective_permissions(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_user_id=user_id,
        company_id=company_id,
    )
    company_rows = []
    for company in companies:
        allowed, denied, sources = company_permission_sets(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=company.id,
        )
        access = session.scalar(
            select(UserCompanyAccess).where(
                UserCompanyAccess.tenant_id == tenant_id,
                UserCompanyAccess.user_id == user_id,
                UserCompanyAccess.company_id == company.id,
                UserCompanyAccess.status == "active",
            )
        )
        company_rows.append(
            EffectiveCompanyPermissions(
                company_id=company.id,
                company_name=company.name,
                access_level=access.access_level if access else None,
                role_name=access.role_name if access else None,
                permissions=sorted(allowed),
                denied_permissions=sorted(denied),
                sources=sources,
            )
        )
    return UserEffectivePermissions(
        user_id=user_id,
        tenant_id=tenant_id,
        role_permissions=sorted(role_permissions),
        tenant_permissions=sorted(tenant_permissions),
        tenant_denied_permissions=sorted(tenant_denied),
        company_permissions=company_rows,
    )


@router.get("/{user_id}/companies", response_model=list[CompanyRead])
def list_user_companies(
    user_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[Company]:
    _require_user_management_or_self(session, tenant_id, actor_user_id, user_id)
    _require_user(session, tenant_id, user_id)
    return list(
        session.scalars(
            select(Company)
            .join(UserCompanyAccess, UserCompanyAccess.company_id == Company.id)
            .where(
                UserCompanyAccess.tenant_id == tenant_id,
                UserCompanyAccess.user_id == user_id,
                UserCompanyAccess.status == "active",
            )
            .order_by(Company.name)
        )
    )


@router.delete("/{user_id}/company-access/{company_id}", status_code=204)
def revoke_company_access(
    user_id: int,
    company_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    access = session.scalar(
        select(UserCompanyAccess).where(
            UserCompanyAccess.tenant_id == tenant_id,
            UserCompanyAccess.user_id == user_id,
            UserCompanyAccess.company_id == company_id,
        )
    )
    if access is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company access not found.")
    access.status = "revoked"
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        action="user_company_access.revoke",
        entity_type="user_company_access",
        entity_id=access.id,
        after=public_state({"id": access.id, "user_id": user_id, "company_id": company_id, "status": "revoked"}),
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _require_user(session: DbSession, tenant_id: int, user_id: int) -> User:
    user = session.scalar(select(User).where(User.tenant_id == tenant_id, User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def _require_user_management_or_self(
    session: DbSession,
    tenant_id: int,
    actor_user_id: int | None,
    target_user_id: int,
) -> None:
    if actor_user_id is None:
        return
    require_actor_user(session, tenant_id=tenant_id, user_id=actor_user_id)
    if actor_user_id == target_user_id:
        return
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)


def _validate_permission_scope(
    session: DbSession,
    *,
    tenant_id: int,
    payload: UserPermissionGrantCreate,
) -> None:
    if payload.scope_type in {"tenant", "system"}:
        if payload.scope_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{payload.scope_type} scoped grants must not include scope_id.",
            )
        return
    if payload.scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{payload.scope_type} scoped grants require scope_id.",
        )
    if payload.scope_type == "company":
        exists = session.scalar(
            select(Company.id).where(Company.tenant_id == tenant_id, Company.id == payload.scope_id)
        )
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
        return
    if payload.scope_type == "platform_account":
        exists = session.scalar(
            select(PlatformAccount.id).where(
                PlatformAccount.tenant_id == tenant_id,
                PlatformAccount.id == payload.scope_id,
            )
        )
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found.")


def _permission_grant_state(grant: UserPermissionGrant) -> dict[str, object]:
    return {
        "id": grant.id,
        "tenant_id": grant.tenant_id,
        "user_id": grant.user_id,
        "scope_type": grant.scope_type,
        "scope_id": grant.scope_id,
        "permission": grant.permission,
        "effect": grant.effect,
        "reason": grant.reason,
        "status": grant.status,
        "created_by": grant.created_by,
    }


def _role_permissions(session: DbSession, *, tenant_id: int, user: User) -> set[str]:
    if user.role_id is None:
        return set()
    role = session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.id == user.role_id))
    if role is None:
        return set()
    permissions = {permission.strip().lower() for permission in role.permissions if permission.strip()}
    if role.name == "tenant_admin":
        permissions.add("tenant.admin")
    return permissions


def _companies_for_effective_permissions(
    session: DbSession,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    target_user_id: int,
    company_id: int | None,
) -> list[Company]:
    if company_id is not None:
        company = session.scalar(select(Company).where(Company.tenant_id == tenant_id, Company.id == company_id))
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
        if actor_user_id == target_user_id:
            allowed = accessible_company_ids(session, tenant_id=tenant_id, user_id=target_user_id)
            if allowed is not None and company_id not in allowed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company access denied.")
        return [company]
    allowed = accessible_company_ids(session, tenant_id=tenant_id, user_id=target_user_id)
    query = select(Company).where(Company.tenant_id == tenant_id)
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(Company.id.in_(allowed))
    return list(session.scalars(query.order_by(Company.name)))
