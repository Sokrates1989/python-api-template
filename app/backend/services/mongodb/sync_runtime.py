"""Runtime implementation of the MongoDB sync service."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from backend.services.mongodb.common import metric_state_key, normalize_document, normalize_metric_values, normalize_tag_keys
from backend.services.mongodb.query_helpers import build_diary_item, find_activity_doc
from backend.services.mongodb.sync_log_repository import get_existing_result, record_conflict, store_result
from backend.services.mongodb.sync_result_helpers import (
    applied_result,
    conflict_result,
    iso_utc,
    merged_result,
    normalize_dt,
    now_utc,
    optional_text,
    parse_iso,
    payload_datetime,
    rejected_result,
    retryable_result,
)
from backend.services.mongodb.wellness_runtime import WellnessService


class SyncService:
    """Replay offline wellness operations against the MongoDB backend."""

    USER_PROFILE_ENTITY = "user_profile"
    _WELLNESS_FEATURE = "wellness"
    _ACTIVITY_ENTITY = "wellness_activity"
    _DIARY_ENTITY = "wellness_diary_entry"
    _CHECKIN_ENTITY = "wellness_checkin"

    def __init__(self) -> None:
        """Initialize the service with the MongoDB wellness runtime dependencies."""
        self.wellness_service = WellnessService()
        self.handler = self.wellness_service.handler
        self.operation_log_collection = self.handler.database["sync_operation_log"]
        self.conflict_log_collection = self.handler.database["sync_conflicts"]
        self._indexes_initialized = False

    async def push_operations(self, *, user_id: str, operations: List[SyncOperationRequest]) -> List[Dict[str, Any]]:
        """Replay a batch of offline wellness operations."""
        await self._ensure_indexes()
        results: List[Dict[str, Any]] = []
        for operation in operations:
            results.append(await self._process_operation(user_id=user_id, operation=operation))
        return results

    async def pull_changes(self, *, user_id: str, cursor: Optional[str], limit: int, entity_type: Optional[str]) -> Dict[str, Any]:
        """Reject incremental pulls because Mongo replay parity is push-only."""
        del user_id, cursor, limit, entity_type
        raise ValueError("Incremental pull is not supported by the MongoDB replay sync service.")

    async def resolve_conflict(self, *, user_id: str, request: SyncConflictResolveRequest) -> Dict[str, Any]:
        """Reject manual conflict resolution for the Mongo replay slice."""
        del user_id
        return rejected_result(
            op_id="manual-resolution",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            error_code="SYNC_UNSUPPORTED",
            error_message="Manual conflict resolution is not implemented for MongoDB wellness sync.",
        )

    async def _ensure_indexes(self) -> None:
        """Ensure the MongoDB wellness and sync indexes are present."""
        if self._indexes_initialized:
            return
        await self.wellness_service._ensure_indexes()
        await self.operation_log_collection.create_index([("user_id", 1), ("op_id", 1)], unique=True, name="idx_sync_operation_log_user_op_id")
        await self.conflict_log_collection.create_index([("user_id", 1), ("detected_at", -1)], name="idx_sync_conflicts_user_detected_at")
        self._indexes_initialized = True

    async def _process_operation(self, *, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        """Route one replay operation to the matching wellness handler."""
        try:
            existing = await get_existing_result(self.operation_log_collection, user_id=user_id, op_id=operation.op_id)
            if existing is not None:
                return existing
            if not self._supports_operation(operation):
                result = rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=(
                        "Unsupported sync slice for MongoDB backend: "
                        f"feature={operation.feature!r}, entity_type={operation.entity_type!r}"
                    ),
                )
                return await store_result(self.operation_log_collection, user_id=user_id, operation=operation, result=result)

            if operation.entity_type == self._ACTIVITY_ENTITY:
                result = await self._process_activity_operation(user_id=user_id, operation=operation)
            elif operation.entity_type == self._DIARY_ENTITY:
                result = await self._process_diary_operation(user_id=user_id, operation=operation)
            elif operation.entity_type == self._CHECKIN_ENTITY:
                result = await self._process_checkin_operation(user_id=user_id, operation=operation)
            else:
                result = rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=f"Unsupported entity_type: {operation.entity_type}",
                )

            if result.get("status") == "conflict":
                await record_conflict(self.conflict_log_collection, user_id=user_id, operation=operation, result=result)
            return await store_result(self.operation_log_collection, user_id=user_id, operation=operation, result=result)
        except DuplicateKeyError:
            existing = await get_existing_result(self.operation_log_collection, user_id=user_id, op_id=operation.op_id)
            if existing is not None:
                return existing
            return retryable_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_message="Duplicate key while storing sync result.",
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            return retryable_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_message=str(exc),
            )

    def _supports_operation(self, operation: SyncOperationRequest) -> bool:
        """Return whether the operation belongs to the wellness replay slice."""
        if operation.entity_type.startswith("wellness_"):
            return True
        return operation.feature == self._WELLNESS_FEATURE

    async def _process_activity_operation(self, *, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        """Replay one activity favorite toggle operation."""
        if operation.action not in {"update", "upsert"}:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._ACTIVITY_ENTITY}: {operation.action}",
            )

        existing = await find_activity_doc(self.wellness_service.activities_collection, user_id=user_id, activity_id=operation.entity_id)
        if existing is None:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message="Activity not found",
            )
        if operation.base_updated_at is None:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message="wellness activity updates require base_updated_at",
            )

        client_favorite = bool(operation.payload.get("favorite", existing.get("favorite", False)))
        current_updated_at = parse_iso(existing.get("updated_at"))
        base_updated_at = normalize_dt(operation.base_updated_at)
        if current_updated_at is not None and current_updated_at == base_updated_at:
            updated = await self._apply_activity_update(user_id=user_id, activity_id=operation.entity_id, favorite=client_favorite)
            return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=updated)

        base_payload = operation.base_payload or {}
        if base_payload.get("favorite") == existing.get("favorite"):
            updated = await self._apply_activity_update(user_id=user_id, activity_id=operation.entity_id, favorite=client_favorite)
            return merged_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=updated)

        return conflict_result(
            op_id=operation.op_id,
            entity_type=operation.entity_type,
            entity_id=operation.entity_id,
            base_payload=base_payload,
            client_payload=dict(operation.payload),
            server_payload=existing,
            conflict_fields=["favorite"],
            error_message="Activity changed on the server while offline.",
        )

    async def _process_diary_operation(self, *, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        """Replay one diary creation operation."""
        if operation.action not in {"create", "upsert"}:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._DIARY_ENTITY}: {operation.action}",
            )

        existing = await self.wellness_service.diary_collection.find_one({"user_id": user_id, "id": operation.entity_id}, {"_id": 0})
        if existing is not None:
            payload = await build_diary_item(self.wellness_service.activities_collection, user_id=user_id, entry=existing)
            return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=payload)

        title = str(operation.payload.get("title") or "").strip()
        summary = str(operation.payload.get("summary") or "").strip()
        if not title or not summary:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message="Diary payload requires title and summary.",
            )

        related_activity_id = operation.payload.get("related_activity_id")
        if related_activity_id:
            related_activity = await find_activity_doc(
                self.wellness_service.activities_collection,
                user_id=user_id,
                activity_id=str(related_activity_id),
            )
            if related_activity is None:
                return rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message="Related activity not found.",
                )

        created_at = payload_datetime(operation.payload.get("created_at")) or now_utc()
        updated_at = now_utc()
        mood_score = int(operation.payload.get("mood_score") or 0)
        document = {
            "id": operation.entity_id,
            "user_id": user_id,
            "title": title,
            "summary": summary,
            "title_key": None,
            "summary_key": None,
            "mood_state_key": metric_state_key("mood", mood_score),
            "mood_score": mood_score,
            "tag_keys": normalize_tag_keys([str(item) for item in operation.payload.get("tag_keys", [])]),
            "related_activity_id": str(related_activity_id) if related_activity_id else None,
            "created_at": iso_utc(created_at),
            "updated_at": iso_utc(updated_at),
        }
        await self.wellness_service.diary_collection.insert_one(document)
        payload = await build_diary_item(self.wellness_service.activities_collection, user_id=user_id, entry=document)
        return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=payload)

    async def _process_checkin_operation(self, *, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        """Replay one check-in creation operation."""
        if operation.action not in {"create", "upsert"}:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._CHECKIN_ENTITY}: {operation.action}",
            )

        existing = await self.wellness_service.checkins_collection.find_one({"user_id": user_id, "id": operation.entity_id}, {"_id": 0})
        if existing is not None:
            return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=normalize_document(existing))

        recorded_at = payload_datetime(operation.payload.get("recorded_at")) or now_utc()
        created_at = payload_datetime(operation.payload.get("created_at")) or recorded_at
        updated_at = now_utc()
        tag_values = operation.payload.get("tag_keys") or operation.payload.get("tags") or []
        metric_values = operation.payload.get("metrics") if isinstance(operation.payload.get("metrics"), dict) else {}
        document = {
            "id": operation.entity_id,
            "user_id": user_id,
            "recorded_at": iso_utc(recorded_at),
            "mood_score": int(operation.payload.get("mood_score") or 0),
            "stress_score": int(operation.payload.get("stress_score") or 0),
            "energy_score": int(operation.payload.get("energy_score") or 0),
            "tag_keys": normalize_tag_keys([str(item) for item in tag_values]),
            "metrics": normalize_metric_values(metric_values),
            "activity_id": optional_text(operation.payload.get("activity_id")),
            "note": optional_text(operation.payload.get("note")),
            "created_at": iso_utc(created_at),
            "updated_at": iso_utc(updated_at),
        }
        await self.wellness_service.checkins_collection.insert_one(document)
        return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=normalize_document(document))

    async def _apply_activity_update(self, *, user_id: str, activity_id: str, favorite: bool) -> Dict[str, Any]:
        """Persist and reload one activity favorite update."""
        now = now_utc()
        await self.wellness_service.activities_collection.update_one(
            {"user_id": user_id, "id": activity_id},
            {"$set": {"favorite": favorite, "updated_at": iso_utc(now)}},
        )
        updated = await find_activity_doc(self.wellness_service.activities_collection, user_id=user_id, activity_id=activity_id)
        if updated is None:
            raise ValueError("Updated activity could not be reloaded.")
        return updated
