from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import DbSession, bearer_token_from_authorization
from app.core.config import get_settings
from app.db.models import (
    Company,
    OauthSignupState,
    Role,
    Tenant,
    TenantCommercialProfile,
    User,
    UserCompanyAccess,
    UserIdentity,
)
from app.db.seed import ROLE_DEFINITIONS
from app.schemas import (
    AuthCompanyAccess,
    AuthMe,
    AuthSession,
    CompanyOnboardingRequest,
    CompanyRead,
    EmailVerifyRequest,
    GoogleSignupCallbackRequest,
    GoogleSignupStartRequest,
    GoogleSignupStartResponse,
    LoginRequest,
    SignupRequest,
    SignupResponse,
    UserRead,
)
from app.services.audit import public_state, record_audit
from app.services.auth import (
    consume_email_verification_token,
    hash_password,
    issue_email_verification_token,
    normalize_email,
    verify_password,
)
from app.services.sso import (
    DEFAULT_OIDC_SCOPES,
    GOOGLE_AUTHORIZATION_ENDPOINT,
    GOOGLE_JWKS_URI,
    GOOGLE_TOKEN_ENDPOINT,
    build_google_authorization_url,
    configure_google_provider,
    create_local_access_token,
    decode_local_access_token,
    exchange_google_code_for_tokens,
    token_urlsafe,
    validate_oauth_redirects,
    verify_google_id_token_claims,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(payload: SignupRequest, session: DbSession) -> SignupResponse:
    settings = get_settings()
    email = normalize_email(payload.email)
    _ensure_email_not_registered(session, email=email, tenant_id=None)
    tenant_name = (payload.tenant_name or payload.company_name or payload.name).strip()
    if not tenant_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tenant name is required.")

    tenant = Tenant(name=tenant_name, tax_id=_blank_to_none(payload.tenant_tax_id), status="active")
    session.add(tenant)
    session.flush()
    _ensure_default_commercial_profile(session, tenant_id=tenant.id)
    role = _ensure_role(session, tenant_id=tenant.id, name="tenant_admin")
    company = _create_company_from_signup(session, tenant_id=tenant.id, payload=payload)
    user = User(
        tenant_id=tenant.id,
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        role_id=role.id,
        mfa_enabled=False,
        status="pending_email_verification",
    )
    session.add(user)
    session.flush()
    if company is not None:
        _grant_company_admin_access(session, tenant_id=tenant.id, user_id=user.id, company_id=company.id)
    raw_token = issue_email_verification_token(session, user=user, settings=settings)
    record_audit(
        session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
        action="auth.signup",
        entity_type="user",
        entity_id=user.id,
        after=public_state(
            {
                "tenant_id": tenant.id,
                "email": email,
                "company_id": company.id if company else None,
                "email_verification": "pending",
            }
        ),
    )
    session.commit()
    verification_url = f"{settings.frontend_base_url}/verify-email?token={raw_token}"
    expose_dev_token = settings.environment == "local" and settings.auth_dev_tokens_enabled
    return SignupResponse(
        tenant_id=tenant.id,
        user_id=user.id,
        company_id=company.id if company else None,
        email=email,
        verification_url=verification_url if expose_dev_token else None,
        dev_verification_token=raw_token if expose_dev_token else None,
        message="Account created. Verify the email before logging in.",
    )


@router.post("/verify-email", response_model=AuthSession)
def verify_email(payload: EmailVerifyRequest, session: DbSession) -> AuthSession:
    settings = get_settings()
    user = consume_email_verification_token(session, raw_token=payload.token)
    user.last_login_at = datetime.now(timezone.utc)
    access_token = create_local_access_token(user=user, tenant_id=user.tenant_id, settings=settings)
    record_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="auth.email.verify",
        entity_type="user",
        entity_id=user.id,
        after=public_state({"email": user.email, "status": user.status}),
    )
    session.commit()
    session.refresh(user)
    return _auth_session(session, user=user, access_token=access_token)


@router.post("/login", response_model=AuthSession)
def login(payload: LoginRequest, session: DbSession) -> AuthSession:
    settings = get_settings()
    email = "demo@demo.invalid" if payload.email.strip().lower() == "demo" else normalize_email(payload.email)
    statement = select(User).where(User.email == email)
    if payload.tenant_id is not None:
        statement = statement.where(User.tenant_id == payload.tenant_id)
    users = list(session.scalars(statement))
    if not users:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if len(users) > 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant ID is required for this email.")
    user = users[0]
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if user.email_verified_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email verification is required.")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active.")
    user.last_login_at = datetime.now(timezone.utc)
    access_token = create_local_access_token(user=user, tenant_id=user.tenant_id, settings=settings)
    record_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        after=public_state({"email": user.email}),
    )
    session.commit()
    session.refresh(user)
    return _auth_session(session, user=user, access_token=access_token)


