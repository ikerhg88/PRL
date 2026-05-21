from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ExternalPlatform,
    PlatformAccount,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformRpaMappingProposal,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTRACT_BUNDLE = PROJECT_ROOT / "requisitos" / "iker_contratos_plataformas_max_scope_2026-05-18"
FIRST_PRIORITY_ARM_SLUGS: tuple[str, ...] = (
    "e_coordina",
    "seisconecta",
    "validate",
    "timenet",
    "nomio",
    "vitaly_cae",
)
ARM_PENDING_REVIEW_SLUGS: tuple[str, ...] = (
    "ctaima",
)
SECOND_PRIORITY_ARM_SLUGS: tuple[str, ...] = (
    "dokyfy",
    "egestiona",
    "folyo",
    "iedoce",
    "integra_asem",
    "koordinatu",
    "metacontratas",
    "quioo",
    "sgs_gestiona",
    "smartosh",
    "ucae",
)
BLOCKED_ARM_SLUGS: tuple[str, ...] = (
    "quironprevencion",
    "sarenet",
)
ALL_ACTIVE_ARM_SLUGS: tuple[str, ...] = (
    *FIRST_PRIORITY_ARM_SLUGS,
    *ARM_PENDING_REVIEW_SLUGS,
    *SECOND_PRIORITY_ARM_SLUGS,
    *BLOCKED_ARM_SLUGS,
)
CONTRACT_SLUG_TO_PLATFORM_KEY = {
    "ctaima": "ctaima_cae",
    "dokyfy": "dokify",
    "e_coordina": "ecoordina",
    "egestiona": "egestiona",
    "folyo": "folyo",
    "iedoce": "iedoce",
    "integra_asem": "asemwebservices_integra",
    "koordinatu": "koordinatu",
    "metacontratas": "metacontratas",
    "seisconecta": "sixconecta",
    "quioo": "quioo",
    "quironprevencion": "quioo",
    "sarenet": "sarenet",
    "sgs_gestiona": "sgs_gestiona",
    "smartosh": "smartosh",
    "validate": "validate",
    "timenet": "timenet",
    "nomio": "nomio",
    "ucae": "ucae",
    "vitaly_cae": "vitaly_cae",
}


@dataclass(frozen=True)
class ContractImportResult:
    source_root: str
    priority_group: str
    platform_slugs: list[str]
    manifests_imported: int
    accounts_imported: int
    platform_accounts_upserted: int
    mappings_imported: int
    skipped: list[str]


def import_first_priority_arm_contracts(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    source_root: Path = DEFAULT_CONTRACT_BUNDLE,
    company_source_label: str = "ARM",
    priority_group: str = "arm_first_priority",
) -> ContractImportResult:
    return import_platform_contracts(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        source_root=source_root,
        company_source_label=company_source_label,
        platform_slugs=FIRST_PRIORITY_ARM_SLUGS,
        priority_group=priority_group,
    )


def import_pending_review_arm_contracts(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    source_root: Path = DEFAULT_CONTRACT_BUNDLE,
    company_source_label: str = "ARM",
    priority_group: str = "arm_pending_review",
) -> ContractImportResult:
    return import_platform_contracts(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        source_root=source_root,
        company_source_label=company_source_label,
        platform_slugs=ARM_PENDING_REVIEW_SLUGS,
        priority_group=priority_group,
    )


def import_all_arm_contracts(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    source_root: Path = DEFAULT_CONTRACT_BUNDLE,
    company_source_label: str = "ARM",
) -> ContractImportResult:
    aggregate = ContractImportResult(
        source_root=str(source_root.resolve()),
        priority_group="all",
        platform_slugs=list(ALL_ACTIVE_ARM_SLUGS),
        manifests_imported=0,
        accounts_imported=0,
        platform_accounts_upserted=0,
        mappings_imported=0,
        skipped=[],
    )
    for slugs, priority_group in (
        (FIRST_PRIORITY_ARM_SLUGS, "arm_first_priority"),
        (ARM_PENDING_REVIEW_SLUGS, "arm_pending_review"),
        (SECOND_PRIORITY_ARM_SLUGS, "arm_second_priority"),
        (BLOCKED_ARM_SLUGS, "arm_blocked"),
    ):
        result = import_platform_contracts(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            source_root=source_root,
            company_source_label=company_source_label,
            platform_slugs=slugs,
            priority_group=priority_group,
        )
        aggregate = ContractImportResult(
            source_root=aggregate.source_root,
            priority_group=aggregate.priority_group,
            platform_slugs=aggregate.platform_slugs,
            manifests_imported=aggregate.manifests_imported + result.manifests_imported,
            accounts_imported=aggregate.accounts_imported + result.accounts_imported,
            platform_accounts_upserted=aggregate.platform_accounts_upserted + result.platform_accounts_upserted,
            mappings_imported=aggregate.mappings_imported + result.mappings_imported,
            skipped=[*aggregate.skipped, *result.skipped],
        )
    return aggregate


