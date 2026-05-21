from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConnectorContext(BaseModel):
    tenant_id: str
    platform_key: str
    dry_run: bool = True
    manual_approval_required: bool = True
    idempotency_key: str | None = None


class ConnectorResult(BaseModel):
    status: str
    message: str
    external_status: str = "unknown"
    audit_required: bool = True
    evidence: dict[str, Any] = {}


class CoordinationPlatformConnector(ABC):
    model_config = ConfigDict(frozen=True)

    connector_key: str
    display_name: str
    connector_type: str
    supports_dry_run: bool = True
    manual_approval_required: bool = True

    @abstractmethod
    async def test_connection(self, context: ConnectorContext) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    async def sync_catalog(self, context: ConnectorContext) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    async def upload_document(
        self,
        context: ConnectorContext,
        document_metadata: dict[str, Any],
    ) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    async def upsert_worker(
        self,
        context: ConnectorContext,
        worker_metadata: dict[str, Any],
    ) -> ConnectorResult:
        raise NotImplementedError
