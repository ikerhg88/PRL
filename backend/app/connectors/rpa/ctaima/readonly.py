from __future__ import annotations

from app.connectors.rpa.common_readonly import ConfiguredReadonlyConnector, ReadonlyPlatformProfile


class CtaimaReadonlyConnector(ConfiguredReadonlyConnector):
    profile = ReadonlyPlatformProfile(
        platform_slug="ctaima",
        connector_key="connector_rpa_ctaima_readonly",
        display_name="CTAIMA / CTAIMA CAE",
        username_selectors=("input[type='email']", "input[type='text']", "#email", "#txtEmail"),
        password_selectors=("input[type='password']", "#password", "#txtPassword"),
        submit_selectors=("button:has-text('CONTINUAR')", "button:has-text('Continuar')", "input[type='submit']"),
        expected_success_terms=("CAE", "Coordinacion", "Coordinación", "Programas"),
        human_context_terms=(
            "captcha",
            "sesion activa",
            "sesión activa",
            "otra sesion",
            "otra sesión",
            "selecciona empresa",
            "seleccione empresa",
        ),
        sensitive_data_scope="captcha_or_human_gateway_required_before_row_reading",
        allow_two_step_login=True,
    )
