from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    PlatformAccount,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
)
from app.services.audit import public_state, record_audit
from app.services.credential_vault import encrypt_platform_credentials
from app.services.platform_review_schedules import DEFAULT_REVIEW_SCOPE, TWELVE_HOUR_INTERVAL_MINUTES


ACTIVE_ACCOUNT_STATUS = "active"
INACTIVE_ACCOUNT_STATUS = "baja"
INACTIVE_STATUSES = {INACTIVE_ACCOUNT_STATUS, "inactive", "inactive_source", "disabled"}


@dataclass(frozen=True)
class CurrentPlatformRow:
    source_row: int
    external_company_name: str
    entry_url: str
    host: str | None
    platform_slug: str
    user_hint_masked: str | None
    has_password: bool
    username: str | None = field(default=None, repr=False, compare=False)
    password: str | None = field(default=None, repr=False, compare=False)
    note: str | None = None


@dataclass
class CurrentPlatformSyncResult:
    source_path: str
    rows_loaded: int
    accounts_activated: int = 0
    accounts_marked_baja: int = 0
    credentials_encrypted: int = 0
    schedules_enabled: int = 0
    schedules_disabled: int = 0
    unmatched_rows: list[dict[str, str]] = field(default_factory=list)
    active_accounts: list[dict[str, str]] = field(default_factory=list)
    inactive_accounts: list[dict[str, str]] = field(default_factory=list)


def load_current_platform_rows(path: Path) -> list[CurrentPlatformRow]:
    try:
        import openpyxl
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError("openpyxl is required to read current platform Excel files.") from exc

    workbook = openpyxl.load_workbook(path, data_only=True)
    worksheets = workbook.worksheets
    if not worksheets:
        return []
    worksheet = worksheets[0]
    rows: list[CurrentPlatformRow] = []
    for index, values in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
        external_company = _clean(values[0] if len(values) > 0 else None)
        entry_url = _clean(values[1] if len(values) > 1 else None)
        user_value = _clean(values[2] if len(values) > 2 else None)
        password_value = _clean(values[3] if len(values) > 3 else None)
        note = _clean(values[4] if len(values) > 4 else None)
        if not external_company and not entry_url:
            continue
        platform_slug = _platform_slug(entry_url=entry_url, external_company=external_company)
        rows.append(
            CurrentPlatformRow(
                source_row=index,
                external_company_name=external_company,
                entry_url=_normalized_entry_url(entry_url),
                host=_host(entry_url),
                platform_slug=platform_slug,
                username=user_value or None,
                password=password_value or None,
                user_hint_masked=_mask_user(user_value),
                has_password=bool(password_value),
                note=note or None,
            )
        )
    return rows


