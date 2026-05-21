from __future__ import annotations

from sqlalchemy import select

from app.db.models import DocumentType, ExternalPlatform, PlatformConnectionMethod, Reseller, Role, SaaSPlan, Tenant
from app.db.session import get_session_factory
from app.platforms.catalog import default_platform_catalog


COMMON_DOCUMENT_TYPES = [
    ("CAE.COMPANY.RC_POLICY", "Poliza de responsabilidad civil", "company", True, 365),
    ("CAE.COMPANY.RC_RECEIPT", "Recibo de responsabilidad civil", "company", True, 365),
    ("CAE.COMPANY.AEAT_CLEARANCE", "Certificado AEAT", "company", True, 180),
    ("CAE.COMPANY.SS_CLEARANCE", "Certificado Seguridad Social", "company", True, 180),
    ("CAE.COMPANY.RLC_TC1", "RLC/TC1", "company", True, 30),
    ("CAE.COMPANY.RNT_TC2", "RNT/TC2", "company", True, 30),
    ("CAE.COMPANY.ITA", "ITA", "company", True, 30),
    ("CAE.WORKER.ID_DOCUMENT", "Documento identificativo", "worker", False, None),
    ("CAE.WORKER.MEDICAL_FITNESS", "Aptitud laboral", "worker", True, 365),
    ("CAE.WORKER.PPE_DELIVERY", "Entrega de EPIs", "worker", True, 365),
    ("CAE.WORKER.BASIC_PRL_COURSE", "Curso basico PRL", "worker", False, None),
    ("CAE.WORKER.PRL_50H_COURSE", "Curso PRL 50 horas", "worker", False, None),
    ("CAE.WORKER.PRL_ART19", "Formacion PRL Art. 19", "worker", False, None),
    ("CAE.WORKER.METAL_TRAINING", "Formacion metal", "worker", False, None),
    ("CAE.WORKER.METAL_RECYCLING", "Reciclaje metal", "worker", False, None),
    ("CAE.WORKER.FORKLIFT_TRAINING", "Formacion carretilla elevadora", "worker", False, None),
    ("CAE.WORKER.MEWP_TRAINING", "Formacion plataforma elevadora", "worker", False, None),
    ("CAE.WORKER.OVERHEAD_CRANE_TRAINING", "Formacion puente grua", "worker", False, None),
    ("CAE.WORKER.HEIGHT_WORKS_TRAINING", "Formacion trabajos en altura", "worker", False, None),
    ("CAE.WORKER.RISK_INFORMATION", "Informacion de riesgos", "worker", True, 365),
]

DEFAULT_SAAS_PLANS = [
    (
        "starter",
        "SaaS Starter",
        1,
        10,
        5,
        ["multi_company", "manual_export", "demo_connector", "basic_dashboard"],
    ),
    (
        "professional",
        "SaaS Professional",
        1,
        50,
        25,
        ["multi_company", "manual_export", "demo_connector", "audit", "advanced_requirements"],
    ),
    (
        "reseller_gestoria",
        "Reseller Gestoria",
        None,
        None,
        None,
        ["multi_tenant_resale", "client_company_portal", "reseller_reporting", "white_label_ready"],
    ),
]

ROLE_DEFINITIONS = {
    "tenant_admin": [
        "tenant.admin",
        "company.all",
        "company.read",
        "company.write",
        "worker.read",
        "worker.write",
        "document.read",
        "document.write",
        "requirement.read",
        "requirement.write",
        "connector.read",
        "connector.write",
        "connector.execute",
        "connector.approve",
        "audit.read",
        "settings.write",
    ],
    "cae_operator": [
        "company.read",
        "worker.read",
        "worker.write",
        "document.read",
        "document.write",
        "requirement.read",
        "connector.read",
        "connector.execute",
    ],
    "external_company_viewer": [
        "company.read",
        "worker.read",
        "document.read",
    ],
}


