from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_platform_operation_catalog import (  # noqa: E402
    PlatformFacts,
    _canonical_field_key,
    _operation_readiness,
    _write_probe_policy,
)


def test_read_external_status_requires_status_value_for_live_verification() -> None:
    facts = PlatformFacts(platform_key="e_coordina")
    facts.capture_statuses["login_likely_success"] = 1
    facts.capture_standard_keys.add("document.status")

    assert (
        _operation_readiness(
            operation_name="read_external_status",
            facts=facts,
            required=["document.status"],
            capture_missing=[],
            contract_missing=[],
        )
        == "readonly_mapping_ready"
    )

    facts.capture_status_value_keys.add("document.status")
    assert (
        _operation_readiness(
            operation_name="read_external_status",
            facts=facts,
            required=["document.status"],
            capture_missing=[],
            contract_missing=[],
        )
        == "verified_readonly_status_counts_available"
    )


def test_write_probe_policy_never_marks_external_write_executed() -> None:
    facts = PlatformFacts(platform_key="demo")
    facts.capture_statuses["login_likely_success"] = 1
    facts.capture_standard_keys.update({"worker.first_name", "worker.identifier_value"})

    policy = _write_probe_policy(facts, "human_assisted_supported")

    assert policy["external_write_executed"] is False
    assert policy["status"] == "requires_dummy_entity_or_provider_sandbox"
    assert policy["candidate_low_risk_standard_keys"] == ["worker.first_name"]


def test_canonical_field_key_normalizes_manifest_suffixes() -> None:
    assert _canonical_field_key("worker.identifier") == "worker.identifier_value"
    assert _canonical_field_key("document.expiry_date_if_applicable") == "document.expires_at"
    assert _canonical_field_key("document.entity_worker_id") == "worker.identifier_value"
