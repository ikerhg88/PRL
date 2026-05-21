from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, PublicTenantId, TenantId, require_tenant
from app.core.config import get_settings
from app.db.models import IdentityProvider, User
from app.schemas import (
    GoogleSsoConfigure,
    SsoCallbackRequest,
    SsoCallbackResponse,
    SsoProviderRead,
    SsoStartRequest,
    SsoStartResponse,
    UserIdentityRead,
    UserRead,
)
from app.services.access_control import require_tenant_wide_access
from app.services.audit import public_state, record_audit
from app.services.sso import (
    complete_google_callback,
    configure_google_provider,
    create_authorization_request,
    decode_local_access_token,
)

router = APIRouter(prefix="/auth/sso", tags=["auth-sso"])


@router.get("/providers", response_model=list[SsoProviderRead])
def list_sso_providers(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[IdentityProvider]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(
        session.scalars(
            select(IdentityProvider)
            .where(IdentityProvider.tenant_id == tenant_id)
            .order_by(IdentityProvider.provider_key)
        )
    )


@router.post("/providers/google", response_model=SsoProviderRead, status_code=201)
def configure_google_sso(
    payload: GoogleSsoConfigure,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> IdentityProvider:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    settings = get_settings()
    provider = configure_google_provider(
        session,
        tenant_id=tenant_id,
        client_id=payload.client_id or settings.google_oidc_client_id,
        encrypted_client_secret_ref=payload.encrypted_client_secret_ref,
        allowed_domains=payload.allowed_domains,
        auto_provision=payload.auto_provision,
        status_value=payload.status,
    )
    record_audit(
        session,
        tenant_id=tenant_id,
        action="sso_provider.google.configure",
        entity_type="identity_provider",
        entity_id=provider.id,
        after=public_state(
            {
                "provider_key": provider.provider_key,
                "client_id": provider.client_id,
                "encrypted_secret_ref": provider.encrypted_client_secret_ref,
                "allowed_domains": provider.allowed_domains,
                "auto_provision": provider.auto_provision,
                "status": provider.status,
            }
        ),
    )
    session.commit()
    session.refresh(provider)
    return provider


@router.post("/google/start", response_model=SsoStartResponse)
def start_google_sso(
    payload: SsoStartRequest,
    tenant_id: PublicTenantId,
    session: DbSession,
) -> SsoStartResponse:
    require_tenant(session, tenant_id)
    provider = _require_provider(session, tenant_id=tenant_id, provider_key="google")
    authorization_url, authorization_state = create_authorization_request(
        session,
        provider=provider,
        redirect_uri=payload.redirect_uri,
        next_url=payload.next_url,
        settings=get_settings(),
    )
    record_audit(
        session,
        tenant_id=tenant_id,
        action="sso.google.start",
        entity_type="identity_provider",
        entity_id=provider.id,
        after=public_state({"provider_key": "google", "redirect_uri": payload.redirect_uri}),
    )
    session.commit()
    return SsoStartResponse(
        provider_key="google",
        authorization_url=authorization_url,
        state=authorization_state.state,
        expires_at=authorization_state.expires_at,
    )


@router.post("/google/callback", response_model=SsoCallbackResponse)
async def complete_google_sso(
    payload: SsoCallbackRequest,
    tenant_id: PublicTenantId,
    session: DbSession,
) -> SsoCallbackResponse:
    require_tenant(session, tenant_id)
    user, identity, access_token, expires_in, next_url = await complete_google_callback(
        session,
        tenant_id=tenant_id,
        state_value=payload.state,
        code=payload.code,
        settings=get_settings(),
    )
    record_audit(
        session,
        tenant_id=tenant_id,
        action="sso.google.login",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        after=public_state({"identity_provider": "google", "user_id": user.id, "email": user.email}),
    )
    session.commit()
    session.refresh(user)
    session.refresh(identity)
    return SsoCallbackResponse(
        tenant_id=tenant_id,
        user=UserRead.model_validate(user),
        identity=UserIdentityRead.model_validate(identity),
        access_token=access_token,
        expires_in=expires_in,
        next_url=next_url,
    )


@router.get("/me", response_model=UserRead)
def get_sso_me(
    session: DbSession,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is required.")
    claims = decode_local_access_token(authorization.split(" ", 1)[1], settings=get_settings())
    user_id = int(claims["sub"])
    tenant_id = int(claims["tenant_id"])
    user = session.scalar(select(User).where(User.tenant_id == tenant_id, User.id == user_id))
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def _require_provider(session: DbSession, *, tenant_id: int, provider_key: str) -> IdentityProvider:
    provider = session.scalar(
        select(IdentityProvider).where(
            IdentityProvider.tenant_id == tenant_id,
            IdentityProvider.provider_key == provider_key,
        )
    )
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO provider not found.")
    return provider
