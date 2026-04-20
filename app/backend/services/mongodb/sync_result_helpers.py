"""Result and timestamp helpers for the MongoDB sync service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def normalize_dt(value: datetime) -> datetime:
    """Normalize a datetime into timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def now_utc() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    """Serialize a datetime using the shared Z-suffixed UTC format."""
    return normalize_dt(value).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any) -> Optional[datetime]:
    """Parse an API timestamp into a UTC datetime when possible."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return normalize_dt(parsed)


def payload_datetime(value: Any) -> Optional[datetime]:
    """Convert a payload timestamp field into a normalized datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return normalize_dt(value)
    if isinstance(value, str):
        return parse_iso(value)
    return None


def version_for_payload(payload: Optional[Dict[str, Any]]) -> Optional[int]:
    """Derive the millisecond version from a stored payload timestamp."""
    if not payload:
        return None
    timestamp = parse_iso(payload.get("updated_at")) or parse_iso(payload.get("created_at"))
    if timestamp is None:
        return None
    return int(timestamp.timestamp() * 1000)


def optional_text(value: Any) -> Optional[str]:
    """Normalize optional text values into stripped strings or `None`."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def applied_result(*, op_id: str, entity_type: str, entity_id: str, server_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build an applied sync result payload."""
    return {
        "op_id": op_id,
        "status": "applied",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "new_version": version_for_payload(server_payload),
        "server_payload": server_payload,
        "conflict": None,
        "error_code": None,
        "error_message": None,
    }


def merged_result(*, op_id: str, entity_type: str, entity_id: str, server_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a merged sync result payload."""
    return {
        "op_id": op_id,
        "status": "merged",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "new_version": version_for_payload(server_payload),
        "server_payload": server_payload,
        "conflict": None,
        "error_code": None,
        "error_message": None,
    }


def rejected_result(*, op_id: str, entity_type: str, entity_id: str, error_code: str, error_message: str) -> Dict[str, Any]:
    """Build a rejected sync result payload."""
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


def retryable_result(*, op_id: str, entity_type: str, entity_id: str, error_message: str) -> Dict[str, Any]:
    """Build a retryable-error sync result payload."""
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


def conflict_result(*, op_id: str, entity_type: str, entity_id: str, base_payload: Dict[str, Any], client_payload: Dict[str, Any], server_payload: Dict[str, Any], conflict_fields: List[str], error_message: str) -> Dict[str, Any]:
    """Build a conflict sync result payload."""
    server_version = version_for_payload(server_payload)
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
