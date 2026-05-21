from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    Company,
    Document,
    DocumentType,
    DocumentVersion,
    ExternalPlatform,
    PlatformAccount,
    PlatformAccountUserAccess,
    Reseller,
    Role,
    SaaSPlan,
    TenantCommercialProfile,
    User,
    UserCompanyAccess,
    UserPermissionGrant,
    Worker,
    WorkerPlatformRegistration,
    WorkerTraining,
    WorkerWorkAssignment,
)
from app.db.seed import seed_common_document_types, seed_demo_tenant, seed_platform_catalog
from app.db.session import get_engine, get_session_factory
from app.services.auth import hash_password
from app.services.platform_contracts import (
    ARM_PENDING_REVIEW_SLUGS,
    DEFAULT_CONTRACT_BUNDLE,
    FIRST_PRIORITY_ARM_SLUGS,
    import_platform_contracts,
)
from app.services.sso import configure_google_provider
from app.services.worker_identity import normalize_worker_identifier, worker_identifier_hash


def create_demo_database() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_sqlite_demo_schema_upgrades(engine)
    seed_platform_catalog()
    seed_common_document_types()
    seed_demo_tenant()
    _seed_operational_sample()


def _ensure_sqlite_demo_schema_upgrades(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "workers" not in existing_tables:
        return
    user_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in existing_tables else set()
    user_additions = {
        "password_hash": "VARCHAR(512)",
        "email_verified_at": "DATETIME",
        "last_login_at": "DATETIME",
    }
    worker_columns = {column["name"] for column in inspector.get_columns("workers")}
    worker_additions = {
        "identifier_value": "VARCHAR(80)",
        "identifier_expires_at": "DATE",
        "email": "VARCHAR(240)",
        "phone": "VARCHAR(60)",
        "social_security_number": "VARCHAR(40)",
        "social_security_last4": "VARCHAR(4)",
        "contract_type": "VARCHAR(80)",
        "starts_at": "DATE",
        "ends_at": "DATE",
        "work_center_name": "VARCHAR(180)",
        "risk_profile": "VARCHAR(80)",
        "medical_fitness_issued_at": "DATE",
        "medical_fitness_provider": "VARCHAR(180)",
        "medical_fitness_restrictions": "TEXT",
        "cae_notes": "TEXT",
    }
    intake_columns = (
        {column["name"] for column in inspector.get_columns("document_intakes")}
        if "document_intakes" in existing_tables
        else set()
    )
    intake_additions = {
        "intake_scope": "VARCHAR(40) NOT NULL DEFAULT 'auto'",
        "requested_company_id": "INTEGER",
        "requested_worker_id": "INTEGER",
        "target_notes": "TEXT",
    }
    version_columns = (
        {column["name"] for column in inspector.get_columns("document_versions")}
        if "document_versions" in existing_tables
        else set()
    )
    version_additions = {
        "platform_expires_at": "DATE",
        "expiry_review_status": "VARCHAR(40) NOT NULL DEFAULT 'ok'",
        "platform_expiry_source": "VARCHAR(160)",
    }
    with engine.begin() as connection:
        for column_name, column_type in user_additions.items():
            if column_name not in user_columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"))
        for column_name, column_type in worker_additions.items():
            if column_name not in worker_columns:
                connection.execute(text(f"ALTER TABLE workers ADD COLUMN {column_name} {column_type}"))
        for column_name, column_type in intake_additions.items():
            if column_name not in intake_columns:
                connection.execute(text(f"ALTER TABLE document_intakes ADD COLUMN {column_name} {column_type}"))
        for column_name, column_type in version_additions.items():
            if column_name not in version_columns:
                connection.execute(text(f"ALTER TABLE document_versions ADD COLUMN {column_name} {column_type}"))


def _seed_operational_sample() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        tenant_id = 1
        admin_role = _role(session, tenant_id, "tenant_admin")
        arm_company = _ensure_company(
            session,
            tenant_id=tenant_id,
            name="Empresa Demo Industrial, S.L.",
            tax_id="B95868543",
            company_type="own",
        )
        quick_demo_user = _ensure_user(
            session,
            tenant_id=tenant_id,
            email="demo@demo.invalid",
            name="ARM Operativa",
            role_id=admin_role.id,
            password="demo",
            force_password=True,
        )
        _ensure_user_company_access(
            session,
            tenant_id=tenant_id,
            user_id=quick_demo_user.id,
            company_id=arm_company.id,
            access_level="admin",
            role_name="ARM",
            permissions=["company.all", "worker.read", "worker.write", "document.read", "document.write"],
        )
        _ensure_user_permission_grant(
            session,
            tenant_id=tenant_id,
            user_id=quick_demo_user.id,
            scope_type="system",
            scope_id=None,
            permission="system.admin",
            effect="allow",
            reason="Cuenta local demo/demo para operar solo con datos ARM.",
        )
        import_platform_contracts(
            session,
            tenant_id=tenant_id,
            actor_user_id=quick_demo_user.id,
            source_root=DEFAULT_CONTRACT_BUNDLE,
            company_source_label="ARM",
            platform_slugs=FIRST_PRIORITY_ARM_SLUGS,
            priority_group="arm_first_priority",
        )
        import_platform_contracts(
            session,
            tenant_id=tenant_id,
            actor_user_id=quick_demo_user.id,
            source_root=DEFAULT_CONTRACT_BUNDLE,
            company_source_label="ARM",
            platform_slugs=ARM_PENDING_REVIEW_SLUGS,
            priority_group="arm_pending_review",
        )
        configure_google_provider(
            session,
            tenant_id=tenant_id,
            client_id=None,
            encrypted_client_secret_ref="env:IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET",
            allowed_domains=[],
            auto_provision=False,
            status_value="disabled",
        )
        existing_arm_workers = list(
            session.scalars(
                select(Worker).where(
                    Worker.tenant_id == tenant_id,
                    Worker.company_id == arm_company.id,
                )
            )
        )
        workers_by_name: dict[str, Worker] = {
            f"{worker.first_name} {worker.last_name}": worker for worker in existing_arm_workers
        }
        if not existing_arm_workers:
            for first_name, last_name in [
                ("Alicia", "Gomez"),
                ("Bruno", "Lopez"),
                ("Carlos", "Perez Ruiz"),
                ("Daniel", "Pendiente revisar"),
                ("Eduardo", "Pendiente revisar"),
                ("Fernando", "Pendiente revisar"),
                ("Hugo", "Pendiente revisar"),
            ]:
                worker = _ensure_arm_worker(
                    session,
                    tenant_id=tenant_id,
                    company_id=arm_company.id,
                    first_name=first_name,
                    last_name=last_name,
                )
                workers_by_name[f"{first_name} {last_name}"] = worker

        _seed_arm_ctaima_pending_observation(session, tenant_id=tenant_id, workers_by_name=workers_by_name)

        session.commit()


def _ensure_company(
    session: Session,
    *,
    tenant_id: int,
    name: str,
    tax_id: str,
    company_type: str,
) -> Company:
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.tax_id == tax_id)
    )
    if company is not None:
        return company
    company = Company(
        tenant_id=tenant_id,
        name=name,
        tax_id=tax_id,
        company_type=company_type,
        status="active",
    )
    session.add(company)
    session.flush()
    return company


