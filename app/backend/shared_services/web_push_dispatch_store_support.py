"""Shared validation and serialization helpers for Web Push dispatch stores.

Provider adapters use these helpers to keep timestamp, identifier, job mapping,
and parameterized SQL behavior consistent without depending on one another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from backend.shared_services.web_push_dispatch import (
    WebPushDispatchDraft,
    WebPushDispatchJob,
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class WebPushDispatchStorageNames:
    """Define app-owned provider identifiers for dispatch jobs.

    Attributes:
        sql_table (str): Existing SQL dispatch table.
        mongo_collection (str): MongoDB dispatch collection.
        neo4j_label (str): Neo4j dispatch node label.
        neo4j_constraint (str): Neo4j owner/key constraint name.
    """

    sql_table: str
    mongo_collection: str
    neo4j_label: str
    neo4j_constraint: str

    def __post_init__(self) -> None:
        """Reject unsafe dynamic storage identifiers.

        Returns:
            None.

        Raises:
            ValueError: When any provider identifier is unsafe.

        Side Effects:
            None.
        """
        for field_name, value in (
            ("sql_table", self.sql_table),
            ("mongo_collection", self.mongo_collection),
            ("neo4j_label", self.neo4j_label),
            ("neo4j_constraint", self.neo4j_constraint),
        ):
            if not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"Unsafe Web Push dispatch {field_name}: {value!r}")


def sql_draft_params(
    user_id: str,
    draft: WebPushDispatchDraft,
    now: datetime,
    *,
    job_id: str,
) -> dict[str, Any]:
    """Build bound SQL values for one desired occurrence.

    Args:
        user_id (str): Recipient account.
        draft (WebPushDispatchDraft): Desired occurrence.
        now (datetime): Replacement time.
        job_id (str): Existing or newly generated job identity.

    Returns:
        dict[str, Any]: Parameter values shared by insert/update statements.
    """
    return {
        "job_id": job_id,
        "user_id": user_id,
        "schedule_key": draft.schedule_key,
        "payload": draft.payload,
        "due_at": draft.due_at,
        "expires_at": draft.expires_at,
        "next_attempt_at": draft.due_at,
        "now": now,
    }


def sql_insert_draft(table: str) -> str:
    """Return a parameterized SQL occurrence insertion.

    Args:
        table (str): Validated app-owned table identifier.

    Returns:
        str: SQL insertion statement.
    """
    return f"""
        INSERT INTO {table} (
            job_id, user_id, schedule_key, payload, due_at, expires_at,
            attempt_count, next_attempt_at, lease_token, lease_until,
            last_failure_code, created_at, updated_at
        ) VALUES (
            :job_id, :user_id, :schedule_key, :payload, :due_at, :expires_at,
            0, :next_attempt_at, NULL, NULL, NULL, :now, :now
        )
    """  # nosec B608


def sql_update_draft(table: str) -> str:
    """Return a parameterized SQL occurrence reset.

    Args:
        table (str): Validated app-owned table identifier.

    Returns:
        str: SQL update statement.
    """
    return f"""
        UPDATE {table}
        SET payload = :payload,
            due_at = :due_at,
            expires_at = :expires_at,
            attempt_count = 0,
            next_attempt_at = :next_attempt_at,
            lease_token = NULL,
            lease_until = NULL,
            last_failure_code = NULL,
            updated_at = :now
        WHERE user_id = :user_id AND schedule_key = :schedule_key
    """  # nosec B608


def sql_text(statement: str) -> Any:
    """Wrap SQL text after lazily importing the selected provider dependency.

    Args:
        statement (str): Parameterized SQL statement.

    Returns:
        Any: SQLAlchemy executable text clause.

    Side Effects:
        Imports SQLAlchemy only when the active store uses the SQL adapter.
    """
    from sqlalchemy import text

    return text(statement)


def job_from_mapping(
    values: Mapping[str, Any],
    *,
    lease_token: str,
) -> WebPushDispatchJob:
    """Convert a provider record into one leased dispatch job.

    Args:
        values (Mapping[str, Any]): Provider row/document/record fields.
        lease_token (str): Claim token written by this worker.

    Returns:
        WebPushDispatchJob: Provider-neutral leased job.

    Raises:
        ValueError: When a provider timestamp is malformed or timezone-naive.
    """
    return WebPushDispatchJob(
        job_id=str(values["job_id"]),
        user_id=str(values["user_id"]),
        schedule_key=str(values["schedule_key"]),
        payload=str(values["payload"]),
        due_at=normalize_datetime(values["due_at"]),
        expires_at=normalize_datetime(values["expires_at"]),
        attempt_count=int(values.get("attempt_count") or 0),
        lease_token=lease_token,
    )


def normalize_datetime(value: Any) -> datetime:
    """Parse and normalize one provider timestamp to UTC.

    Args:
        value (Any): Timezone-aware datetime or ISO text.

    Returns:
        datetime: UTC-aware timestamp.

    Raises:
        ValueError: When parsing fails or timezone information is absent.
    """
    parsed = value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(parsed, datetime) or parsed.tzinfo is None:
        raise ValueError("Web Push dispatch timestamps must be timezone-aware.")
    return parsed.astimezone(timezone.utc)


def iso_timestamp(value: datetime) -> str:
    """Return one timezone-aware timestamp as stable UTC ISO text.

    Args:
        value (datetime): Timezone-aware timestamp.

    Returns:
        str: UTC ISO timestamp ending in ``Z``.

    Raises:
        ValueError: When timezone information is absent.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Web Push dispatch timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    Returns:
        datetime: Current UTC time.
    """
    return datetime.now(timezone.utc)
