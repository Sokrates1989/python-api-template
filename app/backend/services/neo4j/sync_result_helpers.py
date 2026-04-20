"""Result and timestamp helpers for the Neo4j sync service.

This module centralizes repeated response-shaping logic used by the Neo4j sync
service so the orchestration class can remain focused on applying operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services.neo4j.common import iso_utc, normalize_dt, now_utc, parse_iso, payload_datetime



def applied_result(
    *,
    op_id: str,
    entity_type: str,
    entity_id: str,
    server_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build an applied sync result payload.

    Args:
        op_id (str): Operation identifier.
        entity_type (str): Entity type associated with the operation.
        entity_id (str): Entity identifier associated with the operation.
        server_payload (Optional[Dict[str, Any]]): Server state after applying the operation.

    Returns:
        Dict[str, Any]: Standardized sync success payload.
    """
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



def merged_result(
    *,
    op_id: str,
    entity_type: str,
    entity_id: str,
    server_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a merged sync result payload.

    Args:
        op_id (str): Operation identifier.
        entity_type (str): Entity type associated with the operation.
        entity_id (str): Entity identifier associated with the operation.
        server_payload (Optional[Dict[str, Any]]): Server state after applying the merged payload.

    Returns:
        Dict[str, Any]: Standardized sync merged payload.
    """
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



def rejected_result(
    *,
    op_id: str,
    entity_type: str,
    entity_id: str,
    error_code: str,
    error_message: str,
) -> Dict[str, Any]:
    """Build a rejected sync result payload.

    Args:
        op_id (str): Operation identifier.
        entity_type (str): Entity type associated with the operation.
        entity_id (str): Entity identifier associated with the operation.
        error_code (str): Stable rejection code.
        error_message (str): Human-readable rejection reason.

    Returns:
        Dict[str, Any]: Standardized rejection payload.
    """
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



def retryable_result(
    *,
    op_id: str,
    entity_type: str,
    entity_id: str,
    error_message: str,
) -> Dict[str, Any]:
    """Build a retryable-error sync result payload.

    Args:
        op_id (str): Operation identifier.
        entity_type (str): Entity type associated with the operation.
        entity_id (str): Entity identifier associated with the operation.
        error_message (str): Human-readable retryable error reason.

    Returns:
        Dict[str, Any]: Standardized retryable error payload.
    """
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



def conflict_result(
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
    """Build a conflict sync result payload.

    Args:
        op_id (str): Operation identifier.
        entity_type (str): Entity type associated with the operation.
        entity_id (str): Entity identifier associated with the operation.
        base_payload (Dict[str, Any]): Client base payload used for conflict detection.
        client_payload (Dict[str, Any]): Client-submitted payload.
        server_payload (Dict[str, Any]): Current server payload.
        conflict_fields (List[str]): Fields that conflicted.
        error_message (str): Human-readable conflict message.

    Returns:
        Dict[str, Any]: Standardized conflict payload.
    """
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



def version_for_payload(payload: Optional[Dict[str, Any]]) -> Optional[int]:
    """Derive the millisecond version from a stored payload timestamp.

    Args:
        payload (Optional[Dict[str, Any]]): Server payload containing timestamps.

    Returns:
        Optional[int]: Millisecond epoch version or `None` when unavailable.
    """
    if not payload:
        return None
    timestamp = parse_iso(payload.get("updated_at")) or parse_iso(payload.get("created_at"))
    if timestamp is None:
        return None
    return int(timestamp.timestamp() * 1000)



def optional_text(value: Any) -> Optional[str]:
    """Normalize optional text values into stripped strings or `None`.

    Args:
        value (Any): Raw payload value.

    Returns:
        Optional[str]: Stripped text or `None`.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "applied_result",
    "conflict_result",
    "iso_utc",
    "merged_result",
    "normalize_dt",
    "now_utc",
    "optional_text",
    "parse_iso",
    "payload_datetime",
    "rejected_result",
    "retryable_result",
    "version_for_payload",
]
