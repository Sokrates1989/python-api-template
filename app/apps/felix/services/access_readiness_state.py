"""Felix access-readiness state normalization helpers.

The access-readiness record mirrors FelixAppNew's setup gate contract. It is
kept app-owned because setup completion, legal acceptance, and setupPayload
feature switches are Felix product behavior rather than shared API-template
wellness state.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


def default_access_readiness_state() -> Dict[str, Any]:
    """Return the default access-readiness record for a new Felix user.

    Args:
        None.

    Returns:
        Dict[str, Any]: Fresh PWA-compatible readiness state.

    Side Effects:
        None.
    """
    return {
        "setupCompleted": False,
        "setupCompletedAt": None,
        "legalAcceptedVersion": None,
        "legalAcceptedAt": None,
        "setupPayload": None,
    }


def normalize_access_readiness_state(raw_state: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Normalize a stored Felix access-readiness record.

    Args:
        raw_state (Optional[Mapping[str, Any]]): Stored MongoDB document, SQL
            row mapping, Neo4j properties, or partial API state.

    Returns:
        Dict[str, Any]: Complete camelCase readiness record matching the PWA
            integration contract.

    Side Effects:
        None.
    """
    raw = dict(raw_state or {})
    return {
        "setupCompleted": _normalize_bool(_read_key(raw, "setupCompleted", "setup_completed")),
        "setupCompletedAt": _normalize_timestamp_text(_read_key(raw, "setupCompletedAt", "setup_completed_at")),
        "legalAcceptedVersion": _normalize_optional_text(
            _read_key(raw, "legalAcceptedVersion", "legal_accepted_version")
        ),
        "legalAcceptedAt": _normalize_timestamp_text(_read_key(raw, "legalAcceptedAt", "legal_accepted_at")),
        "setupPayload": _normalize_setup_payload(_read_key(raw, "setupPayload", "setup_payload")),
    }


def normalize_access_readiness_patch(
    patch: Mapping[str, Any],
    *,
    current_state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge a partial access-readiness patch into current state.

    Args:
        patch (Mapping[str, Any]): Client-supplied update fields in camelCase or
            snake_case form.
        current_state (Optional[Mapping[str, Any]]): Existing readiness state
            used as the merge base. Defaults are used when absent.

    Returns:
        Dict[str, Any]: Complete normalized readiness state.

    Side Effects:
        None.
    """
    merged = normalize_access_readiness_state(current_state)
    patch_map = dict(patch or {})

    if _has_key(patch_map, "setupCompleted", "setup_completed"):
        merged["setupCompleted"] = _normalize_bool(_read_key(patch_map, "setupCompleted", "setup_completed"))
    if _has_key(patch_map, "setupCompletedAt", "setup_completed_at"):
        merged["setupCompletedAt"] = _normalize_timestamp_text(
            _read_key(patch_map, "setupCompletedAt", "setup_completed_at")
        )
    if _has_key(patch_map, "legalAcceptedVersion", "legal_accepted_version"):
        merged["legalAcceptedVersion"] = _normalize_optional_text(
            _read_key(patch_map, "legalAcceptedVersion", "legal_accepted_version")
        )
    if _has_key(patch_map, "legalAcceptedAt", "legal_accepted_at"):
        merged["legalAcceptedAt"] = _normalize_timestamp_text(
            _read_key(patch_map, "legalAcceptedAt", "legal_accepted_at")
        )
    if _has_key(patch_map, "setupPayload", "setup_payload"):
        next_payload = _normalize_setup_payload(_read_key(patch_map, "setupPayload", "setup_payload"))
        if next_payload is not None:
            merged["setupPayload"] = merge_setup_payload(merged.get("setupPayload"), next_payload)

    return normalize_access_readiness_state(merged)


def merge_setup_payload(
    current_payload: Optional[Mapping[str, Any]],
    next_payload: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Shallow-merge setupPayload exactly like FelixAppNew.

    Args:
        current_payload (Optional[Mapping[str, Any]]): Existing setup payload.
        next_payload (Optional[Mapping[str, Any]]): Incoming setup payload
            patch. When null, the current payload is kept.

    Returns:
        Optional[Dict[str, Any]]: Merged JSON-compatible setup payload or null.

    Side Effects:
        None.
    """
    current = _normalize_setup_payload(current_payload)
    next_value = _normalize_setup_payload(next_payload)
    if next_value is None:
        return deepcopy(current)
    if current is None:
        return deepcopy(next_value)
    return {**current, **next_value}


def _read_key(raw: Mapping[str, Any], camel_key: str, snake_key: str) -> Any:
    """Read a value from camelCase or snake_case keys.

    Args:
        raw (Mapping[str, Any]): Raw source mapping.
        camel_key (str): PWA/API key.
        snake_key (str): SQL/service key.

    Returns:
        Any: First present value, or null.

    Side Effects:
        None.
    """
    if camel_key in raw:
        return raw.get(camel_key)
    return raw.get(snake_key)


def _has_key(raw: Mapping[str, Any], camel_key: str, snake_key: str) -> bool:
    """Return whether a camelCase or snake_case key is present.

    Args:
        raw (Mapping[str, Any]): Raw source mapping.
        camel_key (str): PWA/API key.
        snake_key (str): SQL/service key.

    Returns:
        bool: True when either key is present.

    Side Effects:
        None.
    """
    return camel_key in raw or snake_key in raw


def _normalize_bool(value: Any) -> bool:
    """Normalize a stored boolean value.

    Args:
        value (Any): Raw stored value.

    Returns:
        bool: True only for explicit truthy boolean/integer values.

    Side Effects:
        None.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return False


def _normalize_optional_text(value: Any) -> Optional[str]:
    """Normalize an optional text value.

    Args:
        value (Any): Raw stored value.

    Returns:
        Optional[str]: Trimmed text or null.

    Side Effects:
        None.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_timestamp_text(value: Any) -> Optional[str]:
    """Normalize a timestamp value to ISO text.

    Args:
        value (Any): Raw string or datetime timestamp.

    Returns:
        Optional[str]: ISO-8601 timestamp text or null.

    Side Effects:
        None.
    """
    if isinstance(value, datetime):
        timestamp = value
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return _normalize_optional_text(value)


def _normalize_setup_payload(value: Any) -> Optional[Dict[str, Any]]:
    """Normalize setupPayload to a JSON-compatible object.

    Args:
        value (Any): Raw setupPayload object.

    Returns:
        Optional[Dict[str, Any]]: JSON-compatible mapping or null.

    Side Effects:
        None.
    """
    if not isinstance(value, Mapping):
        return None
    return {str(key): _normalize_json_value(raw_value) for key, raw_value in value.items()}


def _normalize_json_value(value: Any) -> Any:
    """Normalize nested setupPayload values to JSON-compatible data.

    Args:
        value (Any): Raw nested setupPayload value.

    Returns:
        Any: JSON-compatible scalar, list, object, or null.

    Side Effects:
        None.
    """
    if isinstance(value, Mapping):
        return {str(key): _normalize_json_value(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