def _ensure_worker(
    session: Session,
    *,
    tenant_id: int,
    company_id: int,
    first_name: str,
    last_name: str,
    identifier_value: str,
    identifier_last4: str,
    identifier_expires_at: date | None,
    social_security_number: str | None,
    social_security_last4: str | None,
    contract_type: str | None,
    starts_at: date | None,
    work_position: str,
    work_center_name: str | None,
    risk_profile: str | None,
    medical_fitness_status: str,
    medical_fitness_issued_at: date | None,
    medical_fitness_expires_at: date | None,
    medical_fitness_provider: str | None,
    medical_fitness_restrictions: str | None,
) -> Worker:
    worker = session.scalar(
        select(Worker).where(
            Worker.tenant_id == tenant_id,
            Worker.company_id == company_id,
            Worker.identifier_hash == worker_identifier_hash(identifier_value),
        )
    )
    if worker is None:
        worker = session.scalar(
            select(Worker).where(
                Worker.tenant_id == tenant_id,
                Worker.company_id == company_id,
                Worker.identifier_last4 == identifier_last4,
            )
        )
    if worker is not None:
        normalized_identifier = normalize_worker_identifier(identifier_value)
        worker.identifier_value = normalized_identifier
        worker.identifier_hash = worker_identifier_hash(normalized_identifier)
        worker.identifier_last4 = identifier_last4
        worker.identifier_expires_at = identifier_expires_at
        worker.social_security_number = social_security_number
        worker.social_security_last4 = social_security_last4
        worker.contract_type = contract_type
        worker.starts_at = starts_at
        worker.work_position = work_position
        worker.work_center_name = work_center_name
        worker.risk_profile = risk_profile
        worker.medical_fitness_status = medical_fitness_status
        worker.medical_fitness_issued_at = medical_fitness_issued_at
        worker.medical_fitness_expires_at = medical_fitness_expires_at
        worker.medical_fitness_provider = medical_fitness_provider
        worker.medical_fitness_restrictions = medical_fitness_restrictions
        return worker
    normalized_identifier = normalize_worker_identifier(identifier_value)
    worker = Worker(
        tenant_id=tenant_id,
        company_id=company_id,
        first_name=first_name,
        last_name=last_name,
        identifier_type="dni",
        identifier_hash=worker_identifier_hash(normalized_identifier),
        identifier_value=normalized_identifier,
        identifier_last4=identifier_last4,
        identifier_expires_at=identifier_expires_at,
        social_security_number=social_security_number,
        social_security_last4=social_security_last4,
        contract_type=contract_type,
        starts_at=starts_at,
        work_position=work_position,
        work_center_name=work_center_name,
        risk_profile=risk_profile,
        employment_status="active",
        medical_fitness_status=medical_fitness_status,
        medical_fitness_issued_at=medical_fitness_issued_at,
        medical_fitness_expires_at=medical_fitness_expires_at,
        medical_fitness_provider=medical_fitness_provider,
        medical_fitness_restrictions=medical_fitness_restrictions,
        status="active",
    )
    session.add(worker)
    session.flush()
    return worker

