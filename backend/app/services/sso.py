from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import IdentityProvider, SsoAuthorizationState, User, UserIdentity

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
DEFAULT_OIDC_SCOPES = ["openid", "profile", "email"]


class SsoConfigurationError(RuntimeError):
    pass


def configure_google_provider(
    session: Session,
    *,
    tenant_id: int,
    client_id: str | None,
    encrypted_client_secret_ref: str,
    allowed_domains: list[str],
    auto_provision: bool,
    status_value: str,
) -> IdentityProvider:
    provider = session.scalar(
        select(IdentityProvider).where(
            IdentityProvider.tenant_id == tenant_id,
            IdentityProvider.provider_key == "google",
        )
    )
    normalized_domains = sorted({domain.strip().lower() for domain in allowed_domains if domain.strip()})
    if provider is None:
        provider = IdentityProvider(
            tenant_id=tenant_id,
            provider_key="google",
            name="Google Workspace",
            provider_type="oidc",
            issuer=GOOGLE_ISSUER,
            discovery_url=GOOGLE_DISCOVERY_URL,
            authorization_endpoint=GOOGLE_AUTHORIZATION_ENDPOINT,
            token_endpoint=GOOGLE_TOKEN_ENDPOINT,
            jwks_uri=GOOGLE_JWKS_URI,
            userinfo_endpoint=GOOGLE_USERINFO_ENDPOINT,
            client_id=client_id,
            encrypted_client_secret_ref=encrypted_client_secret_ref,
            scopes=DEFAULT_OIDC_SCOPES,
            allowed_domains=normalized_domains,
            auto_provision=auto_provision,
            status=status_value,
        )
        session.add(provider)
    else:
        provider.client_id = client_id
        provider.encrypted_client_secret_ref = encrypted_client_secret_ref
        provider.allowed_domains = normalized_domains
        provider.auto_provision = auto_provision
        provider.status = status_value
    session.flush()
    return provider


def create_authorization_request(
    session: Session,
    *,
    provider: IdentityProvider,
    redirect_uri: str,
    next_url: str | None,
    settings: Settings,
) -> tuple[str, SsoAuthorizationState]:
    if provider.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO provider is not active.")
    if not provider.client_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO provider client_id is missing.")
    validate_oauth_redirects(redirect_uri=redirect_uri, next_url=next_url, settings=settings)

    code_verifier = token_urlsafe(64)
    state_value = token_urlsafe(48)
    nonce = token_urlsafe(48)
    authorization_state = SsoAuthorizationState(
        tenant_id=provider.tenant_id,
        identity_provider_id=provider.id,
        state=state_value,
        nonce=nonce,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        next_url=next_url,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.sso_state_ttl_minutes),
    )
    session.add(authorization_state)
    session.flush()

    authorization_url = build_google_authorization_url(
        client_id=provider.client_id,
        authorization_endpoint=provider.authorization_endpoint,
        redirect_uri=redirect_uri,
        state=state_value,
        nonce=nonce,
        code_verifier=code_verifier,
        scopes=provider.scopes or DEFAULT_OIDC_SCOPES,
        hosted_domain=provider.allowed_domains[0] if provider.allowed_domains else None,
    )
    return authorization_url, authorization_state


def validate_oauth_redirects(*, redirect_uri: str, next_url: str | None, settings: Settings) -> None:
    _validate_allowed_url(redirect_uri, settings=settings, field_name="redirect_uri", require_absolute=True)
    if next_url:
        _validate_allowed_url(next_url, settings=settings, field_name="next_url", require_absolute=False)


async def complete_google_callback(
    session: Session,
    *,
    tenant_id: int,
    state_value: str,
    code: str,
    settings: Settings,
) -> tuple[User, UserIdentity, str, int, str | None]:
    authorization_state = session.scalar(
        select(SsoAuthorizationState).where(
            SsoAuthorizationState.tenant_id == tenant_id,
            SsoAuthorizationState.state == state_value,
        )
    )
    if authorization_state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid SSO state.")
    now = datetime.now(timezone.utc)
    expires_at = _aware_utc(authorization_state.expires_at)
    if authorization_state.consumed_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired SSO state.")

    provider = session.get(IdentityProvider, authorization_state.identity_provider_id)
    if provider is None or provider.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO provider not found.")
    if provider.provider_key != "google":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported SSO provider.")
    if not provider.client_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO provider client_id is missing.")

    client_secret = _resolve_client_secret(provider, settings)
    token_payload = await _exchange_code_for_tokens(
        provider,
        client_id=provider.client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=authorization_state.redirect_uri,
        code_verifier=authorization_state.code_verifier,
    )
    id_token = token_payload.get("id_token")
    if not isinstance(id_token, str):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google did not return an ID token.")
    claims = verify_google_id_token(
        id_token,
        provider=provider,
        client_id=provider.client_id,
        expected_nonce=authorization_state.nonce,
    )
    user, identity = _upsert_sso_identity(session, tenant_id=tenant_id, provider=provider, claims=claims)
    authorization_state.consumed_at = now
    identity.last_login_at = now
    user.last_login_at = now
    access_token = create_local_access_token(user=user, tenant_id=tenant_id, settings=settings)
    return user, identity, access_token, settings.sso_access_token_minutes * 60, authorization_state.next_url


