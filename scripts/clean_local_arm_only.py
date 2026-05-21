# ruff: noqa: E402
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import delete, select, update

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")
os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")

from app.db.demo_seed import create_demo_database
from app.db.models import (
    AuditLog,
    Company,
    Document,
    DocumentIntake,
    DocumentType,
    DocumentRequirement,
    DocumentVersion,
    EmailVerificationToken,
    ExternalDocumentStatus,
    IdentityProvider,
    OauthSignupState,
    PlatformAccount,
    PlatformAccountUserAccess,
    PlatformDiscoveredLabel,
    PlatformEntityMapping,
    PlatformRequirementMapping,
    PlatformReviewRun,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformRpaMappingProposal,
    PlatformStructureSnapshot,
    Project,
    RequirementProfile,
    Reseller,
    Role,
    SaaSPlan,
    SsoAuthorizationState,
    Tenant,
    TenantCommercialProfile,
    TransferAttempt,
    TransferJob,
    User,
    UserCompanyAccess,
    UserIdentity,
    UserPermissionGrant,
    WorkCenter,
    Worker,
    WorkerPlatformRegistration,
    WorkerTraining,
    WorkerWorkAssignment,
)
from app.db.session import get_session_factory


ARM_TAX_ID = "B95868543"
LOCAL_USER = "demo@demo.invalid"


