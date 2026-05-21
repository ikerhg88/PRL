from __future__ import annotations

from app.connectors.base import CoordinationPlatformConnector
from app.connectors.demo import DemoConnector
from app.connectors.manual_export import ManualExportConnector
from app.connectors.rpa.write_registry import list_write_connectors

_CONNECTORS: dict[str, CoordinationPlatformConnector] = {
    DemoConnector.connector_key: DemoConnector(),
    ManualExportConnector.connector_key: ManualExportConnector(),
}
for connector in list_write_connectors():
    _CONNECTORS[connector.connector_key] = connector


def list_connectors() -> list[CoordinationPlatformConnector]:
    return list(_CONNECTORS.values())


def get_connector(connector_key: str) -> CoordinationPlatformConnector:
    return _CONNECTORS[connector_key]
