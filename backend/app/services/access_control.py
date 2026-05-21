from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, Role, User, UserCompanyAccess, UserPermissionGrant


TENANT_WIDE_PERMISSIONS = {"tenant.admin", "company.all", "settings.write"}
SYSTEM_ADMIN_PERMISSIONS = {"system.admin"}
ACCESS_LEVEL_PERMISSIONS = {
    "viewer": {"company.read"},
    "editor": {"company.read", "worker.read", "document.read", "document.write"},
    "manager": {"company.read", "worker.read", "worker.write", "document.read", "document.write"},
    "admin": {
        "company.read",
        "company.write",
        "worker.read",
        "worker.write",
        "document.read",
        "document.write",
        "document.validate",
        "requirement.read",
        "requirement.write",
    },
}


def require_actor_user(session: Session, *, tenant_id: int, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    user = session.scalar(
        select(User).where(
            User.tenant_id == tenant_id,
            User.id == user_id,
            User.status == "active",
        )
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor user denied.")
    return user


def has_tenant_wide_access(session: Session, *, tenant_id: int, user_id: int | None) -> bool:
    user = require_actor_user(session, tenant_id=tenant_id, user_id=user_id)
    if user is None:
        return False
    allowed, denied = tenant_permission_sets(session, tenant_id=tenant_id, user=user)
    if TENANT_WIDE_PERMISSIONS.intersection(denied):
        return False
    return bool(TENANT_WIDE_PERMISSIONS.intersection(allowed))


def tenant_permission_sets(session: Session, *, tenant_id: int, user: User) -> tuple[set[str], set[str]]:
    allowed: set[str] = set()
    denied: set[str] = set()
    role = session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.id == user.role_id))
    if role is not None:
        allowed.update(_normalize_permissions(role.permissions))
        if role.name == "tenant_admin":
            allowed.add("tenant.admin")
    for grant in _active_permission_grants(session, tenant_id=tenant_id, user_id=user.id, scope_type="tenant"):
        _apply_grant(allowed, denied, grant)
    return allowed - denied, denied


