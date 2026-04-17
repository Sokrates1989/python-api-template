"""Request schemas for hybrid sync endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


SyncAction = Literal["create", "update", "delete", "upsert"]


class SyncOperationRequest(BaseModel):
    """Single sync operation submitted by a client device."""

    op_id: str = Field(..., min_length=1, max_length=128)
    feature: Optional[str] = Field(default=None, min_length=1, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=128)
    entity_type: str = Field(..., min_length=1, max_length=64)
    entity_id: str = Field(..., min_length=1, max_length=255)
    action: SyncAction
    base_version: Optional[int] = Field(default=None, ge=0)
    base_updated_at: Optional[datetime] = None
    base_payload: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    client_timestamp: datetime

    @model_validator(mode="after")
    def validate_base_rules(self) -> "SyncOperationRequest":
        if self.action in {"update", "delete"}:
            has_sql_base = self.base_version is not None
            has_document_base = self.base_updated_at is not None
            if not has_sql_base and not has_document_base:
                raise ValueError(
                    "update/delete operations require either base_version or base_updated_at"
                )
        return self


class SyncPushRequest(BaseModel):
    """Batch push request for pending local operations."""

    operations: List[SyncOperationRequest] = Field(default_factory=list, min_length=1, max_length=500)


class SyncConflictResolveRequest(BaseModel):
    """Request payload for explicit conflict resolution."""

    entity_type: str = Field(..., min_length=1, max_length=64)
    entity_id: str = Field(..., min_length=1, max_length=255)
    strategy: Literal["prefer_server", "prefer_local", "merged_payload"]
    payload: Dict[str, Any] = Field(default_factory=dict)
    expected_server_version: Optional[int] = Field(default=None, ge=0)