@router.get("/me", response_model=AuthMe)
def me(session: DbSession, authorization: str | None = Header(default=None, alias="Authorization")) -> AuthMe:
    user = _current_user(session, authorization=authorization)
    return AuthMe(
        tenant_id=user.tenant_id,
        user=UserRead.model_validate(user),
        company_access=_company_access(session, user=user),
    )


@router.post("/companies/onboarding", response_model=CompanyRead, status_code=201)
def create_onboarding_company(
    payload: CompanyOnboardingRequest,
    session: DbSession,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Company:
    user = _current_user(session, authorization=authorization)
    company = Company(tenant_id=user.tenant_id, **payload.model_dump())
    session.add(company)
    session.flush()
    _grant_company_admin_access(session, tenant_id=user.tenant_id, user_id=user.id, company_id=company.id)
    record_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="auth.company.onboarding",
        entity_type="company",
        entity_id=company.id,
        after=public_state(payload.model_dump() | {"id": company.id}),
    )
    session.commit()
    session.refresh(company)
    return company


@router.post("/google/signup/start", response_model=GoogleSignupStartResponse)
def google_signup_start(payload: GoogleSignupStartRequest, session: DbSession) -> GoogleSignupStartResponse:
    settings = get_settings()
    if not settings.google_oidc_client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google OAuth client ID is not configured.",
        )
    validate_oauth_redirects(redirect_uri=payload.redirect_uri, next_url=payload.next_url, settings=settings)
    code_verifier = token_urlsafe(64)
    state_value = token_urlsafe(48)
    nonce = token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.sso_state_ttl_minutes)
    state = OauthSignupState(
        state=state_value,
        nonce=nonce,
        code_verifier=code_verifier,
        redirect_uri=payload.redirect_uri,
        next_url=payload.next_url,
        tenant_name=payload.tenant_name,
        tenant_tax_id=payload.tenant_tax_id,
        company_name=payload.company_name,
        company_tax_id=payload.company_tax_id,
        company_address=payload.company_address,
        expires_at=expires_at,
    )
    session.add(state)
    session.commit()
    authorization_url = build_google_authorization_url(
        client_id=settings.google_oidc_client_id,
        authorization_endpoint=GOOGLE_AUTHORIZATION_ENDPOINT,
        redirect_uri=payload.redirect_uri,
        state=state_value,
        nonce=nonce,
        code_verifier=code_verifier,
        scopes=DEFAULT_OIDC_SCOPES,
    )
    return GoogleSignupStartResponse(
        authorization_url=authorization_url,
        state=state_value,
        expires_at=expires_at,
    )


