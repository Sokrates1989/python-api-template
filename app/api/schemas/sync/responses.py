"""Response schemas for hybrid sync endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SyncResultStatus = Literal["applied", "conflict", "rejected", "retryable_error"]


class SyncConflictPayload(BaseModel):
    """Conflict payload sent when server and client versions diverge."""

    base_payload: Optional[Dict[str, Any]] = None
    client_payload: Dict[str, Any] = Field(default_factory=dict)
    server_payload: Dict[str, Any] = Field(default_factory=dict)
    conflict_fields: List[str] = Field(default_factory=list)
    server_version: Optional[int] = None


class SyncOperationResult(BaseModel):
    """Per-operation result for sync push requests."""

    op_id: str
    status: SyncResultStatus
    entity_type: str
    entity_id: str
    new_version: Optional[int] = None
    server_payload: Optional[Dict[str, Any]] = None
    conflict: Optional[SyncConflictPayload] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class SyncPushResponse(BaseModel):
    """Batch push response."""

    results: List[SyncOperationResult] = Field(default_factory=list)


class SyncChange(BaseModel):
    """Single incremental change entry returned by pull."""

    entity_type: str
    entity_id: str
    action: Literal["upsert", "delete"]
    version: int
    updated_at: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class SyncPullResponse(BaseModel):
    """Incremental pull response."""

    changes: List[SyncChange] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool = False
