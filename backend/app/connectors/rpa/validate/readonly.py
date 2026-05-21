from __future__ import annotations

from app.connectors.rpa.common_readonly import ConfiguredReadonlyConnector, ReadonlyPlatformProfile


class ValidateReadonlyConnector(ConfiguredReadonlyConnector):
    profile = ReadonlyPlatformProfile(
        platform_slug="validate",
        connector_key="connector_rpa_validate_readonly",
        display_name="Validate",
        username_selectors=("input[name='user']", "input[name='username']", "input[type='text']"),
        password_selectors=("input[name='password']", "input[type='password']"),
        submit_selectors=("button[type='submit']", "input[type='submit']"),
        expected_success_terms=("Validate",),
        sensitive_data_scope="landing_and_structure_only_until_document_mapping_is_approved",
    )