@router.post("/google/signup/callback", response_model=AuthSession)
async def google_signup_callback(payload: GoogleSignupCallbackRequest, session: DbSession) -> AuthSession:
    settings = get_settings()
    if not settings.google_oidc_client_id or not settings.google_oidc_client_secret:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Google OAuth client is not configured.")
    state = session.scalar(select(OauthSignupState).where(OauthSignupState.state == payload.state))
    if state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Google signup state.")
    now = datetime.now(timezone.utc)
    expires_at = _aware_utc(state.expires_at)
    if state.consumed_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired Google signup state.")
    token_payload = await exchange_google_code_for_tokens(
        token_endpoint=GOOGLE_TOKEN_ENDPOINT,
        client_id=settings.google_oidc_client_id,
        client_secret=settings.google_oidc_client_secret,
        code=payload.code,
        redirect_uri=state.redirect_uri,
        code_verifier=state.code_verifier,
    )
    id_token = token_payload.get("id_token")
    if not isinstance(id_token, str):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google did not return an ID token.")
    claims = verify_google_id_token_claims(
        id_token,
        jwks_uri=GOOGLE_JWKS_URI,
        allowed_domains=[],
        client_id=settings.google_oidc_client_id,
        expected_nonce=state.nonce,
    )
    email = normalize_email(str(claims.get("email") or ""))
    if claims.get("email_verified") not in {True, "true"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google email is not verified.")
    _ensure_email_not_registered(session, email=email, tenant_id=None)
    tenant_name = (state.tenant_name or state.company_name or str(claims.get("name") or email)).strip()
    tenant = Tenant(name=tenant_name, tax_id=_blank_to_none(state.tenant_tax_id), status="active")
    session.add(tenant)
    session.flush()
    _ensure_default_commercial_profile(session, tenant_id=tenant.id)
    role = _ensure_role(session, tenant_id=tenant.id, name="tenant_admin")
    company = _create_company_from_google_state(session, tenant_id=tenant.id, state=state)
    user = User(
        tenant_id=tenant.id,
        email=email,
        name=str(claims.get("name") or email),
        role_id=role.id,
        mfa_enabled=True,
        status="active",
        email_verified_at=now,
        last_login_at=now,
    )
    session.add(user)
    session.flush()
    if company is not None:
        _grant_company_admin_access(session, tenant_id=tenant.id, user_id=user.id, company_id=company.id)
    provider = configure_google_provider(
        session,
        tenant_id=tenant.id,
        client_id=settings.google_oidc_client_id,
        encrypted_client_secret_ref="env:IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET",
        allowed_domains=[],
        auto_provision=True,
        status_value="active",
    )
    identity = UserIdentity(
        tenant_id=tenant.id,
        user_id=user.id,
        identity_provider_id=provider.id,
        subject=str(claims.get("sub")),
        email=email,
        email_verified=True,
        hosted_domain=str(claims.get("hd") or "") or None,
        last_login_at=now,
    )
    session.add(identity)
    state.consumed_at = now
    access_token = create_local_access_token(user=user, tenant_id=tenant.id, settings=settings)
    record_audit(
        session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
        action="auth.google.signup",
        entity_type="user",
        entity_id=user.id,
        after=public_state({"email": email, "company_id": company.id if company else None}),
    )
    session.commit()
    session.refresh(user)
    return _auth_session(session, user=user, access_token=access_token)


def _auth_session(session: Session, *, user: User, access_token: str) -> AuthSession:
    settings = get_settings()
    return AuthSession(
        tenant_id=user.tenant_id,
        user=UserRead.model_validate(user),
        access_token=access_token,
        expires_in=settings.sso_access_token_minutes * 60,
        company_access=_company_access(session, user=user),
    )


def _current_user(session: Session, *, authorization: str | None) -> User:
    token = bearer_token_from_authorization(authorization)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is required.")
    claims = decode_local_access_token(token, settings=get_settings())
    user_id = int(claims.get("sub") or 0)
    tenant_id = int(claims.get("tenant_id") or 0)
    user = session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session user is not active.")
    return user


def _company_access(session: Session, *, user: User) -> list[AuthCompanyAccess]:
    rows = session.execute(
        select(UserCompanyAccess, Company)
        .join(Company, Company.id == UserCompanyAccess.company_id)
        .where(
            UserCompanyAccess.tenant_id == user.tenant_id,
            UserCompanyAccess.user_id == user.id,
            UserCompanyAccess.status == "active",
        )
        .order_by(Company.name)
    ).all()
    return [
        AuthCompanyAccess(
            company_id=company.id,
            company_name=company.name,
            company_type=company.company_type,
            access_level=access.access_level,
            permissions=access.permissions,
        )
        for access, company in rows
    ]


def _ensure_email_not_registered(session: Session, *, email: str, tenant_id: int | None) -> None:
    statement = select(User).where(User.email == email)
    if tenant_id is not None:
        statement = statement.where(User.tenant_id == tenant_id)
    if session.scalar(statement) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")


def _ensure_role(session: Session, *, tenant_id: int, name: str) -> Role:
    role = session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == name))
    if role is not None:
        return role
    role = Role(
        tenant_id=tenant_id,
        name=name,
        permissions=ROLE_DEFINITIONS.get(name, ROLE_DEFINITIONS["tenant_admin"]),
    )
    session.add(role)
    session.flush()
    return role


def _ensure_default_commercial_profile(session: Session, *, tenant_id: int) -> None:
    exists = session.scalar(select(TenantCommercialProfile).where(TenantCommercialProfile.tenant_id == tenant_id))
    if exists is not None:
        return
    session.add(
        TenantCommercialProfile(
            tenant_id=tenant_id,
            billing_mode="direct",
            seats_purchased=5,
            status="trial",
        )
    )


def _create_company_from_signup(session: Session, *, tenant_id: int, payload: SignupRequest) -> Company | None:
    if not payload.company_name:
        return None
    company = Company(
        tenant_id=tenant_id,
        name=payload.company_name.strip(),
        tax_id=_blank_to_none(payload.company_tax_id),
        company_type="own",
        address=_blank_to_none(payload.company_address),
        status="active",
    )
    session.add(company)
    session.flush()
    return company


def _create_company_from_google_state(
    session: Session,
    *,
    tenant_id: int,
    state: OauthSignupState,
) -> Company | None:
    if not state.company_name:
        return None
    company = Company(
        tenant_id=tenant_id,
        name=state.company_name.strip(),
        tax_id=_blank_to_none(state.company_tax_id),
        company_type="own",
        address=_blank_to_none(state.company_address),
        status="active",
    )
    session.add(company)
    session.flush()
    return company


def _grant_company_admin_access(session: Session, *, tenant_id: int, user_id: int, company_id: int) -> None:
    access = session.scalar(
        select(UserCompanyAccess).where(
            UserCompanyAccess.tenant_id == tenant_id,
            UserCompanyAccess.user_id == user_id,
            UserCompanyAccess.company_id == company_id,
        )
    )
    if access is None:
        session.add(
            UserCompanyAccess(
                tenant_id=tenant_id,
                user_id=user_id,
                company_id=company_id,
                access_level="admin",
                role_name="tenant_admin",
                permissions=["company.all", "worker.read", "worker.write", "document.read", "document.write"],
                status="active",
            )
        )
    else:
        access.access_level = "admin"
        access.role_name = "tenant_admin"
        access.status = "active"


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
