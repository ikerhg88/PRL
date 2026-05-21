from __future__ import annotations

from app.connectors.rpa.common_readonly import ConfiguredReadonlyConnector, ReadonlyPlatformProfile


class SeisConectaReadonlyConnector(ConfiguredReadonlyConnector):
    profile = ReadonlyPlatformProfile(
        platform_slug="seisconecta",
        connector_key="connector_rpa_seisconecta_readonly",
        display_name="6conecta",
        username_selectors=("input[name='username']", "input[name='user']", "input[type='text']"),
        password_selectors=("input[type='password']",),
        submit_selectors=("button[type='submit']", "input[type='submit']"),
        readonly_paths=(
            "/dashboard",
            "/index.php/component/seysconecta/p3:trabajadores/",
            "/index.php/mis-empresas/maquinas-equipos/p3:equipamientos/",
        ),
        expected_success_terms=("Estructura", "Empleados", "Maquinas", "Máquinas", "CAE"),
    )