def sync_current_platform_accounts(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    rows: list[CurrentPlatformRow],
    source_path: Path,
) -> CurrentPlatformSyncResult:
    result = CurrentPlatformSyncResult(source_path=str(source_path), rows_loaded=len(rows))
    proposals = list(
        session.scalars(
            select(PlatformRpaAccountProposal)
            .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
            .order_by(PlatformRpaAccountProposal.id)
        )
    )
    manifests = {
        manifest.id: manifest
        for manifest in session.scalars(
            select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
        )
    }
    active_proposal_ids: set[int] = set()

    for row in rows:
        proposal = _best_match(row, proposals, manifests)
        if proposal is None:
            result.unmatched_rows.append(
                {
                    "source_row": str(row.source_row),
                    "platform_slug": row.platform_slug,
                    "external_company_name": row.external_company_name,
                }
            )
            continue
        active_proposal_ids.add(proposal.id)
        if _activate_proposal(session, proposal=proposal, row=row):
            result.credentials_encrypted += 1
        result.accounts_activated += 1
        result.active_accounts.append(
            {
                "id": str(proposal.id),
                "platform_slug": manifests[proposal.manifest_id].platform_slug,
                "external_company_name": proposal.external_company_name or "",
            }
        )

    for proposal in proposals:
        if proposal.id in active_proposal_ids:
            continue
        _mark_proposal_baja(session, proposal=proposal)
        result.accounts_marked_baja += 1
        manifest = manifests.get(proposal.manifest_id)
        result.inactive_accounts.append(
            {
                "id": str(proposal.id),
                "platform_slug": manifest.platform_slug if manifest else "",
                "external_company_name": proposal.external_company_name or "",
            }
        )

    active_manifest_ids = {
        proposal.manifest_id for proposal in proposals if proposal.id in active_proposal_ids
    }
    for manifest in manifests.values():
        manifest.status = ACTIVE_ACCOUNT_STATUS if manifest.id in active_manifest_ids else INACTIVE_ACCOUNT_STATUS
        schedule = _ensure_schedule(session, tenant_id=tenant_id, actor_user_id=actor_user_id, manifest=manifest)
        if manifest.id in active_manifest_ids:
            schedule.enabled = True
            schedule.interval_minutes = TWELVE_HOUR_INTERVAL_MINUTES
            schedule.review_scope = list(DEFAULT_REVIEW_SCOPE)
            schedule.status = "scheduled"
            schedule.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=TWELVE_HOUR_INTERVAL_MINUTES)
            schedule.dry_run = True
            schedule.manual_approval_required = True
            schedule.notes = (
                "Activa por Excel vigente de plataformas ARM; revision segura cada 12h "
                "sin bypass de captcha/MFA y con aprobacion humana cuando proceda."
            )
            result.schedules_enabled += 1
        else:
            schedule.enabled = False
            schedule.status = INACTIVE_ACCOUNT_STATUS
            schedule.next_run_at = None
            schedule.dry_run = True
            schedule.manual_approval_required = True
            schedule.notes = "Baja por no aparecer en Excel vigente de plataformas ARM."
            result.schedules_disabled += 1

    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_accounts.sync_current_excel",
        entity_type="tenant",
        entity_id=tenant_id,
        after=public_state(
            {
                "source_path": source_path.name,
                "rows_loaded": result.rows_loaded,
                "accounts_activated": result.accounts_activated,
                "accounts_marked_baja": result.accounts_marked_baja,
                "credentials_encrypted": result.credentials_encrypted,
                "unmatched_rows": len(result.unmatched_rows),
                "secrets_imported": result.credentials_encrypted > 0,
            }
        ),
    )
    session.flush()
    return result


def account_is_inactive(status: str | None) -> bool:
    return str(status or "").strip().lower() in INACTIVE_STATUSES


def _activate_proposal(session: Session, *, proposal: PlatformRpaAccountProposal, row: CurrentPlatformRow) -> bool:
    proposal.status = ACTIVE_ACCOUNT_STATUS
    proposal.account_status = "active_in_source"
    proposal.entry_url = row.entry_url or proposal.entry_url
    proposal.host = row.host or proposal.host
    proposal.user_hint_masked = row.user_hint_masked or proposal.user_hint_masked
    proposal.dry_run = True
    proposal.manual_approval_required = True
    credential_stored = False
    if row.username and row.password:
        proposal.credential_secret_ref = encrypt_platform_credentials(
            username=row.username,
            password=row.password,
            metadata={
                "source": "current_platform_excel",
                "source_row": row.source_row,
                "platform_slug": row.platform_slug,
                "host": row.host,
            },
        )
        credential_stored = True
    proposal.notes = _merge_note(
        _strip_obsolete_credential_notes(proposal.notes),
        (
            f"Presente en Excel vigente fila {row.source_row}; credenciales cifradas en DB y "
            "ocultas en logs."
            if credential_stored
            else f"Presente en Excel vigente fila {row.source_row}; sin clave util para cifrar."
        ),
    )
    if proposal.platform_account_id is not None:
        account = session.get(PlatformAccount, proposal.platform_account_id)
        if account is not None:
            account.status = ACTIVE_ACCOUNT_STATUS
            account.mode = "send_receive"
            account.dry_run = True
            account.manual_approval_required = True
            if credential_stored:
                account.auth_type = "encrypted_db_ref"
                account.encrypted_secret_ref = (
                    f"db://platform_rpa_account_proposals/{proposal.id}/credential_secret_ref"
                )
    return credential_stored


