"""Persistence helpers for MongoDB sync operation and conflict logs."""
from __future__ import annotations

from typing import Any, Dict, Optional

from api.schemas.sync.requests import SyncOperationRequest
from backend.services.mongodb.sync_result_helpers import iso_utc, now_utc


async def get_existing_result(collection, *, user_id: str, op_id: str) -> Optional[Dict[str, Any]]:
    """Load a previously stored sync result for an operation id."""
    existing = await collection.find_one({"user_id": user_id, "op_id": op_id}, {"_id": 0, "result": 1})
    if not existing:
        return None
    return dict(existing.get("result") or {})


async def store_result(collection, *, user_id: str, operation: SyncOperationRequest, result: Dict[str, Any]) -> Dict[str, Any]:
    """Persist and return the canonical sync result for an operation."""
    await collection.update_one(
        {"user_id": user_id, "op_id": operation.op_id},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "op_id": operation.op_id,
                "feature": operation.feature,
                "device_id": operation.device_id,
                "entity_type": operation.entity_type,
                "entity_id": operation.entity_id,
                "action": operation.action,
                "created_at": iso_utc(now_utc()),
                "result": result,
            }
        },
        upsert=True,
    )
    stored = await get_existing_result(collection, user_id=user_id, op_id=operation.op_id)
    return stored or result


async def record_conflict(collection, *, user_id: str, operation: SyncOperationRequest, result: Dict[str, Any]) -> None:
    """Persist a conflict log entry for a sync operation."""
    await collection.insert_one(
        {
            "user_id": user_id,
            "op_id": operation.op_id,
            "feature": operation.feature,
            "entity_type": operation.entity_type,
            "entity_id": operation.entity_id,
            "detected_at": iso_utc(now_utc()),
            "result": result,
        }
    )