def verify_google_id_token(
    id_token: str,
    *,
    provider: IdentityProvider,
    client_id: str,
    expected_nonce: str,
) -> dict[str, Any]:
    return verify_google_id_token_claims(
        id_token,
        jwks_uri=provider.jwks_uri,
        allowed_domains=provider.allowed_domains,
        client_id=client_id,
        expected_nonce=expected_nonce,
    )


def verify_google_id_token_claims(
    id_token: str,
    *,
    jwks_uri: str,
    allowed_domains: list[str],
    client_id: str,
    expected_nonce: str,
) -> dict[str, Any]:
    try:
        signing_key = PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            options={"verify_iss": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google ID token.") from exc

    if claims.get("iss") not in {GOOGLE_ISSUER, "accounts.google.com"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google issuer.")
    if claims.get("nonce") != expected_nonce:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google nonce.")
    if allowed_domains and claims.get("hd") not in set(allowed_domains):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google hosted domain denied.")
    return claims


def build_google_authorization_url(
    *,
    client_id: str,
    authorization_endpoint: str = GOOGLE_AUTHORIZATION_ENDPOINT,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_verifier: str,
    scopes: list[str] | None = None,
    hosted_domain: str | None = None,
) -> str:
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes or DEFAULT_OIDC_SCOPES),
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
        "access_type": "online",
        "include_granted_scopes": "true",
    }
    if hosted_domain:
        params["hd"] = hosted_domain
    return f"{authorization_endpoint}?{urlencode(params)}"


def _validate_allowed_url(
    value: str,
    *,
    settings: Settings,
    field_name: str,
    require_absolute: bool,
) -> None:
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid {field_name}.")
        if parsed.netloc not in settings.sso.allowed_redirect_hosts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} host is not allowed.",
            )
        return
    if require_absolute:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must be absolute.")
    if not value.startswith("/") or value.startswith("//"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid {field_name}.")


def create_local_access_token(*, user: User, tenant_id: int, settings: Settings) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.sso_access_token_minutes)
    payload = {
        "sub": str(user.id),
        "tenant_id": tenant_id,
        "email": user.email,
        "name": user.name,
        "role_id": user.role_id,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_local_access_token(token: str, *, settings: Settings) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from exc
    return claims


async def _exchange_code_for_tokens(
    provider: IdentityProvider,
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    return await exchange_google_code_for_tokens(
        token_endpoint=provider.token_endpoint,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )


async def exchange_google_code_for_tokens(
    *,
    token_endpoint: str = GOOGLE_TOKEN_ENDPOINT,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(token_endpoint, data=data)
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google token exchange failed.")
    return cast(dict[str, Any], response.json())


def _upsert_sso_identity(
    session: Session,
    *,
    tenant_id: int,
    provider: IdentityProvider,
    claims: dict[str, Any],
) -> tuple[User, UserIdentity]:
    subject = str(claims.get("sub") or "")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google subject is missing.")
    email = str(claims.get("email") or "")
    email_verified = claims.get("email_verified") is True or claims.get("email_verified") == "true"
    hosted_domain = str(claims.get("hd") or "") or None
    identity = session.scalar(
        select(UserIdentity).where(
            UserIdentity.identity_provider_id == provider.id,
            UserIdentity.subject == subject,
        )
    )
    if identity is not None:
        user = session.get(User, identity.user_id)
        if user is None or user.tenant_id != tenant_id or user.status != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Linked user denied.")
        identity.email = email or identity.email
        identity.email_verified = email_verified
        identity.hosted_domain = hosted_domain
        return user, identity

    user = None
    if email and email_verified:
        user = session.scalar(select(User).where(User.tenant_id == tenant_id, User.email == email))
    if user is None:
        if not provider.auto_provision or not email or not email_verified:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google account is not linked.")
        user = User(
            tenant_id=tenant_id,
            email=email,
            name=str(claims.get("name") or email),
            role_id=None,
            mfa_enabled=True,
            status="active",
            email_verified_at=datetime.now(timezone.utc) if email_verified else None,
        )
        session.add(user)
        session.flush()
    identity = UserIdentity(
        tenant_id=tenant_id,
        user_id=user.id,
        identity_provider_id=provider.id,
        subject=subject,
        email=email or None,
        email_verified=email_verified,
        hosted_domain=hosted_domain,
    )
    session.add(identity)
    session.flush()
    return user, identity


def _resolve_client_secret(provider: IdentityProvider, settings: Settings) -> str:
    if provider.provider_key == "google" and provider.encrypted_client_secret_ref == "env:IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET":
        if settings.google_oidc_client_secret:
            return settings.google_oidc_client_secret
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Google SSO client secret is missing.")
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unsupported SSO secret reference.")


def token_urlsafe(bytes_count: int) -> str:
    return secrets.token_urlsafe(bytes_count).rstrip("=")


def pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