def _mark_proposal_baja(session: Session, *, proposal: PlatformRpaAccountProposal) -> None:
    proposal.status = INACTIVE_ACCOUNT_STATUS
    proposal.account_status = INACTIVE_ACCOUNT_STATUS
    proposal.dry_run = True
    proposal.manual_approval_required = True
    proposal.notes = _merge_note(proposal.notes, "Baja: no aparece en Excel vigente de plataformas ARM.")
    if proposal.platform_account_id is not None:
        account = session.get(PlatformAccount, proposal.platform_account_id)
        if account is not None:
            account.status = INACTIVE_ACCOUNT_STATUS
            account.mode = "disabled"
            account.dry_run = True
            account.manual_approval_required = True


def _ensure_schedule(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    manifest: PlatformRpaManifest,
) -> PlatformReviewSchedule:
    schedule = session.scalar(
        select(PlatformReviewSchedule).where(
            PlatformReviewSchedule.tenant_id == tenant_id,
            PlatformReviewSchedule.manifest_id == manifest.id,
        )
    )
    if schedule is None:
        schedule = PlatformReviewSchedule(
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            external_platform_id=manifest.external_platform_id,
            enabled=False,
            interval_minutes=TWELVE_HOUR_INTERVAL_MINUTES,
            review_scope=list(DEFAULT_REVIEW_SCOPE),
            status="disabled",
            dry_run=True,
            manual_approval_required=True,
            created_by=actor_user_id,
        )
        session.add(schedule)
        session.flush()
    return schedule


def _best_match(
    row: CurrentPlatformRow,
    proposals: list[PlatformRpaAccountProposal],
    manifests: dict[int, PlatformRpaManifest],
) -> PlatformRpaAccountProposal | None:
    candidates = [
        proposal
        for proposal in proposals
        if manifests.get(proposal.manifest_id) is not None
        and manifests[proposal.manifest_id].platform_slug == row.platform_slug
    ]
    if not candidates:
        return None
    scored = sorted(
        ((_company_similarity(row.external_company_name, proposal.external_company_name or ""), proposal) for proposal in candidates),
        key=lambda item: (item[0], -item[1].id),
        reverse=True,
    )
    score, proposal = scored[0]
    return proposal if score >= 0.45 else None


def _company_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _token_set(value: str) -> set[str]:
    stop = {"y", "general", "servei", "grupo"}
    return {token for token in _norm(value).split() if len(token) >= 3 and token not in stop}


def _platform_slug(*, entry_url: str, external_company: str) -> str:
    key = _norm(f"{entry_url} {external_company}")
    if "ctaimacae" in key or "ctaima" in key:
        return "ctaima"
    if "dokyfy" in key or "dokify" in key:
        return "dokyfy"
    if "coordina" in key:
        return "e_coordina"
    if "egestiona" in key:
        return "egestiona"
    if "iedoce" in key:
        return "iedoce"
    if "asemwebservices" in key:
        return "integra_asem"
    if "koordinatu" in key:
        return "koordinatu"
    if "metacontratas" in key:
        return "metacontratas"
    if "quioo" in key:
        return "quioo"
    if "sgs gestiona" in key or "sgs" in key:
        return "sgs_gestiona"
    if "smartosh" in key:
        return "smartosh"
    if "validate" in key:
        return "validate"
    if "vitaly" in key:
        return "vitaly_cae"
    if "6conecta" in key:
        return "seisconecta"
    if "folyo" in key:
        return "folyo"
    if "ucae" in key:
        return "ucae"
    return "unknown"


def _host(entry_url: str) -> str | None:
    if not entry_url:
        return None
    parsed = urlparse(entry_url if "://" in entry_url else f"https://{entry_url}")
    return parsed.netloc.lower() or None


def _normalized_entry_url(entry_url: str) -> str:
    if not entry_url:
        return ""
    return entry_url if "://" in entry_url else f"https://{entry_url}"


def _mask_user(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _merge_note(current: str | None, addition: str) -> str:
    current = current or ""
    if addition in current:
        return current
    return f"{current}\n{addition}".strip()


def _strip_obsolete_credential_notes(current: str | None) -> str:
    lines = []
    for line in (current or "").splitlines():
        normalized = _norm(line)
        if "contrasena no importada" in normalized or "secrets imported false" in normalized:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _clean(value: object) -> str:
    return str(value or "").strip()


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()
