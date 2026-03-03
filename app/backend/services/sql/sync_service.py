"""Hybrid sync service for SQL-backed user profile synchronization."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError

from backend.database import get_database_handler
from backend.database.sql_handler import SQLHandler
from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from models.sql.sync_operation_log import SyncOperationLog
from models.sql.user import User


class SyncService:
    """Implements push/pull and conflict resolution for user profile sync."""

    USER_PROFILE_ENTITY = "user_profile"

    def __init__(self) -> None:
        self.handler = get_database_handler()
        if not isinstance(self.handler, SQLHandler):
            raise ValueError("SyncService requires SQL database")

    async def push_operations(
        self,
        *,
        user_id: str,
        operations: List[SyncOperationRequest],
    ) -> List[Dict[str, Any]]:
        """Process a batch of sync operations with per-operation outcomes."""
        results: List[Dict[str, Any]] = []

        async with self.handler.AsyncSessionLocal() as session:
            for operation in operations:
                result = await self._process_operation(
                    session=session,
                    user_id=user_id,
                    operation=operation,
                )
                results.append(result)

        return results

    async def pull_changes(
        self,
        *,
        user_id: str,
        cursor: Optional[str],
        limit: int,
        entity_type: Optional[str],
    ) -> Dict[str, Any]:
        """Return incremental changes after a cursor for the authenticated user."""
        if entity_type and entity_type != self.USER_PROFILE_ENTITY:
            return {
                "changes": [],
                "next_cursor": cursor,
                "has_more": False,
            }

        cursor_dt, cursor_entity = self._decode_cursor(cursor)

        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return {
                    "changes": [],
                    "next_cursor": cursor,
                    "has_more": False,
                }

            updated_at = self._normalize_dt(user.updated_at or user.created_at)
            should_emit = cursor_dt is None or self._is_after_cursor(
                item_dt=updated_at,
                item_entity=user.id,
                cursor_dt=cursor_dt,
                cursor_entity=cursor_entity,
            )

            if not should_emit:
                return {
                    "changes": [],
                    "next_cursor": cursor,
                    "has_more": False,
                }

            payload = user.to_dict()
            change = {
                "entity_type": self.USER_PROFILE_ENTITY,
                "entity_id": user.id,
                "action": "upsert",
                "version": int(user.version or 1),
                "updated_at": self._iso(updated_at),
                "payload": payload,
            }

            return {
                "changes": [change][:limit],
                "next_cursor": self._encode_cursor(updated_at, user.id),
                "has_more": False,
            }

    async def resolve_conflict(
        self,
        *,
        user_id: str,
        request: SyncConflictResolveRequest,
    ) -> Dict[str, Any]:
        """Apply an explicit conflict-resolution strategy for user profile."""
        if request.entity_type != self.USER_PROFILE_ENTITY:
            return self._rejected_result(
                op_id="manual-resolution",
                entity_type=request.entity_type,
                entity_id=request.entity_id,
                error_code="SYNC_VALIDATION_FAILED",
                error_message=f"Unsupported entity_type: {request.entity_type}",
            )

        if request.entity_id != user_id:
            return self._rejected_result(
                op_id="manual-resolution",
                entity_type=request.entity_type,
                entity_id=request.entity_id,
                error_code="SYNC_AUTH_REQUIRED",
                error_message="Operation entity_id does not match authenticated user",
            )

        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                return self._rejected_result(
                    op_id="manual-resolution",
                    entity_type=request.entity_type,
                    entity_id=request.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message="User not found",
                )

            if (
                request.expected_server_version is not None
                and user.version != request.expected_server_version
            ):
                return self._conflict_result(
                    op_id="manual-resolution",
                    entity_type=request.entity_type,
                    entity_id=request.entity_id,
                    base_payload={"id": user.id, "version": request.expected_server_version},
                    client_payload=request.payload,
                    server_payload=user.to_dict(),
                    conflict_fields=self._conflict_fields(request.payload, user),
                    server_version=user.version,
                )

            if request.strategy == "prefer_server":
                return {
                    "op_id": "manual-resolution",
                    "status": "applied",
                    "entity_type": request.entity_type,
                    "entity_id": request.entity_id,
                    "new_version": int(user.version or 1),
                    "server_payload": user.to_dict(),
                    "conflict": None,
                    "error_code": None,
                    "error_message": None,
                }

            patch = self._extract_supported_patch(request.payload)
            if request.strategy in {"prefer_local", "merged_payload"} and not patch:
                return self._rejected_result(
                    op_id="manual-resolution",
                    entity_type=request.entity_type,
                    entity_id=request.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message="payload must contain at least one supported field",
                )

            validation_error = await self._validate_uniques(session=session, user=user, patch=patch)
            if validation_error:
                return self._rejected_result(
                    op_id="manual-resolution",
                    entity_type=request.entity_type,
                    entity_id=request.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=validation_error,
                )

            changed = self._apply_patch(user=user, patch=patch)
            if changed:
                user.version = int(user.version or 1) + 1
                await session.commit()
                await session.refresh(user)

            return {
                "op_id": "manual-resolution",
                "status": "applied",
                "entity_type": request.entity_type,
                "entity_id": request.entity_id,
                "new_version": int(user.version or 1),
                "server_payload": user.to_dict(),
                "conflict": None,
                "error_code": None,
                "error_message": None,
            }

    async def _process_operation(
        self,
        *,
        session,
        user_id: str,
        operation: SyncOperationRequest,
    ) -> Dict[str, Any]:
        """Process one operation with idempotent replay behavior."""
        try:
            existing = await self._get_existing_result(
                session=session,
                op_id=operation.op_id,
                user_id=user_id,
            )
            if existing is not None:
                return existing

            if operation.entity_type != self.USER_PROFILE_ENTITY:
                result = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=f"Unsupported entity_type: {operation.entity_type}",
                )
                await self._store_result_and_commit(
                    session=session,
                    operation=operation,
                    user_id=user_id,
                    result=result,
                )
                return result

            if operation.entity_id != user_id:
                result = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_AUTH_REQUIRED",
                    error_message="Operation entity_id does not match authenticated user",
                )
                await self._store_result_and_commit(
                    session=session,
                    operation=operation,
                    user_id=user_id,
                    result=result,
                )
                return result

            if operation.action not in {"update", "upsert"}:
                result = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=f"Unsupported action for user_profile: {operation.action}",
                )
                await self._store_result_and_commit(
                    session=session,
                    operation=operation,
                    user_id=user_id,
                    result=result,
                )
                return result

            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                rejected = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message="User not found",
                )
                await self._store_result_and_commit(
                    session=session,
                    operation=operation,
                    user_id=user_id,
                    result=rejected,
                )
                return rejected

            if operation.base_version is not None and user.version != operation.base_version:
                conflict = self._conflict_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    base_payload={"id": user.id, "version": operation.base_version},
                    client_payload=operation.payload,
                    server_payload=user.to_dict(),
                    conflict_fields=self._conflict_fields(operation.payload, user),
                    server_version=user.version,
                )
                await self._store_result_and_commit(
                    session=session,
                    operation=operation,
                    user_id=user_id,
                    result=conflict,
                )
                return conflict

            patch = self._extract_supported_patch(operation.payload)
            if not patch:
                rejected = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message="payload must contain at least one supported field",
                )
                await self._store_result_and_commit(
                    session=session,
                    operation=operation,
                    user_id=user_id,
                    result=rejected,
                )
                return rejected

            validation_error = await self._validate_uniques(session=session, user=user, patch=patch)
            if validation_error:
                rejected = self._rejected_result(
                    op_id=operation.op_id,
                    entity_type=operation.entity_type,
                    entity_id=operation.entity_id,
                    error_code="SYNC_VALIDATION_FAILED",
                    error_message=validation_error,
                )
                await self._store_result_and_commit(
                    session=session,
                    operation=operation,
                    user_id=user_id,
                    result=rejected,
                )
                return rejected

            changed = self._apply_patch(user=user, patch=patch)
            if changed:
                user.version = int(user.version or 1) + 1
                await session.flush()
                await session.refresh(user)

            applied = {
                "op_id": operation.op_id,
                "status": "applied",
                "entity_type": operation.entity_type,
                "entity_id": operation.entity_id,
                "new_version": int(user.version or 1),
                "server_payload": user.to_dict(),
                "conflict": None,
                "error_code": None,
                "error_message": None,
            }

            await self._store_result_and_commit(
                session=session,
                operation=operation,
                user_id=user_id,
                result=applied,
            )
            return applied

        except IntegrityError as exc:
            await session.rollback()
            existing = await self._get_existing_result(session=session, op_id=operation.op_id, user_id=user_id)
            if existing is not None:
                return existing
            return {
                "op_id": operation.op_id,
                "status": "retryable_error",
                "entity_type": operation.entity_type,
                "entity_id": operation.entity_id,
                "new_version": None,
                "server_payload": None,
                "conflict": None,
                "error_code": "SYNC_RETRYABLE",
                "error_message": f"Database integrity error: {str(exc)}",
            }
        except Exception as exc:  # pragma: no cover - defensive fallback
            await session.rollback()
            return {
                "op_id": operation.op_id,
                "status": "retryable_error",
                "entity_type": operation.entity_type,
                "entity_id": operation.entity_id,
                "new_version": None,
                "server_payload": None,
                "conflict": None,
                "error_code": "SYNC_RETRYABLE",
                "error_message": str(exc),
            }

    async def _store_result_and_commit(
        self,
        *,
        session,
        operation: SyncOperationRequest,
        user_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Persist operation result for idempotent replay and commit transaction."""
        log_entry = SyncOperationLog(
            op_id=operation.op_id,
            user_id=user_id,
            device_id=operation.device_id,
            entity_type=operation.entity_type,
            entity_id=operation.entity_id,
            action=operation.action,
            status=result.get("status", "rejected"),
            result_json=SyncOperationLog.dump_result(result),
        )
        session.add(log_entry)
        await session.commit()

    async def _get_existing_result(
        self,
        *,
        session,
        op_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Return a previously persisted operation result if present."""
        query = await session.execute(select(SyncOperationLog).where(SyncOperationLog.op_id == op_id))
        existing = query.scalar_one_or_none()
        if existing is None:
            return None
        if existing.user_id != user_id:
            return {
                "op_id": op_id,
                "status": "rejected",
                "entity_type": existing.entity_type,
                "entity_id": existing.entity_id,
                "new_version": None,
                "server_payload": None,
                "conflict": None,
                "error_code": "SYNC_AUTH_REQUIRED",
                "error_message": "Operation id belongs to another user",
            }
        return existing.get_result()

    async def _validate_uniques(self, *, session, user: User, patch: Dict[str, Any]) -> Optional[str]:
        """Validate uniqueness constraints before applying profile patch."""
        email = patch.get("email")
        if email is not None and email != user.email:
            query = await session.execute(
                select(User).where(and_(User.email == email, User.id != user.id))
            )
            if query.scalar_one_or_none() is not None:
                return "Email already in use"

        username = patch.get("username")
        if username is not None and username != user.username:
            query = await session.execute(
                select(User).where(and_(User.username == username, User.id != user.id))
            )
            if query.scalar_one_or_none() is not None:
                return "Username already in use"

        return None

    def _apply_patch(self, *, user: User, patch: Dict[str, Any]) -> bool:
        """Apply supported profile fields. Returns True when data changed."""
        changed = False
        for key in ("email", "username", "first_name", "last_name"):
            if key in patch and getattr(user, key) != patch[key]:
                setattr(user, key, patch[key])
                changed = True
        return changed

    def _extract_supported_patch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Keep only fields supported by the user_profile sync slice."""
        allowed = {"email", "username", "first_name", "last_name"}
        return {key: value for key, value in payload.items() if key in allowed}

    def _conflict_fields(self, payload: Dict[str, Any], user: User) -> List[str]:
        """Return fields that diverge between local payload and server state."""
        fields: List[str] = []
        for key in ("email", "username", "first_name", "last_name"):
            if key in payload and payload.get(key) != getattr(user, key):
                fields.append(key)
        return fields

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
        server_version: Optional[int],
    ) -> Dict[str, Any]:
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
            "error_message": "Version conflict detected",
        }

    def _encode_cursor(self, updated_at: datetime, entity_id: str) -> str:
        """Encode opaque cursor token."""
        payload = {
            "updated_at": self._iso(updated_at),
            "entity_id": entity_id,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")

    def _decode_cursor(self, cursor: Optional[str]) -> tuple[Optional[datetime], str]:
        """Decode cursor token into datetime + tiebreak entity id."""
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

    def _is_after_cursor(
        self,
        *,
        item_dt: datetime,
        item_entity: str,
        cursor_dt: datetime,
        cursor_entity: str,
    ) -> bool:
        """Deterministic ordering helper used by pull cursor comparisons."""
        if item_dt > cursor_dt:
            return True
        if item_dt < cursor_dt:
            return False
        return item_entity > cursor_entity

    def _normalize_dt(self, value: datetime) -> datetime:
        """Normalize datetime values into UTC-aware timestamps."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _iso(self, value: datetime) -> str:
        """Serialize datetime as ISO-8601 UTC."""
        return self._normalize_dt(value).isoformat().replace("+00:00", "Z")


