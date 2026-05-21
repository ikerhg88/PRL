from __future__ import annotations

from app.connectors.base import CoordinationPlatformConnector
from app.connectors.rpa.ctaima.write import CtaimaWriteConnector
from app.connectors.rpa.e_coordina.write import ECoordinaWriteConnector
from app.connectors.rpa.nomio.write import NomioWriteConnector
from app.connectors.rpa.seisconecta.write import SeisConectaWriteConnector
from app.connectors.rpa.timenet.write import TimenetWriteConnector
from app.connectors.rpa.validate.write import ValidateWriteConnector
from app.connectors.rpa.vitaly_cae.write import VitalyCaeWriteConnector


_CONNECTOR_INSTANCES: tuple[CoordinationPlatformConnector, ...] = (
    ECoordinaWriteConnector(),
    SeisConectaWriteConnector(),
    CtaimaWriteConnector(),
    NomioWriteConnector(),
    TimenetWriteConnector(),
    ValidateWriteConnector(),
    VitalyCaeWriteConnector(),
)

_CONNECTORS: dict[str, CoordinationPlatformConnector] = {
    connector.connector_key: connector for connector in _CONNECTOR_INSTANCES
}

_PLATFORM_TO_CONNECTOR_KEY = {
    str(getattr(connector, "platform_slug")): connector_key
    for connector_key, connector in _CONNECTORS.items()
}


def list_write_connectors() -> list[CoordinationPlatformConnector]:
    return list(_CONNECTORS.values())


def implemented_write_connector_keys() -> set[str]:
    return set(_CONNECTORS)


def write_connector_key_for_platform_slug(platform_slug: str) -> str | None:
    return _PLATFORM_TO_CONNECTOR_KEY.get(platform_slug)


def get_write_connector(connector_key: str) -> CoordinationPlatformConnector | None:
    return _CONNECTORS.get(connector_key)