def _ensure_arm_worker(
    session: Session,
    *,
    tenant_id: int,
    company_id: int,
    first_name: str,
    last_name: str,
) -> Worker:
    worker = session.scalar(
        select(Worker).where(
            Worker.tenant_id == tenant_id,
            Worker.company_id == company_id,
            Worker.first_name == first_name,
            Worker.last_name == last_name,
        )
    )
    if worker is not None:
        worker.status = "active"
        worker.employment_status = "active"
        worker.cae_notes = "Ficha ARM creada desde intake documental; revisar antes de aprobar documentos."
        return worker
    worker = Worker(
        tenant_id=tenant_id,
        company_id=company_id,
        first_name=first_name,
        last_name=last_name,
        identifier_type=None,
        identifier_hash=None,
        identifier_value=None,
        identifier_last4=None,
        work_position=None,
        employment_status="active",
        medical_fitness_status="pendiente",
        cae_notes="Ficha ARM creada desde intake documental; revisar antes de aprobar documentos.",
        status="active",
    )
    session.add(worker)
    session.flush()
    return worker


def _ensure_worker_training(
    session: Session,
    *,
    tenant_id: int,
    worker_id: int,
    course_code: str,
    course_name: str,
    provider: str | None,
    hours: int | None,
    issued_at: date | None,
    expires_at: date | None,
    status: str,
) -> WorkerTraining:
    training = session.scalar(
        select(WorkerTraining).where(
            WorkerTraining.tenant_id == tenant_id,
            WorkerTraining.worker_id == worker_id,
            WorkerTraining.course_code == course_code,
        )
    )
    if training is not None:
        training.course_name = course_name
        training.provider = provider
        training.hours = hours
        training.issued_at = issued_at
        training.expires_at = expires_at
        training.status = status
        return training
    training = WorkerTraining(
        tenant_id=tenant_id,
        worker_id=worker_id,
        course_code=course_code,
        course_name=course_name,
        provider=provider,
        hours=hours,
        issued_at=issued_at,
        expires_at=expires_at,
        status=status,
    )
    session.add(training)
    session.flush()
    return training


