"""Runtime implementation of the Neo4j sync service.

This module hosts the concrete Neo4j sync orchestration while delegating common
response shaping and log persistence to smaller helper modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from backend.services.neo4j.common import iso_utc, metric_state_key, normalize_metric_values, normalize_tag_keys, now_utc, parse_iso, payload_datetime
from backend.services.neo4j.sync_log_repository import get_existing_result, record_conflict, store_result
from backend.services.neo4j.sync_result_helpers import (
    applied_result,
    conflict_result,
    optional_text,
    rejected_result,
    retryable_result,
)
from backend.services.neo4j.wellness_query_helpers import build_diary_item, find_activity_doc
from backend.services.neo4j.wellness_runtime import WellnessService


class SyncService:
    """Replay offline wellness operations against the Neo4j backend."""

    USER_PROFILE_ENTITY = "user_profile"
    _WELLNESS_FEATURE = "wellness"
    _ACTIVITY_ENTITY = "wellness_activity"
    _ACTIVITY_CATEGORY_ENTITY = "wellness_activity_category"
    _DIARY_ENTITY = "wellness_diary_entry"
    _CHECKIN_ENTITY = "wellness_checkin"

    def __init__(self) -> None:
        """Initialize the service with the Neo4j wellness runtime dependencies."""
        self.wellness_service = WellnessService()
        self.driver = self.wellness_service.driver
        self._indexes_initialized = False

    async def push_operations(
        self,
        *,
        user_id: str,
        operations: List[SyncOperationRequest],
    ) -> List[Dict[str, Any]]:
        """Replay a batch of offline wellness operations.

        Args:
            user_id (str): Authenticated user identifier.
            operations (List[SyncOperationRequest]): Operations to replay.

        Returns:
            List[Dict[str, Any]]: One sync result per operation.
        """
        await self._ensure_indexes()
        results: List[Dict[str, Any]] = []
        for operation in operations:
            results.append(await self._process_operation(user_id=user_id, operation=operation))
        return results

    async def pull_changes(
        self,
        *,
        user_id: str,
        cursor: Optional[str],
        limit: int,
        entity_type: Optional[str],
    ) -> Dict[str, Any]:
        """Reject incremental pulls because Neo4j replay parity is push-only.

        Args:
            user_id (str): Authenticated user identifier.
            cursor (Optional[str]): Ignored incremental cursor.
            limit (int): Ignored result limit.
            entity_type (Optional[str]): Ignored entity type filter.

        Raises:
            ValueError: Always raised because pull is not supported.
        """
        del user_id, cursor, limit, entity_type
        raise ValueError("Incremental pull is not supported by the Neo4j replay sync service.")

    async def resolve_conflict(
        self,
        *,
        user_id: str,
        request: SyncConflictResolveRequest,
    ) -> Dict[str, Any]:
        """Reject manual conflict resolution for the Neo4j replay slice.

        Args:
            user_id (str): Authenticated user identifier.
            request (SyncConflictResolveRequest): Conflict resolution request.

        Returns:
            Dict[str, Any]: Rejected result payload explaining the limitation.
        """
        del user_id
        return rejected_result(
            op_id="manual-resolution",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            error_code="SYNC_UNSUPPORTED",
            error_message="Manual conflict resolution is not implemented for Neo4j wellness sync.",
        )

    async def _ensure_indexes(self) -> None:
        """Ensure the Neo4j wellness and sync indexes are present."""
        if self._indexes_initialized:
            return
        await self.wellness_service._ensure_indexes()
        self._indexes_initialized = True

    async def _process_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        """Route one replay operation to the matching wellness handler.

        Args:
            user_id (str): Authenticated user identifier.
            operation (SyncOperationRequest): Operation to process.

        Returns:
            Dict[str, Any]: Sync result for the operation.
        """
        try:
            existing = await get_existing_result(self.driver, user_id=user_id, op_id=operation.op_id)
            if existing is not None:
                return existing

            if not self._supports_operation(operation):
                result = rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=(
                        "Unsupported sync slice for Neo4j backend: "
                        f"feature={operation.feature!r}, entity_type={operation.entity_type!r}"
                    ),
                )
                return await store_result(self.driver, user_id=user_id, operation=operation, result=result)

            if operation.entity_type == self._ACTIVITY_ENTITY:
                result = await self._process_activity_operation(user_id=user_id, operation=operation)
            elif operation.entity_type == self._ACTIVITY_CATEGORY_ENTITY:
                result = await self._process_activity_category_operation(user_id=user_id, operation=operation)
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
                await record_conflict(self.driver, user_id=user_id, operation=operation, result=result)
            return await store_result(self.driver, user_id=user_id, operation=operation, result=result)
        except Exception as exc:  # pragma: no cover - defensive fallback
            return retryable_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_message=str(exc),
            )

    def _supports_operation(self, operation: SyncOperationRequest) -> bool:
        """Return whether the operation belongs to the wellness replay slice.

        Args:
            operation (SyncOperationRequest): Operation to validate.

        Returns:
            bool: `True` when the operation can be processed by this service.
        """
        if operation.entity_type.startswith("wellness_"):
            return True
        return operation.feature == self._WELLNESS_FEATURE

    async def _process_activity_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        """Replay one activity catalogue operation.

        Args:
            user_id (str): Authenticated user identifier.
            operation (SyncOperationRequest): Activity update operation.

        Returns:
            Dict[str, Any]: Sync result for the activity update.
        """
        if operation.action not in {"create", "update", "upsert", "delete"}:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._ACTIVITY_ENTITY}: {operation.action}",
            )

        payload = {**operation.payload, "id": operation.entity_id}
        existing = await find_activity_doc(self.driver, user_id=user_id, activity_id=operation.entity_id)
        if existing is not None and operation.action == "update" and operation.base_updated_at is not None:
            current_updated_at = parse_iso(existing.get("updated_at"))
            if current_updated_at is not None and current_updated_at != operation.base_updated_at:
                return conflict_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, base_payload=operation.base_payload or {}, client_payload=dict(operation.payload), server_payload=existing, conflict_fields=sorted(set(operation.payload).intersection(existing)), error_message="Activity changed on the server while offline.")
        if operation.action == "delete":
            response = await self.wellness_service.delete_activity(user_id, operation.entity_id)
        elif operation.action == "update":
            response = await self.wellness_service.update_activity(user_id, operation.entity_id, payload)
        else:
            response = ({"status": "success", "data": existing} if existing else await self.wellness_service.create_activity(user_id, payload))
        if response.get("status") != "success":
            return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=str(response.get("message") or "Activity mutation failed"))
        return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=None if operation.action == "delete" else response.get("data"))

    async def _process_activity_category_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        """Replay one activity category catalogue operation."""
        if operation.action not in {"create", "update", "upsert", "delete"}:
            return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=f"Unsupported action for {self._ACTIVITY_CATEGORY_ENTITY}: {operation.action}")
        payload = {**operation.payload, "key": operation.entity_id}
        with self.driver.session() as session:
            record = session.run("MATCH (c:WellnessActivityCategory {user_id: $user_id, key: $key}) RETURN properties(c) AS category", user_id=user_id, key=operation.entity_id).single()
        existing = dict(record["category"]) if record else None
        if existing is not None and operation.action == "update" and operation.base_updated_at is not None:
            current_updated_at = parse_iso(existing.get("updated_at"))
            if current_updated_at is not None and current_updated_at != operation.base_updated_at:
                return conflict_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, base_payload=operation.base_payload or {}, client_payload=dict(operation.payload), server_payload=existing, conflict_fields=sorted(set(operation.payload).intersection(existing)), error_message="Activity category changed on the server while offline.")
        if operation.action == "delete":
            response = await self.wellness_service.delete_activity_category(user_id, operation.entity_id)
        elif operation.action == "update":
            response = await self.wellness_service.update_activity_category(user_id, operation.entity_id, payload)
        else:
            response = ({"status": "success", "data": existing} if existing else await self.wellness_service.create_activity_category(user_id, payload))
        if response.get("status") != "success":
            return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=str(response.get("message") or "Activity category mutation failed"))
        return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=None if operation.action == "delete" else response.get("data"))

    async def _process_diary_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        """Replay one diary create operation.

        Args:
            user_id (str): Authenticated user identifier.
            operation (SyncOperationRequest): Diary creation operation.

        Returns:
            Dict[str, Any]: Sync result for the diary operation.
        """
        if operation.action not in {"create", "update", "upsert", "delete"}:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._DIARY_ENTITY}: {operation.action}",
            )

        existing = await self._find_diary_doc(user_id=user_id, entry_id=operation.entity_id)
        if operation.action == "delete":
            if existing is None:
                return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=None)
            response = await self.wellness_service.delete_diary_entry(user_id, operation.entity_id)
            if response.get("status") != "success":
                return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=str(response.get("message")))
            return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=None)
        if existing is not None:
            if operation.action in {"update", "upsert"}:
                response = await self.wellness_service.update_diary_entry(user_id, operation.entity_id, dict(operation.payload))
                if response.get("status") != "success":
                    return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=str(response.get("message")))
                return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=response.get("data"))
            payload = await build_diary_item(self.driver, user_id=user_id, entry=existing)
            return applied_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                server_payload=payload,
            )
        if operation.action == "update":
            return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="Diary entry not found")

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
            related_activity = await find_activity_doc(self.driver, user_id=user_id, activity_id=str(related_activity_id))
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
        with self.driver.session() as session:
            session.run("CREATE (d:WellnessDiaryEntry) SET d = $props", props=document)
        payload = await build_diary_item(self.driver, user_id=user_id, entry=document)
        return applied_result(
            op_id=operation.op_id,
            entity_type=operation.entity_type,
            entity_id=operation.entity_id,
            server_payload=payload,
        )

    async def _process_checkin_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        """Replay one check-in create operation.

        Args:
            user_id (str): Authenticated user identifier.
            operation (SyncOperationRequest): Check-in creation operation.

        Returns:
            Dict[str, Any]: Sync result for the check-in operation.
        """
        if operation.action not in {"create", "update", "upsert", "delete"}:
            return rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._CHECKIN_ENTITY}: {operation.action}",
            )

        existing = await self._find_checkin_doc(user_id=user_id, checkin_id=operation.entity_id)
        if operation.action == "delete":
            if existing is None:
                return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=None)
            response = await self.wellness_service.delete_checkin(user_id, operation.entity_id)
            if response.get("status") != "success":
                return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=str(response.get("message")))
            return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=None)
        if existing is not None:
            if operation.action in {"update", "upsert"}:
                response = await self.wellness_service.update_checkin(user_id, operation.entity_id, dict(operation.payload))
                if response.get("status") != "success":
                    return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=str(response.get("message")))
                return applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=response.get("data"))
            return applied_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                server_payload=existing,
            )
        if operation.action == "update":
            return rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="Check-in not found")

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
        with self.driver.session() as session:
            session.run("CREATE (c:WellnessCheckIn) SET c = $props", props=document)
        return applied_result(
            op_id=operation.op_id,
            entity_type=operation.entity_type,
            entity_id=operation.entity_id,
            server_payload=document,
        )

    async def _find_diary_doc(self, *, user_id: str, entry_id: str) -> Optional[Dict[str, Any]]:
        """Load one diary entry payload for replay idempotency checks.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier.

        Returns:
            Optional[Dict[str, Any]]: Diary payload when found.
        """
        query = """
        MATCH (d:WellnessDiaryEntry {user_id: $user_id, id: $entry_id})
        RETURN d {
            .id, .title_key, .title, .summary_key, .summary, .mood_state_key,
            .mood_score, .tag_keys, .related_activity_id, .created_at, .updated_at
        } AS entry
        LIMIT 1
        """
        with self.driver.session() as session:
            record = session.run(query, user_id=user_id, entry_id=entry_id).single()
        if record is None:
            return None
        return dict(record["entry"])

    async def _find_checkin_doc(self, *, user_id: str, checkin_id: str) -> Optional[Dict[str, Any]]:
        """Load one check-in payload for replay idempotency checks.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier.

        Returns:
            Optional[Dict[str, Any]]: Check-in payload when found.
        """
        query = """
        MATCH (c:WellnessCheckIn {user_id: $user_id, id: $checkin_id})
        RETURN c {
            .id, .user_id, .recorded_at, .mood_score, .stress_score, .energy_score,
            .tag_keys, .metrics, .activity_id, .note, .created_at, .updated_at
        } AS checkin
        LIMIT 1
        """
        with self.driver.session() as session:
            record = session.run(query, user_id=user_id, checkin_id=checkin_id).single()
        if record is None:
            return None
        return dict(record["checkin"])
