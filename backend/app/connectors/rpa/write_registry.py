from __future__ import annotations

from typing import cast

from app.connectors.base import CoordinationPlatformConnector
from app.connectors.rpa.ctaima.write import CtaimaWriteConnector
from app.connectors.rpa.dokyfy.write import DokyfyWriteConnector
from app.connectors.rpa.e_coordina.write import ECoordinaWriteConnector
from app.connectors.rpa.egestiona.write import EGestionaWriteConnector
from app.connectors.rpa.folyo.write import FolyoWriteConnector
from app.connectors.rpa.iedoce.write import IEDOCEWriteConnector
from app.connectors.rpa.integra_asem.write import IntegraAsemWriteConnector
from app.connectors.rpa.koordinatu.write import KoordinatuWriteConnector
from app.connectors.rpa.metacontratas.write import MetacontratasWriteConnector
from app.connectors.rpa.nomio.write import NomioWriteConnector
from app.connectors.rpa.quioo.write import QuiooWriteConnector
from app.connectors.rpa.sgs_gestiona.write import SgsGestionaWriteConnector
from app.connectors.rpa.seisconecta.write import SeisConectaWriteConnector
from app.connectors.rpa.smartosh.write import SmartoshWriteConnector
from app.connectors.rpa.timenet.write import TimenetWriteConnector
from app.connectors.rpa.ucae.write import UcaeWriteConnector
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
    DokyfyWriteConnector(),
    EGestionaWriteConnector(),
    FolyoWriteConnector(),
    IEDOCEWriteConnector(),
    IntegraAsemWriteConnector(),
    KoordinatuWriteConnector(),
    MetacontratasWriteConnector(),
    QuiooWriteConnector(),
    SgsGestionaWriteConnector(),
    SmartoshWriteConnector(),
    UcaeWriteConnector(),
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


def live_adapter_status_for_connector_key(connector_key: str | None) -> str:
    if connector_key is None:
        return "no_write_connector"
    connector = _CONNECTORS.get(connector_key)
    if connector is None:
        return "no_write_connector"
    helper = getattr(connector, "helper_spec", None)
    if not callable(helper):
        return "blocked_live_adapter_missing"
    helper_spec = helper()
    if getattr(helper_spec, "live_adapter_available", False):
        return "specific_live_adapter_available"
    return "blocked_live_adapter_missing"


def live_adapter_status_for_platform_slug(platform_slug: str) -> str:
    return live_adapter_status_for_connector_key(write_connector_key_for_platform_slug(platform_slug))


def helper_metadata_for_connector_key(connector_key: str | None) -> dict[str, object] | None:
    if connector_key is None:
        return None
    connector = _CONNECTORS.get(connector_key)
    if connector is None:
        return None
    helper = getattr(connector, "helper_spec", None)
    if not callable(helper):
        return None
    helper_spec = helper()
    as_dict = getattr(helper_spec, "as_dict", None)
    if not callable(as_dict):
        return None
    return cast(dict[str, object], as_dict())


def helper_metadata_for_platform_slug(platform_slug: str) -> dict[str, object] | None:
    return helper_metadata_for_connector_key(write_connector_key_for_platform_slug(platform_slug))


def write_connector_key_for_platform_slug(platform_slug: str) -> str | None:
    return _PLATFORM_TO_CONNECTOR_KEY.get(platform_slug)


def get_write_connector(connector_key: str) -> CoordinationPlatformConnector | None:
    return _CONNECTORS.get(connector_key)
