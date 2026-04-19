"""Neo4j-backed hybrid replay service for wellness entities.

This service replays the same offline wellness operations supported by the
MongoDB and SQL template slices, but persists the operation/conflict logs as
Neo4j nodes. Incremental pull and manual conflict resolution remain outside the
Neo4j parity scope for now, so this service focuses on `/v1/sync/push`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from backend.services.neo4j.wellness_service import WellnessService


class SyncService:
    """Replay offline wellness operations against the Neo4j backend."""

    USER_PROFILE_ENTITY = "user_profile"
    _WELLNESS_FEATURE = "wellness"
    _ACTIVITY_ENTITY = "wellness_activity"
    _DIARY_ENTITY = "wellness_diary_entry"
    _CHECKIN_ENTITY = "wellness_checkin"

    def __init__(self) -> None:
        self.wellness_service = WellnessService()
        self.driver = self.wellness_service.driver
        self._indexes_initialized = False

    async def push_operations(
        self,
        *,
        user_id: str,
        operations: List[SyncOperationRequest],
    ) -> List[Dict[str, Any]]:
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
        raise ValueError("Incremental pull is not supported by the Neo4j replay sync service.")

    async def resolve_conflict(
        self,
        *,
        user_id: str,
        request: SyncConflictResolveRequest,
    ) -> Dict[str, Any]:
        return self._rejected_result(
            op_id="manual-resolution",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            error_code="SYNC_UNSUPPORTED",
            error_message="Manual conflict resolution is not implemented for Neo4j wellness sync.",
        )

    async def _ensure_indexes(self) -> None:
        if self._indexes_initialized:
            return

        await self.wellness_service._ensure_indexes()
        statements = [
            "CREATE INDEX sync_operation_log_lookup IF NOT EXISTS FOR (n:SyncOperationLog) ON (n.user_id, n.op_id)",
            "CREATE INDEX sync_conflict_log_user_id IF NOT EXISTS FOR (n:SyncConflictLog) ON (n.user_id, n.detected_at)",
        ]
        with self.driver.session() as session:
            for statement in statements:
                session.run(statement)
        self._indexes_initialized = True

    async def _process_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        try:
            existing = await self._get_existing_result(user_id=user_id, op_id=operation.op_id)
            if existing is not None:
                return existing

            if not self._supports_operation(operation):
                result = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=(
                        "Unsupported sync slice for Neo4j backend: "
                        f"feature={operation.feature!r}, entity_type={operation.entity_type!r}"
                    ),
                )
                return await self._store_result(user_id=user_id, operation=operation, result=result)

            if operation.entity_type == self._ACTIVITY_ENTITY:
                result = await self._process_activity_operation(user_id=user_id, operation=operation)
            elif operation.entity_type == self._DIARY_ENTITY:
                result = await self._process_diary_operation(user_id=user_id, operation=operation)
            elif operation.entity_type == self._CHECKIN_ENTITY:
                result = await self._process_checkin_operation(user_id=user_id, operation=operation)
            else:
                result = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=f"Unsupported entity_type: {operation.entity_type}",
                )

            return await self._store_result(user_id=user_id, operation=operation, result=result)
        except Exception as exc:  # pragma: no cover - defensive fallback
            return self._retryable_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_message=str(exc),
            )

    def _supports_operation(self, operation: SyncOperationRequest) -> bool:
        if operation.entity_type.startswith("wellness_"):
            return True
        return operation.feature == self._WELLNESS_FEATURE

    async def _process_activity_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        if operation.action not in {"update", "upsert"}:
            return self._rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._ACTIVITY_ENTITY}: {operation.action}",
            )

        existing = await self.wellness_service._find_activity_doc(user_id, operation.entity_id)
        if existing is None:
            return self._rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message="Activity not found",
            )

        if operation.base_updated_at is None:
            return self._rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message="wellness activity updates require base_updated_at",
            )

        client_favorite = bool(operation.payload.get("favorite", existing.get("favorite", False)))
        current_updated_at = self._parse_iso(existing.get("updated_at"))
        base_updated_at = self._normalize_dt(operation.base_updated_at)

        if current_updated_at is not None and current_updated_at == base_updated_at:
            updated = await self._apply_activity_update(
                user_id=user_id,
                activity_id=operation.entity_id,
                favorite=client_favorite,
            )
            return self._applied_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                server_payload=updated,
            )

        base_payload = operation.base_payload or {}
        if base_payload.get("favorite") == existing.get("favorite"):
            updated = await self._apply_activity_update(
                user_id=user_id,
                activity_id=operation.entity_id,
                favorite=client_favorite,
            )
            return self._merged_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                server_payload=updated,
            )

        conflict = self._conflict_result(
            op_id=operation.op_id,
            entity_type=operation.entity_type,
            entity_id=operation.entity_id,
            base_payload=operation.base_payload or {},
            client_payload=dict(operation.payload),
            server_payload=existing,
            conflict_fields=["favorite"],
            error_message="Activity changed on the server while offline.",
        )
        await self._record_conflict(user_id=user_id, operation=operation, result=conflict)
        return conflict

    async def _process_diary_operation(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        if operation.action not in {"create", "upsert"}:
            return self._rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._DIARY_ENTITY}: {operation.action}",
            )

        existing = await self._find_diary_doc(user_id=user_id, entry_id=operation.entity_id)
        if existing is not None:
            payload = await self.wellness_service._build_diary_item(user_id, existing)
            return self._applied_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                server_payload=payload,
            )

        title = str(operation.payload.get("title") or "").strip()
        summary = str(operation.payload.get("summary") or "").strip()
        if not title or not summary:
            return self._rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message="Diary payload requires title and summary.",
            )

        related_activity_id = operation.payload.get("related_activity_id")
        if related_activity_id:
            related_activity = await self.wellness_service._find_activity_doc(user_id, str(related_activity_id))
            if related_activity is None:
                return self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message="Related activity not found.",
                )

        created_at = self._payload_datetime(operation.payload.get("created_at")) or self._now_utc()
        updated_at = self._now_utc()
        mood_score = int(operation.payload.get("mood_score") or 0)
        document = {
            "id": operation.entity_id,
            "user_id": user_id,
            "title": title,
            "summary": summary,
            "title_key": None,
            "summary_key": None,
            "mood_state_key": self.wellness_service._metric_state_key("mood", mood_score),
            "mood_score": mood_score,
            "tag_keys": self.wellness_service._normalize_tag_keys(
                [str(item) for item in operation.payload.get("tag_keys", [])],
            ),
            "related_activity_id": str(related_activity_id) if related_activity_id else None,
            "created_at": self._iso(created_at),
            "updated_at": self._iso(updated_at),
        }
        with self.driver.session() as session:
            session.run("CREATE (d:WellnessDiaryEntry) SET d = $props", props=document)
        payload = await self.wellness_service._build_diary_item(user_id, document)
        return self._applied_result(
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
        if operation.action not in {"create", "upsert"}:
            return self._rejected_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported action for {self._CHECKIN_ENTITY}: {operation.action}",
            )

        existing = await self._find_checkin_doc(user_id=user_id, checkin_id=operation.entity_id)
        if existing is not None:
            return self._applied_result(
                op_id=operation.op_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                server_payload=existing,
            )

        recorded_at = self._payload_datetime(operation.payload.get("recorded_at")) or self._now_utc()
        created_at = self._payload_datetime(operation.payload.get("created_at")) or recorded_at
        updated_at = self._now_utc()
        document = {
            "id": operation.entity_id,
            "user_id": user_id,
            "recorded_at": self._iso(recorded_at),
            "mood_score": int(operation.payload.get("mood_score") or 0),
            "stress_score": int(operation.payload.get("stress_score") or 0),
            "energy_score": int(operation.payload.get("energy_score") or 0),
            "note": self._optional_text(operation.payload.get("note")),
            "created_at": self._iso(created_at),
            "updated_at": self._iso(updated_at),
        }
        with self.driver.session() as session:
            session.run("CREATE (c:WellnessCheckIn) SET c = $props", props=document)
        return self._applied_result(
            op_id=operation.op_id,
            entity_type=operation.entity_type,
            entity_id=operation.entity_id,
            server_payload=document,
        )

    async def _apply_activity_update(
        self,
        *,
        user_id: str,
        activity_id: str,
        favorite: bool,
    ) -> Dict[str, Any]:
        now = self._iso(self._now_utc())
        query = """
        MATCH (a:WellnessActivity {user_id: $user_id, id: $activity_id})
        SET a.favorite = $favorite,
            a.updated_at = $updated_at
        RETURN a {
            .id, .user_id, .icon_key, .title_key, .title, .summary_key, .summary,
            .duration_minutes, .favorite, .category_keys, .energy_impact,
            .created_at, .updated_at
        } AS activity
        """
        with self.driver.session() as session:
            record = session.run(
                query,
                user_id=user_id,
                activity_id=activity_id,
                favorite=favorite,
                updated_at=now,
            ).single()
        if record is None:
            raise ValueError("Updated activity could not be reloaded.")
        return dict(record["activity"])

    async def _find_diary_doc(self, *, user_id: str, entry_id: str) -> Optional[Dict[str, Any]]:
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
        query = """
        MATCH (c:WellnessCheckIn {user_id: $user_id, id: $checkin_id})
        RETURN c {
            .id, .user_id, .recorded_at, .mood_score, .stress_score, .energy_score,
            .note, .created_at, .updated_at
        } AS checkin
        LIMIT 1
        """
        with self.driver.session() as session:
            record = session.run(query, user_id=user_id, checkin_id=checkin_id).single()
        if record is None:
            return None
        return dict(record["checkin"])

    async def _get_existing_result(
        self,
        *,
        user_id: str,
        op_id: str,
    ) -> Optional[Dict[str, Any]]:
        query = """
        MATCH (log:SyncOperationLog {user_id: $user_id, op_id: $op_id})
        RETURN log.result_json AS result_json
        LIMIT 1
        """
        with self.driver.session() as session:
            record = session.run(query, user_id=user_id, op_id=op_id).single()
        if record is None:
            return None
        raw_result = record.get("result_json")
        if not raw_result:
            return None
        return json.loads(str(raw_result))

    async def _store_result(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        created_at = self._iso(self._now_utc())
        query = """
        MERGE (log:SyncOperationLog {user_id: $user_id, op_id: $op_id})
        ON CREATE SET
            log.feature = $feature,
            log.device_id = $device_id,
            log.entity_type = $entity_type,
            log.entity_id = $entity_id,
            log.action = $action,
            log.created_at = $created_at,
            log.result_json = $result_json
        RETURN log.result_json AS result_json
        """
        with self.driver.session() as session:
            record = session.run(
                query,
                user_id=user_id,
                op_id=operation.op_id,
                feature=operation.feature,
                device_id=operation.device_id,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                action=operation.action,
                created_at=created_at,
                result_json=json.dumps(result),
            ).single()
        if record is None or not record.get("result_json"):
            return result
        return json.loads(str(record["result_json"]))

    async def _record_conflict(
        self,
        *,
        user_id: str,
        operation: SyncOperationRequest,
        result: Dict[str, Any],
    ) -> None:
        query = """
        CREATE (log:SyncConflictLog {
            user_id: $user_id,
            op_id: $op_id,
            feature: $feature,
            entity_type: $entity_type,
            entity_id: $entity_id,
            detected_at: $detected_at,
            result_json: $result_json
        })
        """
        with self.driver.session() as session:
            session.run(
                query,
                user_id=user_id,
                op_id=operation.op_id,
                feature=operation.feature,
                entity_type=operation.entity_type,
                entity_id=operation.entity_id,
                detected_at=self._iso(self._now_utc()),
                result_json=json.dumps(result),
            )

    def _applied_result(
        self,
        *,
        op_id: str,
        entity_type: str,
        entity_id: str,
        server_payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "op_id": op_id,
            "status": "applied",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "new_version": self._version_for_payload(server_payload),
            "server_payload": server_payload,
            "conflict": None,
            "error_code": None,
            "error_message": None,
        }

    def _merged_result(
        self,
        *,
        op_id: str,
        entity_type: str,
        entity_id: str,
        server_payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "op_id": op_id,
            "status": "merged",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "new_version": self._version_for_payload(server_payload),
            "server_payload": server_payload,
            "conflict": None,
            "error_code": None,
            "error_message": None,
        }

    def _rejected_result(
        self,
        *,
        op_id: str,
        entity_type: str,
        entity_id: str,
        error_code: str,
        error_message: str,
    ) -> Dict[str, Any]:
        return {
            "op_id": op_id,
            "status": "rejected",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "new_version": None,
            "server_payload": None,
            "conflict": None,
            "error_code": error_code,
            "error_message": error_message,
        }

    def _retryable_result(
        self,
        *,
        op_id: str,
        entity_type: str,
        entity_id: str,
        error_message: str,
    ) -> Dict[str, Any]:
        return {
            "op_id": op_id,
            "status": "retryable_error",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "new_version": None,
            "server_payload": None,
            "conflict": None,
            "error_code": "SYNC_RETRYABLE",
            "error_message": error_message,
        }

    def _conflict_result(
        self,
        *,
        op_id: str,
        entity_type: str,
        entity_id: str,
        base_payload: Dict[str, Any],
        client_payload: Dict[str, Any],
        server_payload: Dict[str, Any],
        conflict_fields: List[str],
        error_message: str,
    ) -> Dict[str, Any]:
        server_version = self._version_for_payload(server_payload)
        return {
            "op_id": op_id,
            "status": "conflict",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "new_version": server_version,
            "server_payload": server_payload,
            "conflict": {
                "base_payload": base_payload,
                "client_payload": client_payload,
                "server_payload": server_payload,
                "conflict_fields": conflict_fields,
                "server_version": server_version,
            },
            "error_code": "SYNC_CONFLICT",
            "error_message": error_message,
        }

    def _version_for_payload(self, payload: Optional[Dict[str, Any]]) -> Optional[int]:
        if not payload:
            return None
        timestamp = self._parse_iso(payload.get("updated_at")) or self._parse_iso(payload.get("created_at"))
        if timestamp is None:
            return None
        return int(timestamp.timestamp() * 1000)

    @staticmethod
    def _optional_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_dt(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _now_utc(cls) -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _iso(cls, value: datetime) -> str:
        return cls._normalize_dt(value).isoformat().replace("+00:00", "Z")

    @classmethod
    def _parse_iso(cls, value: Any) -> Optional[datetime]:
        if not value or not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return cls._normalize_dt(parsed)

    @classmethod
    def _payload_datetime(cls, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return cls._normalize_dt(value)
        if isinstance(value, str):
            return cls._parse_iso(value)
        return None