def main() -> None:
    create_demo_database()
    session_factory = get_session_factory()
    with session_factory() as session:
        arm_company = session.scalar(select(Company).where(Company.tax_id == ARM_TAX_ID))
        if arm_company is None:
            raise RuntimeError("ARM company was not found after local seed.")
        tenant_id = arm_company.tenant_id
        other_tenant_ids = set(session.scalars(select(Tenant.id).where(Tenant.id != tenant_id)))
        _delete_other_tenants(session, other_tenant_ids)
        arm_company_id = arm_company.id
        arm_worker_ids = set(
            session.scalars(
                select(Worker.id).where(
                    Worker.tenant_id == tenant_id,
                    Worker.company_id == arm_company_id,
                )
            )
        )

        non_arm_worker_ids = set(
            session.scalars(
                select(Worker.id).where(
                    Worker.tenant_id == tenant_id,
                    Worker.company_id != arm_company_id,
                )
            )
        )
        non_arm_company_ids = set(
            session.scalars(
                select(Company.id).where(
                    Company.tenant_id == tenant_id,
                    Company.id != arm_company_id,
                )
            )
        )
        non_local_user_ids = set(
            session.scalars(
                select(User.id).where(
                    User.tenant_id == tenant_id,
                    User.email != LOCAL_USER,
                )
            )
        )

        bad_document_ids = set(
            session.scalars(
                select(Document.id).where(
                    Document.tenant_id == tenant_id,
                    ~(
                        ((Document.entity_type == "company") & (Document.entity_id == arm_company_id))
                        | ((Document.entity_type == "worker") & (Document.entity_id.in_(arm_worker_ids or [-1])))
                    ),
                )
            )
        )
        bad_version_ids = set(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(bad_document_ids or [-1])))
        )

        _delete(session, EmailVerificationToken, EmailVerificationToken.tenant_id == tenant_id)
        _delete(session, OauthSignupState, OauthSignupState.id.is_not(None))
        _delete(session, SsoAuthorizationState, SsoAuthorizationState.tenant_id == tenant_id)
        _delete(session, UserIdentity, UserIdentity.tenant_id == tenant_id)

        _delete(session, PlatformReviewRun, PlatformReviewRun.tenant_id == tenant_id)
        session.execute(
            update(PlatformReviewSchedule)
            .where(PlatformReviewSchedule.tenant_id == tenant_id)
            .values(last_run_at=None, last_result_status=None, last_result_summary=None)
        )

        _delete(session, ExternalDocumentStatus, ExternalDocumentStatus.id.is_not(None))
        _delete(session, TransferAttempt, TransferAttempt.id.is_not(None))
        _delete(session, TransferJob, TransferJob.tenant_id == tenant_id)
        _delete(session, AuditLog, AuditLog.tenant_id == tenant_id)

        _delete(session, WorkerTraining, WorkerTraining.worker_id.in_(non_arm_worker_ids or [-1]))
        _delete(session, WorkerWorkAssignment, WorkerWorkAssignment.worker_id.in_(non_arm_worker_ids or [-1]))
        _delete(session, WorkerPlatformRegistration, WorkerPlatformRegistration.worker_id.in_(non_arm_worker_ids or [-1]))

        arm_intake_ids = set(
            session.scalars(
                select(DocumentIntake.id).where(
                    DocumentIntake.tenant_id == tenant_id,
                    (DocumentIntake.requested_company_id == arm_company_id)
                    | (DocumentIntake.predicted_company_id == arm_company_id)
                    | (DocumentIntake.target_notes.is_not(None) & DocumentIntake.target_notes.ilike("%ARM%")),
                )
            )
        )
        _delete(session, DocumentIntake, DocumentIntake.tenant_id == tenant_id, DocumentIntake.id.not_in(arm_intake_ids or [-1]))
        session.execute(
            update(DocumentIntake)
            .where(DocumentIntake.tenant_id == tenant_id, DocumentIntake.requested_worker_id.in_(non_arm_worker_ids or [-1]))
            .values(requested_worker_id=None)
        )
        session.execute(
            update(DocumentIntake)
            .where(DocumentIntake.tenant_id == tenant_id, DocumentIntake.predicted_worker_id.in_(non_arm_worker_ids or [-1]))
            .values(predicted_worker_id=None)
        )

        _delete(session, DocumentVersion, DocumentVersion.id.in_(bad_version_ids or [-1]))
        _delete(session, Document, Document.id.in_(bad_document_ids or [-1]))

        _delete(session, DocumentRequirement, DocumentRequirement.id.is_not(None))
        _delete(session, RequirementProfile, RequirementProfile.tenant_id == tenant_id)
        _delete(session, Project, Project.tenant_id == tenant_id)
        _delete(session, WorkCenter, WorkCenter.tenant_id == tenant_id)

        session.execute(
            update(PlatformStructureSnapshot)
            .where(
                PlatformStructureSnapshot.tenant_id == tenant_id,
                PlatformStructureSnapshot.company_id.in_(non_arm_company_ids or [-1]),
            )
            .values(company_id=None)
        )
        session.execute(
            update(PlatformDiscoveredLabel)
            .where(
                PlatformDiscoveredLabel.tenant_id == tenant_id,
                PlatformDiscoveredLabel.company_id.in_(non_arm_company_ids or [-1]),
            )
            .values(company_id=None)
        )

        _delete(session, PlatformAccountUserAccess, PlatformAccountUserAccess.tenant_id == tenant_id)
        _delete(session, PlatformAccount, PlatformAccount.tenant_id == tenant_id)

        _delete(session, UserCompanyAccess, UserCompanyAccess.tenant_id == tenant_id, UserCompanyAccess.company_id.in_(non_arm_company_ids or [-1]))
        _delete(session, UserCompanyAccess, UserCompanyAccess.tenant_id == tenant_id, UserCompanyAccess.user_id.in_(non_local_user_ids or [-1]))
        _delete(session, UserPermissionGrant, UserPermissionGrant.tenant_id == tenant_id, UserPermissionGrant.user_id.in_(non_local_user_ids or [-1]))
        _delete(session, User, User.id.in_(non_local_user_ids or [-1]))

        _delete(session, Worker, Worker.id.in_(non_arm_worker_ids or [-1]))
        _delete(session, Company, Company.id.in_(non_arm_company_ids or [-1]))
        _delete(session, TenantCommercialProfile, TenantCommercialProfile.tenant_id == tenant_id)
        _delete(session, Reseller, Reseller.id.is_not(None))
        _delete(session, SaaSPlan, SaaSPlan.id.is_not(None))

        local_user = session.scalar(select(User).where(User.email == LOCAL_USER, User.tenant_id == tenant_id))
        if local_user is not None:
            local_user.name = "ARM Operativa"
        arm_company.name = "Empresa Demo Industrial, S.L."
        arm_company.status = "active"
        session.commit()

        print(
            {
                "tenant_id": tenant_id,
                "arm_company_id": arm_company_id,
                "arm_workers_kept": len(arm_worker_ids),
                "non_arm_workers_deleted": len(non_arm_worker_ids),
                "non_arm_companies_deleted": len(non_arm_company_ids),
                "non_local_users_deleted": len(non_local_user_ids),
            }
        )