def _ensure_worker_work_assignment(
    session: Session,
    *,
    tenant_id: int,
    worker_id: int,
    work_name: str,
    client_company_name: str | None,
    role: str | None,
    starts_at: date | None,
    ends_at: date | None,
    status: str,
    source: str,
) -> WorkerWorkAssignment:
    assignment = session.scalar(
        select(WorkerWorkAssignment).where(
            WorkerWorkAssignment.tenant_id == tenant_id,
            WorkerWorkAssignment.worker_id == worker_id,
            WorkerWorkAssignment.work_name == work_name,
        )
    )
    if assignment is not None:
        assignment.client_company_name = client_company_name
        assignment.role = role
        assignment.starts_at = starts_at
        assignment.ends_at = ends_at
        assignment.status = status
        assignment.source = source
        return assignment
    assignment = WorkerWorkAssignment(
        tenant_id=tenant_id,
        worker_id=worker_id,
        work_name=work_name,
        client_company_name=client_company_name,
        role=role,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        source=source,
    )
    session.add(assignment)
    session.flush()
    return assignment


def _ensure_worker_platform_registration(
    session: Session,
    *,
    tenant_id: int,
    worker_id: int,
    platform_account_id: int | None,
    external_platform_id: int,
    platform_name: str,
    external_worker_id: str | None,
    registration_status: str,
    assignment_scope: str | None,
    source: str,
    notes: str | None = None,
) -> WorkerPlatformRegistration:
    statement = select(WorkerPlatformRegistration).where(
        WorkerPlatformRegistration.tenant_id == tenant_id,
        WorkerPlatformRegistration.worker_id == worker_id,
        WorkerPlatformRegistration.platform_name == platform_name,
    )
    if platform_account_id is None:
        statement = statement.where(WorkerPlatformRegistration.platform_account_id.is_(None))
    else:
        statement = statement.where(WorkerPlatformRegistration.platform_account_id == platform_account_id)
    registration = session.scalar(statement)
    if registration is not None:
        registration.platform_account_id = platform_account_id
        registration.external_platform_id = external_platform_id
        registration.platform_name = platform_name
        registration.external_worker_id = external_worker_id
        registration.registration_status = registration_status
        registration.assignment_scope = assignment_scope
        registration.source = source
        registration.notes = notes
        return registration
    registration = WorkerPlatformRegistration(
        tenant_id=tenant_id,
        worker_id=worker_id,
        platform_account_id=platform_account_id,
        external_platform_id=external_platform_id,
        platform_name=platform_name,
        external_worker_id=external_worker_id,
        registration_status=registration_status,
        assignment_scope=assignment_scope,
        source=source,
        notes=notes,
    )
    session.add(registration)
    session.flush()
    return registration


def _seed_arm_ctaima_pending_observation(
    session: Session,
    *,
    tenant_id: int,
    workers_by_name: dict[str, Worker],
) -> None:
    worker = workers_by_name.get("Alicia Gomez")
    if worker is None:
        return
    platform = session.scalar(select(ExternalPlatform).where(ExternalPlatform.platform_key == "ctaima_cae"))
    if platform is None:
        return
    cliente_a_account = session.scalar(
        select(PlatformAccount)
        .where(
            PlatformAccount.tenant_id == tenant_id,
            PlatformAccount.external_platform_id == platform.id,
            PlatformAccount.display_name.ilike("%CLIENTE_A%"),
        )
        .order_by(PlatformAccount.id)
    )
    _ensure_worker_platform_registration(
        session,
        tenant_id=tenant_id,
        worker_id=worker.id,
        platform_account_id=cliente_a_account.id if cliente_a_account is not None else None,
        external_platform_id=platform.id,
        platform_name="CTAIMA / CTAIMA CAE",
        external_worker_id=None,
        registration_status="missing_required_document",
        assignment_scope="CLIENTE_A",
        source="manual_external_observation",
        notes=(
            "CLIENTE_A: falta Entrega de EPIs en CTAIMA para Alicia Gomez. "
            "Observacion manual ARM; la lectura automatica queda bloqueada por captcha/control."
        ),
    )