def import_platform_contracts(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    source_root: Path,
    company_source_label: str,
    platform_slugs: tuple[str, ...],
    priority_group: str,
) -> ContractImportResult:
    root = source_root.resolve()
    if not root.exists():
        raise FileNotFoundError(str(root))

    manifests_imported = 0
    accounts_imported = 0
    platform_accounts_upserted = 0
    mappings_imported = 0
    skipped: list[str] = []
    for manifest_path in _manifest_paths(root, platform_slugs):
        manifest_data = _load_yaml(manifest_path)
        platform_data = manifest_data.get("platform") or {}
        platform_slug = str(platform_data.get("id") or "").strip()
        if platform_slug not in platform_slugs:
            continue
        platform_key = CONTRACT_SLUG_TO_PLATFORM_KEY.get(platform_slug, platform_slug)
        platform = session.scalar(select(ExternalPlatform).where(ExternalPlatform.platform_key == platform_key))
        if platform is None:
            skipped.append(f"{platform_slug}: missing catalog platform {platform_key}")
            continue
        mappings_path = manifest_path.with_name("04_mappings.yaml")
        mappings_data = _load_yaml(mappings_path) if mappings_path.exists() else {}
        accounts = [
            account
            for account in manifest_data.get("accounts") or []
            if str(account.get("company_source_label") or "").upper() == company_source_label.upper()
        ]
        if not accounts:
            skipped.append(f"{platform_slug}: no accounts for {company_source_label}")
            continue

        manifest = _upsert_manifest(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            external_platform_id=platform.id,
            platform_slug=platform_slug,
            manifest_data=manifest_data,
            source_ref=_relative_source_ref(manifest_path),
            priority_group=priority_group,
            status=_manifest_status(accounts),
        )
        manifests_imported += 1
        session.query(PlatformRpaMappingProposal).filter(
            PlatformRpaMappingProposal.tenant_id == tenant_id,
            PlatformRpaMappingProposal.manifest_id == manifest.id,
        ).delete()
        for account_data in accounts:
            platform_account = _upsert_platform_account(
                session,
                tenant_id=tenant_id,
                external_platform_id=platform.id,
                platform_name=manifest.platform_name,
                account_data=account_data,
            )
            platform_accounts_upserted += 1
            _upsert_account_proposal(
                session,
                tenant_id=tenant_id,
                manifest_id=manifest.id,
                external_platform_id=platform.id,
                platform_account_id=platform_account.id,
                account_data=account_data,
            )
            accounts_imported += 1

        created_mappings = _create_mapping_proposals(
            session,
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            mappings_data=mappings_data,
        )
        mappings_imported += created_mappings
    session.flush()
    return ContractImportResult(
        source_root=str(root),
        priority_group=priority_group,
        platform_slugs=list(platform_slugs),
        manifests_imported=manifests_imported,
        accounts_imported=accounts_imported,
        platform_accounts_upserted=platform_accounts_upserted,
        mappings_imported=mappings_imported,
        skipped=skipped,
    )


