from __future__ import annotations

from typing import Any, Protocol

from app.connectors.rpa.ctaima.readonly import CtaimaReadonlyConnector
from app.connectors.rpa.e_coordina.readonly import ECoordinaReadonlyConnector
from app.connectors.rpa.nomio.readonly import NomioReadonlyConnector
from app.connectors.rpa.seisconecta.readonly import SeisConectaReadonlyConnector
from app.connectors.rpa.timenet.readonly import TimenetReadonlyConnector
from app.connectors.rpa.validate.readonly import ValidateReadonlyConnector
from app.connectors.rpa.vitaly_cae.readonly import VitalyCaeReadonlyConnector
from app.services.platform_credentials import PlatformCredentials


class ReadonlyRpaConnector(Protocol):
    connector_key: str
    platform_slug: str

    def run_login_probe(
        self,
        *,
        entry_url: str,
        credentials: PlatformCredentials,
        expected_context: str,
        timeout_ms: int = 30_000,
    ) -> Any:
        ...


_CONNECTOR_INSTANCES: tuple[Any, ...] = (
    ECoordinaReadonlyConnector(),
    SeisConectaReadonlyConnector(),
    CtaimaReadonlyConnector(),
    NomioReadonlyConnector(),
    TimenetReadonlyConnector(),
    ValidateReadonlyConnector(),
    VitalyCaeReadonlyConnector(),
)

_CONNECTORS: dict[str, ReadonlyRpaConnector] = {
    connector.platform_slug: connector for connector in _CONNECTOR_INSTANCES
}


def implemented_readonly_platform_slugs() -> set[str]:
    return set(_CONNECTORS)


def get_readonly_connector(platform_slug: str) -> ReadonlyRpaConnector | None:
    return _CONNECTORS.get(platform_slug)