def _role(session: Session, tenant_id: int, name: str) -> Role:
    role = session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == name))
    if role is None:
        raise RuntimeError(f"Missing demo role {name}")
    return role


def _ensure_user(
    session: Session,
    *,
    tenant_id: int,
    email: str,
    name: str,
    role_id: int,
    password: str = "DemoPassword123!",
    force_password: bool = False,
) -> User:
    user = session.scalar(select(User).where(User.tenant_id == tenant_id, User.email == email))
    if user is not None:
        user.name = name
        user.role_id = role_id
        user.status = "active"
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        if force_password or not user.password_hash:
            user.password_hash = _hash_local_demo_password(password)
        return user
    user = User(
        tenant_id=tenant_id,
        email=email,
        name=name,
        password_hash=_hash_local_demo_password(password),
        role_id=role_id,
        mfa_enabled=False,
        status="active",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    return user


def _hash_local_demo_password(password: str) -> str:
    if len(password) >= 10:
        return hash_password(password)
    salt = secrets.token_bytes(16)
    iterations = 210_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        ]
    )


def _ensure_user_company_access(
    session: Session,
    *,
    tenant_id: int,
    user_id: int,
    company_id: int,
    access_level: str,
    role_name: str,
    permissions: list[str],
) -> UserCompanyAccess:
    access = session.scalar(
        select(UserCompanyAccess).where(
            UserCompanyAccess.tenant_id == tenant_id,
            UserCompanyAccess.user_id == user_id,
            UserCompanyAccess.company_id == company_id,
        )
    )
    if access is not None:
        access.access_level = access_level
        access.role_name = role_name
        access.permissions = permissions
        access.status = "active"
        return access
    access = UserCompanyAccess(
        tenant_id=tenant_id,
        user_id=user_id,
        company_id=company_id,
        access_level=access_level,
        role_name=role_name,
        permissions=permissions,
        status="active",
    )
    session.add(access)
    session.flush()
    return access


def _ensure_platform_account(
    session: Session,
    *,
    tenant_id: int,
    platform_key: str,
    display_name: str,
    auth_type: str,
    mode: str,
) -> PlatformAccount:
    platform = session.scalar(select(ExternalPlatform).where(ExternalPlatform.platform_key == platform_key))
    if platform is None:
        raise RuntimeError(f"Missing platform {platform_key}")
    account = session.scalar(
        select(PlatformAccount).where(
            PlatformAccount.tenant_id == tenant_id,
            PlatformAccount.external_platform_id == platform.id,
            PlatformAccount.display_name == display_name,
        )
    )
    if account is not None:
        account.auth_type = auth_type
        account.mode = mode
        account.dry_run = True
        account.manual_approval_required = True
        account.status = "active"
        return account
    account = PlatformAccount(
        tenant_id=tenant_id,
        external_platform_id=platform.id,
        display_name=display_name,
        auth_type=auth_type,
        encrypted_secret_ref=None,
        mode=mode,
        dry_run=True,
        manual_approval_required=True,
        status="active",
    )
    session.add(account)
    session.flush()
    return account


def _ensure_user_permission_grant(
    session: Session,
    *,
    tenant_id: int,
    user_id: int,
    scope_type: str,
    scope_id: int | None,
    permission: str,
    effect: str,
    reason: str,
) -> UserPermissionGrant:
    grant = session.scalar(
        select(UserPermissionGrant).where(
            UserPermissionGrant.tenant_id == tenant_id,
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.scope_type == scope_type,
            UserPermissionGrant.scope_id == scope_id,
            UserPermissionGrant.permission == permission,
            UserPermissionGrant.effect == effect,
        )
    )
    if grant is not None:
        grant.reason = reason
        grant.status = "active"
        return grant
    grant = UserPermissionGrant(
        tenant_id=tenant_id,
        user_id=user_id,
        scope_type=scope_type,
        scope_id=scope_id,
        permission=permission,
        effect=effect,
        reason=reason,
        status="active",
    )
    session.add(grant)
    session.flush()
    return grant