def _manifest_paths(root: Path, platform_slugs: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(root.glob("*/03_rpa_manifest.yaml")):
        data = _load_yaml(path)
        platform_slug = str((data.get("platform") or {}).get("id") or "").strip()
        if platform_slug in platform_slugs:
            paths.append(path)
    return paths


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _upsert_manifest(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    external_platform_id: int,
    platform_slug: str,
    manifest_data: dict[str, Any],
    source_ref: str,
    priority_group: str,
    status: str,
) -> PlatformRpaManifest:
    platform_data = manifest_data.get("platform") or {}
    scope_data = manifest_data.get("scope") or {}
    manifest = session.scalar(
        select(PlatformRpaManifest).where(
            PlatformRpaManifest.tenant_id == tenant_id,
            PlatformRpaManifest.platform_slug == platform_slug,
        )
    )
    if manifest is None:
        manifest = PlatformRpaManifest(tenant_id=tenant_id, platform_slug=platform_slug)
        session.add(manifest)
    manifest.external_platform_id = external_platform_id
    manifest.platform_name = str(platform_data.get("name") or platform_slug)
    manifest.family = _optional_string(platform_data.get("family"))
    manifest.mode = str(platform_data.get("mode") or "authorized_rpa")
    manifest.status = status
    manifest.priority_group = priority_group
    manifest.source_ref = source_ref
    manifest.schema_version = _optional_string(manifest_data.get("schema_version"))
    manifest.generated_at = _optional_string(manifest_data.get("generated_at"))
    manifest.hosts = _string_list(platform_data.get("hosts"))
    manifest.entry_urls = _string_list(platform_data.get("entry_urls"))
    manifest.allowed_operations = _string_list(scope_data.get("allowed_operations"))
    manifest.allowed_entity_types = _string_list(scope_data.get("allowed_entity_types"))
    manifest.requires_signed_authorization = bool(platform_data.get("requires_signed_authorization", True))
    manifest.dry_run_default = bool(platform_data.get("dry_run_default", True))
    manifest.manual_approval_required = bool(platform_data.get("manual_approval_required", True))
    manifest.rpa_assisted_on_control = bool(platform_data.get("rpa_assisted_on_captcha_mfa_or_notice", True))
    manifest.sensitive_data_minimization_required = bool(
        platform_data.get("sensitive_data_minimization_required", False)
    )
    manifest.auxiliary_platform_review_required = bool(
        platform_data.get("auxiliary_platform_review_required", False)
    )
    manifest.manifest_json = _redacted_manifest(manifest_data)
    manifest.created_by = manifest.created_by or actor_user_id
    session.flush()
    return manifest


def _upsert_platform_account(
    session: Session,
    *,
    tenant_id: int,
    external_platform_id: int,
    platform_name: str,
    account_data: dict[str, Any],
) -> PlatformAccount:
    display_name = _account_display_name(platform_name, account_data)
    account = session.scalar(
        select(PlatformAccount).where(
            PlatformAccount.tenant_id == tenant_id,
            PlatformAccount.external_platform_id == external_platform_id,
            PlatformAccount.display_name == display_name,
        )
    )
    if account is None:
        account = PlatformAccount(
            tenant_id=tenant_id,
            external_platform_id=external_platform_id,
            display_name=display_name,
        )
        session.add(account)
    account.auth_type = "vault_ref"
    account.encrypted_secret_ref = _optional_string(account_data.get("credential_secret_ref"))
    account.mode = "disabled"
    account.dry_run = bool(account_data.get("dry_run", True))
    account.manual_approval_required = bool(account_data.get("manual_approval_required", True))
    account.status = _account_status(account_data)
    session.flush()
    return account


def _upsert_account_proposal(
    session: Session,
    *,
    tenant_id: int,
    manifest_id: int,
    external_platform_id: int,
    platform_account_id: int,
    account_data: dict[str, Any],
) -> PlatformRpaAccountProposal:
    source_platform_account_id = str(account_data.get("platform_account_id") or "").strip()
    proposal = session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.source_platform_account_id == source_platform_account_id,
        )
    )
    if proposal is None:
        proposal = PlatformRpaAccountProposal(
            tenant_id=tenant_id,
            source_platform_account_id=source_platform_account_id,
        )
        session.add(proposal)
    proposal.manifest_id = manifest_id
    proposal.external_platform_id = external_platform_id
    proposal.platform_account_id = platform_account_id
    proposal.company_source_label = _optional_string(account_data.get("company_source_label"))
    proposal.source_excel_sheet = _optional_string(account_data.get("source_excel_sheet"))
    proposal.source_excel_row = _optional_int(account_data.get("source_excel_row"))
    proposal.external_company_name = _optional_string(account_data.get("external_company_name"))
    proposal.entry_url = _optional_string(account_data.get("entry_url"))
    proposal.host = _optional_string(account_data.get("host"))
    proposal.user_hint_masked = _optional_string(account_data.get("user_hint_masked"))
    proposal.credential_secret_ref = _optional_string(account_data.get("credential_secret_ref"))
    proposal.account_status = str(account_data.get("account_status") or "active_in_source")
    proposal.status = _account_status(account_data)
    proposal.dry_run = bool(account_data.get("dry_run", True))
    proposal.manual_approval_required = bool(account_data.get("manual_approval_required", True))
    proposal.allowed_operations = _string_list(account_data.get("allowed_operations"))
    proposal.allowed_entity_types = _string_list(account_data.get("allowed_entity_types"))
    proposal.notes = _optional_string(account_data.get("notes"))
    session.flush()
    return proposal


