"""Persistence helpers for Neo4j sync operation and conflict logs.

This module isolates the low-level Cypher used to read and write sync
operation/conflict log nodes so the sync service can focus on orchestration.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from api.schemas.sync.requests import SyncOperationRequest
from backend.services.neo4j.common import iso_utc, now_utc


async def get_existing_result(driver, *, user_id: str, op_id: str) -> Optional[Dict[str, Any]]:
    """Load a previously stored sync result for an operation id.

    Args:
        driver: Neo4j driver instance used to open sessions.
        user_id (str): Authenticated user identifier.
        op_id (str): Operation identifier.

    Returns:
        Optional[Dict[str, Any]]: Decoded stored result when present.
    """
    query = """
    MATCH (log:SyncOperationLog {user_id: $user_id, op_id: $op_id})
    RETURN log.result_json AS result_json
    LIMIT 1
    """
    with driver.session() as session:
        record = session.run(query, user_id=user_id, op_id=op_id).single()
    if record is None:
        return None
    raw_result = record.get("result_json")
    if not raw_result:
        return None
    return json.loads(str(raw_result))


async def store_result(driver, *, user_id: str, operation: SyncOperationRequest, result: Dict[str, Any]) -> Dict[str, Any]:
    """Persist and return the canonical sync result for an operation.

    Args:
        driver: Neo4j driver instance used to open sessions.
        user_id (str): Authenticated user identifier.
        operation (SyncOperationRequest): Operation being persisted.
        result (Dict[str, Any]): Computed sync result payload.

    Returns:
        Dict[str, Any]: Persisted result payload.
    """
    created_at = iso_utc(now_utc())
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
    with driver.session() as session:
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


async def record_conflict(driver, *, user_id: str, operation: SyncOperationRequest, result: Dict[str, Any]) -> None:
    """Persist a conflict log entry for a sync operation.

    Args:
        driver: Neo4j driver instance used to open sessions.
        user_id (str): Authenticated user identifier.
        operation (SyncOperationRequest): Operation that produced the conflict.
        result (Dict[str, Any]): Conflict result payload.

    Returns:
        None: Writes a conflict log node when invoked.
    """
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
    with driver.session() as session:
        session.run(
            query,
            user_id=user_id,
            op_id=operation.op_id,
            feature=operation.feature,
            entity_type=operation.entity_type,
            entity_id=operation.entity_id,
            detected_at=iso_utc(now_utc()),
            result_json=json.dumps(result),
        )