def _delete_other_tenants(session, tenant_ids: set[int]) -> None:
    if not tenant_ids:
        return

    document_ids = set(session.scalars(select(Document.id).where(Document.tenant_id.in_(tenant_ids))))
    document_version_ids = set(
        session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(document_ids or [-1])))
    )
    transfer_ids = set(session.scalars(select(TransferJob.id).where(TransferJob.tenant_id.in_(tenant_ids))))
    profile_ids = set(session.scalars(select(RequirementProfile.id).where(RequirementProfile.tenant_id.in_(tenant_ids))))

    _delete(session, EmailVerificationToken, EmailVerificationToken.tenant_id.in_(tenant_ids))
    _delete(session, SsoAuthorizationState, SsoAuthorizationState.tenant_id.in_(tenant_ids))
    _delete(session, UserIdentity, UserIdentity.tenant_id.in_(tenant_ids))
    _delete(session, IdentityProvider, IdentityProvider.tenant_id.in_(tenant_ids))

    _delete(session, PlatformReviewRun, PlatformReviewRun.tenant_id.in_(tenant_ids))
    _delete(session, PlatformReviewSchedule, PlatformReviewSchedule.tenant_id.in_(tenant_ids))
    _delete(session, PlatformRpaMappingProposal, PlatformRpaMappingProposal.tenant_id.in_(tenant_ids))
    _delete(session, PlatformRpaAccountProposal, PlatformRpaAccountProposal.tenant_id.in_(tenant_ids))
    _delete(session, PlatformRpaManifest, PlatformRpaManifest.tenant_id.in_(tenant_ids))
    _delete(session, PlatformDiscoveredLabel, PlatformDiscoveredLabel.tenant_id.in_(tenant_ids))
    _delete(session, PlatformStructureSnapshot, PlatformStructureSnapshot.tenant_id.in_(tenant_ids))
    _delete(session, PlatformRequirementMapping, PlatformRequirementMapping.tenant_id.in_(tenant_ids))
    _delete(session, PlatformEntityMapping, PlatformEntityMapping.tenant_id.in_(tenant_ids))
    _delete(session, PlatformAccountUserAccess, PlatformAccountUserAccess.tenant_id.in_(tenant_ids))
    _delete(session, PlatformAccount, PlatformAccount.tenant_id.in_(tenant_ids))

    _delete(session, TransferAttempt, TransferAttempt.transfer_job_id.in_(transfer_ids or [-1]))
    _delete(session, TransferJob, TransferJob.tenant_id.in_(tenant_ids))
    _delete(session, ExternalDocumentStatus, ExternalDocumentStatus.document_version_id.in_(document_version_ids or [-1]))
    _delete(session, DocumentIntake, DocumentIntake.tenant_id.in_(tenant_ids))
    _delete(session, DocumentVersion, DocumentVersion.document_id.in_(document_ids or [-1]))
    _delete(session, Document, Document.tenant_id.in_(tenant_ids))
    _delete(session, DocumentRequirement, DocumentRequirement.profile_id.in_(profile_ids or [-1]))
    _delete(session, RequirementProfile, RequirementProfile.tenant_id.in_(tenant_ids))

    _delete(session, WorkerTraining, WorkerTraining.tenant_id.in_(tenant_ids))
    _delete(session, WorkerWorkAssignment, WorkerWorkAssignment.tenant_id.in_(tenant_ids))
    _delete(session, WorkerPlatformRegistration, WorkerPlatformRegistration.tenant_id.in_(tenant_ids))
    _delete(session, Worker, Worker.tenant_id.in_(tenant_ids))
    _delete(session, Project, Project.tenant_id.in_(tenant_ids))
    _delete(session, WorkCenter, WorkCenter.tenant_id.in_(tenant_ids))
    _delete(session, UserCompanyAccess, UserCompanyAccess.tenant_id.in_(tenant_ids))
    _delete(session, UserPermissionGrant, UserPermissionGrant.tenant_id.in_(tenant_ids))
    _delete(session, User, User.tenant_id.in_(tenant_ids))
    _delete(session, Role, Role.tenant_id.in_(tenant_ids))
    _delete(session, DocumentType, DocumentType.tenant_id.in_(tenant_ids))
    _delete(session, TenantCommercialProfile, TenantCommercialProfile.tenant_id.in_(tenant_ids))
    _delete(session, AuditLog, AuditLog.tenant_id.in_(tenant_ids))
    _delete(session, Company, Company.tenant_id.in_(tenant_ids))
    _delete(session, Tenant, Tenant.id.in_(tenant_ids))


def _delete(session, model, *conditions) -> None:
    statement = delete(model)
    for condition in conditions:
        statement = statement.where(condition)
    session.execute(statement)


if __name__ == "__main__":
    main()