def seed_platform_catalog() -> None:
    catalog = default_platform_catalog()
    session_factory = get_session_factory()
    with session_factory() as session:
        for item in catalog:
            platform = session.scalar(
                select(ExternalPlatform).where(ExternalPlatform.platform_key == item.platform_key)
            )
            if platform is None:
                platform = ExternalPlatform(
                    platform_key=item.platform_key,
                    name=item.name,
                    status=item.status,
                    is_commercial=item.is_commercial,
                    notes=item.notes,
                )
                session.add(platform)
                session.flush()
            else:
                platform.name = item.name
                platform.status = item.status
                platform.is_commercial = item.is_commercial
                platform.notes = item.notes

            allowed_method_keys = {method.method_key for method in item.methods}
            for method in item.methods:
                exists = session.scalar(
                    select(PlatformConnectionMethod).where(
                        PlatformConnectionMethod.external_platform_id == platform.id,
                        PlatformConnectionMethod.method_key == method.method_key,
                    )
                )
                if exists is None:
                    session.add(
                        PlatformConnectionMethod(
                            external_platform_id=platform.id,
                            method_key=method.method_key,
                            connector_type=method.connector_type,
                            connector_key=method.connector_key,
                            status=method.status,
                            implemented=method.implemented,
                            dry_run_supported=method.dry_run_supported,
                            manual_approval_required=method.manual_approval_required,
                            notes=method.notes,
                        )
                    )
                else:
                    exists.connector_type = method.connector_type
                    exists.connector_key = method.connector_key
                    exists.status = method.status
                    exists.implemented = method.implemented
                    exists.dry_run_supported = method.dry_run_supported
                    exists.manual_approval_required = method.manual_approval_required
                    exists.notes = method.notes
            stale_methods = session.scalars(
                select(PlatformConnectionMethod).where(
                    PlatformConnectionMethod.external_platform_id == platform.id,
                    PlatformConnectionMethod.method_key.notin_(allowed_method_keys),
                )
            )
            for stale_method in stale_methods:
                session.delete(stale_method)
        allowed_keys = {item.platform_key for item in catalog}
        stale_platforms = session.scalars(
            select(ExternalPlatform).where(ExternalPlatform.platform_key.notin_(allowed_keys))
        )
        for platform in stale_platforms:
            platform.status = "removed"
            platform.notes = "Retirada del catalogo activo hasta que exista una plataforma real autorizada."
        session.commit()


def seed_common_document_types() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        for code, name, entity_scope, requires_expiration, validity_days in COMMON_DOCUMENT_TYPES:
            exists = session.scalar(
                select(DocumentType).where(DocumentType.tenant_id.is_(None), DocumentType.code == code)
            )
            if exists is not None:
                continue
            session.add(
                DocumentType(
                    tenant_id=None,
                    code=code,
                    name=name,
                    entity_scope=entity_scope,
                    is_common_cae_type=True,
                    requires_expiration=requires_expiration,
                    default_validity_days=validity_days,
                    retention_days=3650,
                )
            )
        session.commit()


def seed_saas_catalog() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        for plan_key, name, max_tenants, max_companies, max_users, features in DEFAULT_SAAS_PLANS:
            plan = session.scalar(select(SaaSPlan).where(SaaSPlan.plan_key == plan_key))
            if plan is None:
                session.add(
                    SaaSPlan(
                        plan_key=plan_key,
                        name=name,
                        max_tenants=max_tenants,
                        max_companies=max_companies,
                        max_users=max_users,
                        features=features,
                        status="active",
                    )
                )
            else:
                plan.name = name
                plan.max_tenants = max_tenants
                plan.max_companies = max_companies
                plan.max_users = max_users
                plan.features = features
                plan.status = "active"

        reseller = session.scalar(select(Reseller).where(Reseller.tax_id == "GESTORIA-DEMO"))
        if reseller is None:
            session.add(
                Reseller(
                    name="Gestoria Demo",
                    tax_id="GESTORIA-DEMO",
                    contact_email="operaciones@gestoria-demo.invalid",
                    status="active",
                )
            )
        session.commit()


def seed_demo_tenant() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.tax_id.in_(["ARM-LOCAL", "DEMO-IPRL-CAE"])))
        if tenant is None:
            tenant = Tenant(name="ARM Operativa Local", tax_id="ARM-LOCAL", status="active")
            session.add(tenant)
            session.flush()
        else:
            tenant.name = "ARM Operativa Local"
            tenant.tax_id = "ARM-LOCAL"
            tenant.status = "active"
        for role_name, permissions in ROLE_DEFINITIONS.items():
            role = session.scalar(
                select(Role).where(Role.tenant_id == tenant.id, Role.name == role_name)
            )
            if role is None:
                session.add(Role(tenant_id=tenant.id, name=role_name, permissions=permissions))
            else:
                role.permissions = sorted(set(role.permissions).union(permissions))
        session.commit()


if __name__ == "__main__":
    seed_platform_catalog()
    seed_common_document_types()
    seed_saas_catalog()
    seed_demo_tenant()
    print("Seed completed: platforms, common document types, SaaS catalog and demo tenant.")