def _create_mapping_proposals(
    session: Session,
    *,
    tenant_id: int,
    manifest_id: int,
    external_platform_id: int,
    mappings_data: dict[str, Any],
) -> int:
    created = 0
    field_mappings = mappings_data.get("field_mappings") or {}
    if isinstance(field_mappings, dict):
        for entity_scope, mappings in field_mappings.items():
            if not isinstance(mappings, list):
                continue
            for item in mappings:
                if not isinstance(item, dict):
                    continue
                session.add(
                    PlatformRpaMappingProposal(
                        tenant_id=tenant_id,
                        manifest_id=manifest_id,
                        external_platform_id=external_platform_id,
                        mapping_kind="field",
                        entity_scope=str(entity_scope),
                        iker_key=str(item.get("iker_field") or ""),
                        external_label=_optional_string(item.get("external_label_or_field_proposed")),
                        requirement=_optional_string(item.get("requirement")),
                        review_status="pending_review",
                        status=str(item.get("status") or "proposed_pending_platform_validation"),
                        metadata_json={"source": "field_mappings"},
                    )
                )
                created += 1
    for item in mappings_data.get("document_type_mappings") or []:
        if not isinstance(item, dict):
            continue
        session.add(
            PlatformRpaMappingProposal(
                tenant_id=tenant_id,
                manifest_id=manifest_id,
                external_platform_id=external_platform_id,
                mapping_kind="document_type",
                entity_scope=None,
                iker_key=str(item.get("iker_document_type") or ""),
                external_label=_optional_string(item.get("external_document_type_proposed")),
                external_catalog_value=_optional_string(item.get("external_catalog_value")),
                applies_to=_optional_string(item.get("applies_to")),
                review_status="pending_review",
                status=str(item.get("status") or "proposed_pending_platform_validation"),
                metadata_json={"source": "document_type_mappings"},
            )
        )
        created += 1
    catalogs = mappings_data.get("catalogs") or {}
    if isinstance(catalogs, dict):
        for catalog_key, item in catalogs.items():
            if not isinstance(item, dict):
                continue
            session.add(
                PlatformRpaMappingProposal(
                    tenant_id=tenant_id,
                    manifest_id=manifest_id,
                    external_platform_id=external_platform_id,
                    mapping_kind="catalog",
                    entity_scope=None,
                    iker_key=str(catalog_key),
                    external_label=_optional_string(item.get("source")),
                    external_catalog_value=_optional_string(item.get("external_catalog_status")),
                    review_status="pending_review",
                    status="pending_platform_confirmation",
                    metadata_json={"source": "catalogs"},
                )
            )
            created += 1
    session.flush()
    return created


def _manifest_status(accounts: list[dict[str, Any]]) -> str:
    if any(_has_pending_endpoint(account.get("host")) or _has_pending_endpoint(account.get("entry_url")) for account in accounts):
        return "blocked_pending_host"
    return "proposal_disabled"


def _account_status(account_data: dict[str, Any]) -> str:
    if _has_pending_endpoint(account_data.get("host")) or _has_pending_endpoint(account_data.get("entry_url")):
        return "blocked_pending_host"
    if str(account_data.get("account_status") or "") != "active_in_source":
        return "inactive_source"
    return "proposal_disabled"


def _has_pending_endpoint(value: object) -> bool:
    return str(value or "").strip().upper().startswith("PENDIENTE")


def _account_display_name(platform_name: str, account_data: dict[str, Any]) -> str:
    external_company = _optional_string(account_data.get("external_company_name")) or "Cuenta"
    value = f"{platform_name} - {external_company}"
    return value[:180]


def _redacted_manifest(manifest_data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(manifest_data)
    cleaned_accounts: list[dict[str, Any]] = []
    for account in manifest_data.get("accounts") or []:
        if not isinstance(account, dict):
            continue
        clean_account = dict(account)
        if clean_account.get("credential_secret_ref"):
            clean_account["credential_secret_ref"] = "vault://***"
        cleaned_accounts.append(clean_account)
    cleaned["accounts"] = cleaned_accounts
    return cleaned


def _relative_source_ref(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        cleaned = str(value).strip()
        return int(cleaned) if cleaned else None
    except (TypeError, ValueError):
        return None
