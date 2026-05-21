from __future__ import annotations

from app.connectors.rpa.common_readonly import ConfiguredReadonlyConnector, ReadonlyPlatformProfile


class TimenetReadonlyConnector(ConfiguredReadonlyConnector):
    profile = ReadonlyPlatformProfile(
        platform_slug="timenet",
        connector_key="connector_rpa_timenet_readonly",
        display_name="Timenet",
        username_selectors=("input[name='username']", "input[name='email']", "input[type='text']"),
        password_selectors=("input[type='password']",),
        submit_selectors=("button[type='submit']", "input[type='submit']"),
        readonly_paths=("/workers", "/checks/control"),
        expected_success_terms=("Panel de control", "Trabajadores", "Control de marcajes"),
        sensitive_data_scope="time_tracking_headers_and_aggregate_structure_only",
    )