def _ensure_platform_user_access(
    session: Session,
    *,
    tenant_id: int,
    platform_account_id: int,
    user_id: int,
    access_level: str,
    permissions: list[str],
    allowed_operations: list[str],
) -> PlatformAccountUserAccess:
    access = session.scalar(
        select(PlatformAccountUserAccess).where(
            PlatformAccountUserAccess.tenant_id == tenant_id,
            PlatformAccountUserAccess.platform_account_id == platform_account_id,
            PlatformAccountUserAccess.user_id == user_id,
        )
    )
    if access is not None:
        access.access_level = access_level
        access.permissions = permissions
        access.allowed_operations = allowed_operations
        access.status = "active"
        return access
    access = PlatformAccountUserAccess(
        tenant_id=tenant_id,
        platform_account_id=platform_account_id,
        user_id=user_id,
        access_level=access_level,
        permissions=permissions,
        allowed_operations=allowed_operations,
        status="active",
    )
    session.add(access)
    session.flush()
    return access


def _ensure_tenant_commercial_profile(session: Session, *, tenant_id: int) -> TenantCommercialProfile:
    plan = session.scalar(select(SaaSPlan).where(SaaSPlan.plan_key == "reseller_gestoria"))
    reseller = session.scalar(select(Reseller).where(Reseller.tax_id == "GESTORIA-DEMO"))
    profile = session.scalar(
        select(TenantCommercialProfile).where(TenantCommercialProfile.tenant_id == tenant_id)
    )
    if profile is not None:
        profile.plan_id = plan.id if plan else None
        profile.reseller_id = reseller.id if reseller else None
        profile.billing_mode = "reseller_managed"
        profile.seats_purchased = 25
        profile.status = "active"
        return profile
    profile = TenantCommercialProfile(
        tenant_id=tenant_id,
        plan_id=plan.id if plan else None,
        reseller_id=reseller.id if reseller else None,
        billing_mode="reseller_managed",
        seats_purchased=25,
        status="active",
    )
    session.add(profile)
    session.flush()
    return profile


def _document_type(session: Session, code: str) -> DocumentType:
    document_type = session.scalar(
        select(DocumentType).where(DocumentType.tenant_id.is_(None), DocumentType.code == code)
    )
    if document_type is None:
        raise RuntimeError(f"Missing common document type {code}")
    return document_type


def _ensure_document_with_version(
    session: Session,
    *,
    tenant_id: int,
    document_type_id: int,
    entity_type: str,
    entity_id: int,
    filename: str,
    sha256: str,
    expires_at: date | None,
) -> None:
    storage_key, actual_sha256, size_bytes = _ensure_demo_storage_file(filename, sha256)
    document = session.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.document_type_id == document_type_id,
            Document.entity_type == entity_type,
            Document.entity_id == entity_id,
        )
    )
    if document is not None:
        version = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.file_storage_key == storage_key,
            )
        )
        if version is not None:
            version.filename = filename
            version.sha256 = actual_sha256
            version.expires_at = expires_at
            version.file_storage_key = storage_key
            version.size_bytes = size_bytes
        return
    document = Document(
        tenant_id=tenant_id,
        document_type_id=document_type_id,
        entity_type=entity_type,
        entity_id=entity_id,
        status_internal="valid_internal",
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        file_storage_key=storage_key,
        sha256=actual_sha256,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=size_bytes,
        issued_at=date.today() - timedelta(days=30),
        expires_at=expires_at,
        source="demo",
    )
    session.add(version)
    session.flush()
    document.current_version_id = version.id


def _ensure_demo_storage_file(filename: str, sha256: str) -> tuple[str, str, int]:
    safe_filename = "".join(char if char.isalnum() or char in "._-" else "_" for char in filename).strip("._")
    safe_filename = safe_filename or "documento-demo.pdf"
    relative = Path("demo") / safe_filename
    root = Path(get_settings().document_storage_path).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise RuntimeError("Demo document path escapes storage root")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            f"Documento demo CAE\nFichero: {safe_filename}\nSHA esperado: {sha256}\n",
            encoding="utf-8",
        )
    content = path.read_bytes()
    return f"local://{relative.as_posix()}", hashlib.sha256(content).hexdigest(), len(content)


if __name__ == "__main__":
    create_demo_database()
    print("Demo database ready.")
