from __future__ import annotations

from app.connectors.rpa.common_readonly import ConfiguredReadonlyConnector, ReadonlyPlatformProfile


class NomioReadonlyConnector(ConfiguredReadonlyConnector):
    profile = ReadonlyPlatformProfile(
        platform_slug="nomio",
        connector_key="connector_rpa_nomio_readonly",
        display_name="Nomio",
        username_selectors=("input[name='Input.Email']", "input[name='Email']", "input[type='text']"),
        password_selectors=("input[name='Input.Password']", "input[name='Password']", "input[type='password']"),
        submit_selectors=("button[type='submit']", "input[type='submit']"),
        readonly_paths=("/AvisosAutomaticos", "/empresas", "/trabajadores", "/periodos"),
        expected_success_terms=("Nomio", "Menu principal", "Menú principal", "Periodos", "Trabajadores"),
        sensitive_data_scope="labor_headers_and_aggregate_structure_only",
    )
