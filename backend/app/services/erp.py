from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas import ErpConnectorRead, WorkerCreate


def erp_connector_catalog() -> list[ErpConnectorRead]:
    return [connector.to_read_model() for connector in _CONNECTORS.values()]


def get_erp_connector(connector_key: str) -> ErpConnector | None:
    return _CONNECTORS.get(connector_key)


class ErpConnector(Protocol):
    connector_key: str
    name: str
    status: str
    mode: str
    notes: str

    @property
    def available(self) -> bool: ...

    def to_read_model(self) -> ErpConnectorRead: ...

    def preview_workers(self, *, company_id: int) -> list[WorkerCreate]: ...


@dataclass(frozen=True)
class StaticErpConnector:
    connector_key: str
    name: str
    status: str
    mode: str
    notes: str

    @property
    def available(self) -> bool:
        return self.status == "available"

    def to_read_model(self) -> ErpConnectorRead:
        return ErpConnectorRead(
            connector_key=self.connector_key,
            name=self.name,
            status=self.status,
            mode=self.mode,  # type: ignore[arg-type]
            notes=self.notes,
        )

    def preview_workers(self, *, company_id: int) -> list[WorkerCreate]:
        raise NotImplementedError("Connector does not support worker preview.")


class DemoErpConnector(StaticErpConnector):
    def preview_workers(self, *, company_id: int) -> list[WorkerCreate]:
        return [
            WorkerCreate(
                company_id=company_id,
                first_name="ERP",
                last_name="Demo Uno",
                identifier_type="dni",
                identifier_value="11111111H",
                social_security_number="280000000000",
                work_position="Operario ERP",
                work_center_name="Obra importada ERP",
                employment_status="active",
            ),
            WorkerCreate(
                company_id=company_id,
                first_name="ERP",
                last_name="Demo Dos",
                identifier_type="nie",
                identifier_value="X1234567L",
                social_security_number="289876543210",
                work_position="Encargado ERP",
                work_center_name="Obra importada ERP",
                employment_status="active",
            ),
        ]


_CONNECTORS: dict[str, ErpConnector] = {
    "erp_demo_csv": DemoErpConnector(
        connector_key="erp_demo_csv",
        name="Importador CSV demo",
        status="available",
        mode="file",
        notes="Conector local para validar el flujo de previsualizacion y alta; no llama a APIs externas.",
    ),  # type: ignore[dict-item]
    "erp_authorized_api": StaticErpConnector(
        connector_key="erp_authorized_api",
        name="API autorizada",
        status="disabled_until_configured",
        mode="api",
        notes="Plantilla para un ERP real configurado por empresa con credenciales autorizadas.",
    ),  # type: ignore[dict-item]
}
