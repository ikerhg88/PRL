from __future__ import annotations

from app.connectors.rpa.common_readonly import ConfiguredReadonlyConnector, ReadonlyPlatformProfile


class VitalyCaeReadonlyConnector(ConfiguredReadonlyConnector):
    profile = ReadonlyPlatformProfile(
        platform_slug="vitaly_cae",
        connector_key="connector_rpa_vitaly_cae_readonly",
        display_name="Vitaly CAE",
        username_selectors=("input[name='username']", "input[name='email']", "input[type='text']"),
        password_selectors=("input[type='password']",),
        submit_selectors=("button[type='submit']", "input[type='submit']"),
        expected_success_terms=("Vitaly CAE",),
        human_context_terms=("Seleccione la empresa", "Selecciona empresa", "select-client-login"),
        sensitive_data_scope="requires_human_company_selection_before_reading",
    )