def require_tenant_wide_access(session: Session, *, tenant_id: int, user_id: int | None) -> None:
    if not has_tenant_wide_access(session, tenant_id=tenant_id, user_id=user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant administration denied.")


def has_system_admin_access(session: Session, *, tenant_id: int, user_id: int | None) -> bool:
    user = require_actor_user(session, tenant_id=tenant_id, user_id=user_id)
    if user is None:
        return False
    allowed, denied = tenant_permission_sets(session, tenant_id=tenant_id, user=user)
    for grant in _active_permission_grants(session, tenant_id=tenant_id, user_id=user.id, scope_type="system"):
        _apply_grant(allowed, denied, grant)
    if SYSTEM_ADMIN_PERMISSIONS.intersection(denied):
        return False
    return bool(SYSTEM_ADMIN_PERMISSIONS.intersection(allowed))


def require_system_admin_access(session: Session, *, tenant_id: int, user_id: int | None) -> None:
    if not has_system_admin_access(session, tenant_id=tenant_id, user_id=user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System administration denied.")


def accessible_company_ids(session: Session, *, tenant_id: int, user_id: int | None) -> list[int] | None:
    if user_id is None:
        return []
    if has_tenant_wide_access(session, tenant_id=tenant_id, user_id=user_id):
        return None
    company_access_ids = set(
        session.scalars(
            select(UserCompanyAccess.company_id).where(
                UserCompanyAccess.tenant_id == tenant_id,
                UserCompanyAccess.user_id == user_id,
                UserCompanyAccess.status == "active",
            )
        )
    )
    grant_company_ids = {
        int(grant.scope_id)
        for grant in _active_permission_grants(session, tenant_id=tenant_id, user_id=user_id, scope_type="company")
        if grant.effect == "allow" and grant.scope_id is not None and grant.permission.endswith(".read")
    }
    denied_company_ids = {
        int(grant.scope_id)
        for grant in _active_permission_grants(session, tenant_id=tenant_id, user_id=user_id, scope_type="company")
        if grant.effect == "deny" and grant.scope_id is not None and grant.permission == "company.read"
    }
    return sorted((company_access_ids | grant_company_ids) - denied_company_ids)


def accessible_company_ids_for_permission(
    session: Session,
    *,
    tenant_id: int,
    user_id: int | None,
    permission: str,
) -> list[int] | None:
    allowed_company_ids = accessible_company_ids(session, tenant_id=tenant_id, user_id=user_id)
    if allowed_company_ids is None:
        return None
    return [
        company_id
        for company_id in allowed_company_ids
        if has_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=company_id,
            permission=permission,
        )
    ]


def require_company_access(
    session: Session,
    *,
    tenant_id: int,
    user_id: int | None,
    company_id: int,
) -> None:
    company = session.scalar(select(Company).where(Company.tenant_id == tenant_id, Company.id == company_id))
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    allowed = accessible_company_ids(session, tenant_id=tenant_id, user_id=user_id)
    if allowed is not None and company_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company access denied.")


def require_company_permission(
    session: Session,
    *,
    tenant_id: int,
    user_id: int | None,
    company_id: int,
    permission: str,
) -> None:
    require_company_access(session, tenant_id=tenant_id, user_id=user_id, company_id=company_id)
    if not has_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        company_id=company_id,
        permission=permission,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{permission} denied.")


def company_permission_sets(
    session: Session,
    *,
    tenant_id: int,
    user_id: int,
    company_id: int,
) -> tuple[set[str], set[str], list[str]]:
    user = require_actor_user(session, tenant_id=tenant_id, user_id=user_id)
    if user is None:
        return set(), set(), []
    tenant_allowed, tenant_denied = tenant_permission_sets(session, tenant_id=tenant_id, user=user)
    allowed = set(tenant_allowed)
    denied = set(tenant_denied)
    sources = ["role_or_tenant"]
    access = session.scalar(
        select(UserCompanyAccess).where(
            UserCompanyAccess.tenant_id == tenant_id,
            UserCompanyAccess.user_id == user_id,
            UserCompanyAccess.company_id == company_id,
            UserCompanyAccess.status == "active",
        )
    )
    if access is not None:
        allowed.update(ACCESS_LEVEL_PERMISSIONS.get(access.access_level, set()))
        allowed.update(_normalize_permissions(access.permissions))
        sources.append("company_access")
    for grant in _active_permission_grants(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        scope_type="company",
        scope_id=company_id,
    ):
        _apply_grant(allowed, denied, grant)
        sources.append(f"grant:{grant.effect}")
    return allowed - denied, denied, sorted(set(sources))


def has_company_permission(
    session: Session,
    *,
    tenant_id: int,
    user_id: int | None,
    company_id: int,
    permission: str,
) -> bool:
    if user_id is None:
        return False
    allowed, denied, _sources = company_permission_sets(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        company_id=company_id,
    )
    normalized = permission.strip().lower()
    return normalized in allowed and normalized not in denied


def _active_permission_grants(
    session: Session,
    *,
    tenant_id: int,
    user_id: int,
    scope_type: str,
    scope_id: int | None = None,
) -> list[UserPermissionGrant]:
    clauses = [
        UserPermissionGrant.tenant_id == tenant_id,
        UserPermissionGrant.user_id == user_id,
        UserPermissionGrant.scope_type == scope_type,
        UserPermissionGrant.status == "active",
    ]
    if scope_id is not None:
        clauses.append(UserPermissionGrant.scope_id == scope_id)
    return list(session.scalars(select(UserPermissionGrant).where(*clauses).order_by(UserPermissionGrant.id)))


def _normalize_permissions(values: list[str]) -> set[str]:
    return {value.strip().lower() for value in values if value.strip()}


def _apply_grant(allowed: set[str], denied: set[str], grant: UserPermissionGrant) -> None:
    permission = grant.permission.strip().lower()
    if grant.effect == "deny":
        denied.add(permission)
        allowed.discard(permission)
        return
    if permission not in denied:
        allowed.add(permission)
