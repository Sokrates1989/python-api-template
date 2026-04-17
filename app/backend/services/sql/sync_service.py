"""Hybrid sync service for SQL-backed user profile and wellness synchronization."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from backend.database import get_database_handler
from backend.database.sql_handler import SQLHandler
from backend.services.sql.wellness_service import WellnessService as SQLWellnessService
from models.sql.sync_conflict_log import SyncConflictLog
from models.sql.sync_operation_log import SyncOperationLog
from models.sql.user import User
from models.sql.wellness import WellnessActivity, WellnessCheckIn, WellnessDiaryEntry


class SyncService:
    USER_PROFILE_ENTITY = "user_profile"
    _ACTIVITY_ENTITY = "wellness_activity"
    _DIARY_ENTITY = "wellness_diary_entry"
    _CHECKIN_ENTITY = "wellness_checkin"

    def __init__(self) -> None:
        self.handler = get_database_handler()
        if not isinstance(self.handler, SQLHandler):
            raise ValueError("SyncService requires SQL database")
        self.wellness_service = SQLWellnessService()

    async def push_operations(self, *, user_id: str, operations: List[SyncOperationRequest]) -> List[Dict[str, Any]]:
        await self.wellness_service._ensure_seed_data(user_id)
        results: List[Dict[str, Any]] = []
        async with self.handler.AsyncSessionLocal() as session:
            for operation in operations:
                results.append(await self._process_operation(session=session, user_id=user_id, operation=operation))
        return results

    async def pull_changes(self, *, user_id: str, cursor: Optional[str], limit: int, entity_type: Optional[str]) -> Dict[str, Any]:
        if entity_type and entity_type != self.USER_PROFILE_ENTITY:
            return {"changes": [], "next_cursor": cursor, "has_more": False}
        cursor_dt, cursor_entity = self._decode_cursor(cursor)
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return {"changes": [], "next_cursor": cursor, "has_more": False}
            updated_at = self._normalize_dt(user.updated_at or user.created_at)
            should_emit = cursor_dt is None or self._is_after_cursor(item_dt=updated_at, item_entity=user.id, cursor_dt=cursor_dt, cursor_entity=cursor_entity)
            if not should_emit:
                return {"changes": [], "next_cursor": cursor, "has_more": False}
            change = {"entity_type": self.USER_PROFILE_ENTITY, "entity_id": user.id, "action": "upsert", "version": int(user.version or 1), "updated_at": self._iso(updated_at), "payload": user.to_dict()}
            return {"changes": [change][:limit], "next_cursor": self._encode_cursor(updated_at, user.id), "has_more": False}

    async def resolve_conflict(self, *, user_id: str, request: SyncConflictResolveRequest) -> Dict[str, Any]:
        if request.entity_type != self.USER_PROFILE_ENTITY:
            return self._rejected_result(op_id="manual-resolution", entity_type=request.entity_type, entity_id=request.entity_id, error_code="SYNC_UNSUPPORTED", error_message="Manual conflict resolution is only implemented for user_profile.")
        if request.entity_id != user_id:
            return self._rejected_result(op_id="manual-resolution", entity_type=request.entity_type, entity_id=request.entity_id, error_code="SYNC_AUTH_REQUIRED", error_message="Operation entity_id does not match authenticated user")
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return self._rejected_result(op_id="manual-resolution", entity_type=request.entity_type, entity_id=request.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="User not found")
            if request.expected_server_version is not None and user.version != request.expected_server_version:
                return self._conflict_result(op_id="manual-resolution", entity_type=request.entity_type, entity_id=request.entity_id, base_payload={"id": user.id, "version": request.expected_server_version}, client_payload=request.payload, server_payload=user.to_dict(), conflict_fields=self._conflict_fields(request.payload, user), server_version=user.version)
            if request.strategy == "prefer_server":
                return {"op_id": "manual-resolution", "status": "applied", "entity_type": request.entity_type, "entity_id": request.entity_id, "new_version": int(user.version or 1), "server_payload": user.to_dict(), "conflict": None, "error_code": None, "error_message": None}
            patch = self._extract_supported_patch(request.payload)
            if request.strategy in {"prefer_local", "merged_payload"} and not patch:
                return self._rejected_result(op_id="manual-resolution", entity_type=request.entity_type, entity_id=request.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="payload must contain at least one supported field")
            validation_error = await self._validate_uniques(session=session, user=user, patch=patch)
            if validation_error:
                return self._rejected_result(op_id="manual-resolution", entity_type=request.entity_type, entity_id=request.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=validation_error)
            changed = self._apply_patch(user=user, patch=patch)
            if changed:
                user.version = int(user.version or 1) + 1
                await session.commit()
                await session.refresh(user)
            return {"op_id": "manual-resolution", "status": "applied", "entity_type": request.entity_type, "entity_id": request.entity_id, "new_version": int(user.version or 1), "server_payload": user.to_dict(), "conflict": None, "error_code": None, "error_message": None}

    async def _process_operation(self, *, session, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        try:
            existing = await self._get_existing_result(session=session, op_id=operation.op_id, user_id=user_id)
            if existing is not None:
                return existing
            if operation.entity_type == self.USER_PROFILE_ENTITY:
                result = await self._process_user_profile_operation(session=session, user_id=user_id, operation=operation)
            elif operation.entity_type == self._ACTIVITY_ENTITY:
                result = await self._process_activity_operation(session=session, user_id=user_id, operation=operation)
            elif operation.entity_type == self._DIARY_ENTITY:
                result = await self._process_diary_operation(session=session, user_id=user_id, operation=operation)
            elif operation.entity_type == self._CHECKIN_ENTITY:
                result = await self._process_checkin_operation(session=session, user_id=user_id, operation=operation)
            else:
                result = self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=f"Unsupported entity_type: {operation.entity_type}")
            if result.get("status") == "conflict":
                await self._record_conflict(session=session, user_id=user_id, operation=operation, result=result)
            await self._store_result_and_commit(session=session, operation=operation, user_id=user_id, result=result)
            return result
        except IntegrityError as exc:
            await session.rollback()
            existing = await self._get_existing_result(session=session, op_id=operation.op_id, user_id=user_id)
            if existing is not None:
                return existing
            return {"op_id": operation.op_id, "status": "retryable_error", "entity_type": operation.entity_type, "entity_id": operation.entity_id, "new_version": None, "server_payload": None, "conflict": None, "error_code": "SYNC_RETRYABLE", "error_message": f"Database integrity error: {str(exc)}"}
        except Exception as exc:
            await session.rollback()
            return {"op_id": operation.op_id, "status": "retryable_error", "entity_type": operation.entity_type, "entity_id": operation.entity_id, "new_version": None, "server_payload": None, "conflict": None, "error_code": "SYNC_RETRYABLE", "error_message": str(exc)}

    async def _process_user_profile_operation(self, *, session, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        if operation.entity_id != user_id:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_AUTH_REQUIRED", error_message="Operation entity_id does not match authenticated user")
        if operation.action not in {"update", "upsert"}:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=f"Unsupported action for user_profile: {operation.action}")
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="User not found")
        if operation.base_version is not None and user.version != operation.base_version:
            return self._conflict_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, base_payload={"id": user.id, "version": operation.base_version}, client_payload=operation.payload, server_payload=user.to_dict(), conflict_fields=self._conflict_fields(operation.payload, user), server_version=user.version)
        patch = self._extract_supported_patch(operation.payload)
        if not patch:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="payload must contain at least one supported field")
        validation_error = await self._validate_uniques(session=session, user=user, patch=patch)
        if validation_error:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=validation_error)
        changed = self._apply_patch(user=user, patch=patch)
        if changed:
            user.version = int(user.version or 1) + 1
            await session.flush()
            await session.refresh(user)
        return {"op_id": operation.op_id, "status": "applied", "entity_type": operation.entity_type, "entity_id": operation.entity_id, "new_version": int(user.version or 1), "server_payload": user.to_dict(), "conflict": None, "error_code": None, "error_message": None}

    async def _process_activity_operation(self, *, session, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        if operation.action not in {"update", "upsert"}:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=f"Unsupported action for {self._ACTIVITY_ENTITY}: {operation.action}")
        existing = await self.wellness_service._find_activity(session, user_id, operation.entity_id)
        if existing is None:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="Activity not found")
        if operation.base_updated_at is None:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="wellness activity updates require base_updated_at")
        client_favorite = bool(operation.payload.get("favorite", existing.favorite))
        current_updated_at = self._normalize_dt(existing.updated_at or existing.created_at)
        base_updated_at = self._normalize_dt(operation.base_updated_at)
        if current_updated_at == base_updated_at:
            existing.favorite = client_favorite
            existing.updated_at = self._now_utc()
            return self._applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=existing.to_dict())
        base_payload = operation.base_payload or {}
        if base_payload.get("favorite") == bool(existing.favorite):
            existing.favorite = client_favorite
            existing.updated_at = self._now_utc()
            return self._merged_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=existing.to_dict())
        return self._conflict_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, base_payload=base_payload, client_payload=dict(operation.payload), server_payload=existing.to_dict(), conflict_fields=["favorite"], server_version=self._version_for_payload(existing.to_dict()))

    async def _process_diary_operation(self, *, session, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        if operation.action not in {"create", "upsert"}:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=f"Unsupported action for {self._DIARY_ENTITY}: {operation.action}")
        result = await session.execute(select(WellnessDiaryEntry).where(and_(WellnessDiaryEntry.user_id == user_id, WellnessDiaryEntry.id == operation.entity_id)))
        existing = result.scalar_one_or_none()
        if existing is not None:
            payload = await self.wellness_service._build_diary_item(session, user_id, existing)
            return self._applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=payload)
        title = str(operation.payload.get("title") or "").strip()
        summary = str(operation.payload.get("summary") or "").strip()
        if not title or not summary:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="Diary payload requires title and summary.")
        related_activity_id = operation.payload.get("related_activity_id")
        if related_activity_id and await self.wellness_service._find_activity(session, user_id, str(related_activity_id)) is None:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message="Related activity not found.")
        created_at = self._payload_datetime(operation.payload.get("created_at")) or self._now_utc()
        mood_score = int(operation.payload.get("mood_score") or 0)
        entry = WellnessDiaryEntry(user_id=user_id, id=operation.entity_id, title_key=None, title=title, summary_key=None, summary=summary, mood_state_key=self.wellness_service._metric_state_key("mood", mood_score), mood_score=mood_score, related_activity_id=str(related_activity_id) if related_activity_id else None, created_at=created_at, updated_at=self._now_utc())
        entry.tag_keys = self.wellness_service._normalize_tag_keys([str(item) for item in operation.payload.get("tag_keys", [])])
        session.add(entry)
        payload = await self.wellness_service._build_diary_item(session, user_id, entry)
        return self._applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=payload)

    async def _process_checkin_operation(self, *, session, user_id: str, operation: SyncOperationRequest) -> Dict[str, Any]:
        if operation.action not in {"create", "upsert"}:
            return self._rejected_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, error_code="SYNC_VALIDATION_FAILED", error_message=f"Unsupported action for {self._CHECKIN_ENTITY}: {operation.action}")
        result = await session.execute(select(WellnessCheckIn).where(and_(WellnessCheckIn.user_id == user_id, WellnessCheckIn.id == operation.entity_id)))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return self._applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=existing.to_dict())
        recorded_at = self._payload_datetime(operation.payload.get("recorded_at")) or self._now_utc()
        checkin = WellnessCheckIn(user_id=user_id, id=operation.entity_id, recorded_at=recorded_at, mood_score=int(operation.payload.get("mood_score") or 0), stress_score=int(operation.payload.get("stress_score") or 0), energy_score=int(operation.payload.get("energy_score") or 0), note=self._optional_text(operation.payload.get("note")), created_at=self._payload_datetime(operation.payload.get("created_at")) or recorded_at, updated_at=self._now_utc())
        session.add(checkin)
        return self._applied_result(op_id=operation.op_id, entity_type=operation.entity_type, entity_id=operation.entity_id, server_payload=checkin.to_dict())

    async def _store_result_and_commit(self, *, session, operation: SyncOperationRequest, user_id: str, result: Dict[str, Any]) -> None:
        session.add(SyncOperationLog(op_id=operation.op_id, user_id=user_id, device_id=operation.device_id, entity_type=operation.entity_type, entity_id=operation.entity_id, action=operation.action, status=result.get("status", "rejected"), result_json=SyncOperationLog.dump_result(result)))
        await session.commit()

    async def _get_existing_result(self, *, session, op_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        query = await session.execute(select(SyncOperationLog).where(SyncOperationLog.op_id == op_id))
        existing = query.scalar_one_or_none()
        if existing is None:
            return None
        if existing.user_id != user_id:
            return {"op_id": op_id, "status": "rejected", "entity_type": existing.entity_type, "entity_id": existing.entity_id, "new_version": None, "server_payload": None, "conflict": None, "error_code": "SYNC_AUTH_REQUIRED", "error_message": "Operation id belongs to another user"}
        return existing.get_result()

    async def _record_conflict(self, *, session, user_id: str, operation: SyncOperationRequest, result: Dict[str, Any]) -> None:
        session.add(SyncConflictLog(user_id=user_id, op_id=operation.op_id, feature=operation.feature, entity_type=operation.entity_type, entity_id=operation.entity_id, result_json=SyncConflictLog.dump_result(result)))

    async def _validate_uniques(self, *, session, user: User, patch: Dict[str, Any]) -> Optional[str]:
        email = patch.get("email")
        if email is not None and email != user.email:
            query = await session.execute(select(User).where(and_(User.email == email, User.id != user.id)))
            if query.scalar_one_or_none() is not None:
                return "Email already in use"
        username = patch.get("username")
        if username is not None and username != user.username:
            query = await session.execute(select(User).where(and_(User.username == username, User.id != user.id)))
            if query.scalar_one_or_none() is not None:
                return "Username already in use"
        return None

    def _apply_patch(self, *, user: User, patch: Dict[str, Any]) -> bool:
        changed = False
        for key in ("email", "username", "first_name", "last_name"):
            if key in patch and getattr(user, key) != patch[key]:
                setattr(user, key, patch[key])
                changed = True
        return changed

    def _extract_supported_patch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"email", "username", "first_name", "last_name"}
        return {key: value for key, value in payload.items() if key in allowed}

    def _conflict_fields(self, payload: Dict[str, Any], user: User) -> List[str]:
        fields: List[str] = []
        for key in ("email", "username", "first_name", "last_name"):
            if key in payload and payload.get(key) != getattr(user, key):
                fields.append(key)
        return fields

    def _applied_result(self, *, op_id: str, entity_type: str, entity_id: str, server_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return {"op_id": op_id, "status": "applied", "entity_type": entity_type, "entity_id": entity_id, "new_version": self._version_for_payload(server_payload), "server_payload": server_payload, "conflict": None, "error_code": None, "error_message": None}

    def _merged_result(self, *, op_id: str, entity_type: str, entity_id: str, server_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return {"op_id": op_id, "status": "merged", "entity_type": entity_type, "entity_id": entity_id, "new_version": self._version_for_payload(server_payload), "server_payload": server_payload, "conflict": None, "error_code": None, "error_message": None}

    def _rejected_result(self, *, op_id: str, entity_type: str, entity_id: str, error_code: str, error_message: str) -> Dict[str, Any]:
        return {"op_id": op_id, "status": "rejected", "entity_type": entity_type, "entity_id": entity_id, "new_version": None, "server_payload": None, "conflict": None, "error_code": error_code, "error_message": error_message}

    def _conflict_result(self, *, op_id: str, entity_type: str, entity_id: str, base_payload: Dict[str, Any], client_payload: Dict[str, Any], server_payload: Dict[str, Any], conflict_fields: List[str], server_version: Optional[int]) -> Dict[str, Any]:
        return {"op_id": op_id, "status": "conflict", "entity_type": entity_type, "entity_id": entity_id, "new_version": server_version, "server_payload": server_payload, "conflict": {"base_payload": base_payload, "client_payload": client_payload, "server_payload": server_payload, "conflict_fields": conflict_fields, "server_version": server_version}, "error_code": "SYNC_CONFLICT", "error_message": "Version conflict detected"}

    def _version_for_payload(self, payload: Optional[Dict[str, Any]]) -> Optional[int]:
        if not payload:
            return None
        timestamp = self._payload_datetime(payload.get("updated_at")) or self._payload_datetime(payload.get("created_at"))
        return int(timestamp.timestamp() * 1000) if timestamp is not None else None

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

    def _encode_cursor(self, updated_at: datetime, entity_id: str) -> str:
        payload = {"updated_at": self._iso(updated_at), "entity_id": entity_id}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")

    def _decode_cursor(self, cursor: Optional[str]) -> tuple[Optional[datetime], str]:
        if not cursor:
            return None, ""
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = base64.urlsafe_b64decode(f"{cursor}{padding}").decode("utf-8")
            payload = json.loads(raw)
            updated_raw = payload.get("updated_at")
            entity_id = str(payload.get("entity_id") or "")
            if not updated_raw:
                return None, ""
            decoded_dt = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
            return self._normalize_dt(decoded_dt), entity_id
        except Exception:
            return None, ""

    def _is_after_cursor(self, *, item_dt: datetime, item_entity: str, cursor_dt: datetime, cursor_entity: str) -> bool:
        if item_dt > cursor_dt:
            return True
        if item_dt < cursor_dt:
            return False
        return item_entity > cursor_entity
