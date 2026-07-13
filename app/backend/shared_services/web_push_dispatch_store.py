"""Provider-neutral durable storage for scheduled Web Push dispatch jobs.

Backend apps supply validated SQL table, MongoDB collection, and Neo4j label
identifiers. The store owns replacement, leasing, completion, retry, and
discard mechanics while apps own migrations, payload policy, and authorization.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.database import get_database_handler
from backend.shared_services.web_push_dispatch import (
    WebPushDispatchDraft,
    WebPushDispatchJob,
    WebPushScheduleReplaceResult,
)
from backend.shared_services.web_push_dispatch_store_mongodb import (
    MongoWebPushDispatchStoreMixin,
)
from backend.shared_services.web_push_dispatch_store_support import (
    WebPushDispatchStorageNames,
    iso_timestamp,
    job_from_mapping,
    normalize_datetime,
    sql_draft_params,
    sql_insert_draft,
    sql_text,
    sql_update_draft,
    utc_now,
)


class WebPushDispatchStore(MongoWebPushDispatchStoreMixin):
    """Persist leased dispatch jobs through the active database provider."""

    def __init__(
        self,
        names: WebPushDispatchStorageNames,
        *,
        handler: Any = None,
    ) -> None:
        """Create a provider-aware dispatch store.

        Args:
            names (WebPushDispatchStorageNames): App-owned identifiers.
            handler (Any): Optional provider handler override used by tests.

        Returns:
            None.

        Side Effects:
            Resolves the global database handler when no override is supplied.
        """
        self.names = names
        self.handler = handler if handler is not None else get_database_handler()

    async def replace_user_schedule(
        self,
        user_id: str,
        drafts: list[WebPushDispatchDraft],
        *,
        now: datetime,
    ) -> WebPushScheduleReplaceResult:
        """Replace one account's unleased scheduled horizon.

        Args:
            user_id (str): Authorized recipient account.
            drafts (list[WebPushDispatchDraft]): Complete desired horizon.
            now (datetime): UTC-aware replacement time.

        Returns:
            WebPushScheduleReplaceResult: Desired and obsolete-job counts.

        Raises:
            ValueError: When the active provider is unsupported.

        Side Effects:
            Removes obsolete unleased jobs and upserts desired occurrences.
        """
        provider = self._provider_name()
        if provider == "mongodb":
            return await self._replace_mongodb(user_id, drafts, now=now)
        if provider == "sql":
            return await self._replace_sql(user_id, drafts, now=now)
        if provider == "neo4j":
            return await asyncio.to_thread(
                self._replace_neo4j,
                user_id,
                drafts,
                now,
            )
        raise ValueError(f"Unsupported Web Push dispatch provider: {provider}")

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[WebPushDispatchJob]:
        """Lease one bounded due-job batch.

        Args:
            now (datetime): UTC-aware claim time.
            limit (int): Maximum jobs to claim.
            lease_seconds (int): Crash-recovery lease duration.

        Returns:
            list[WebPushDispatchJob]: Claimed jobs with lease tokens.

        Raises:
            ValueError: When the active provider is unsupported.

        Side Effects:
            Writes lease token and expiry to claimed provider records.
        """
        provider = self._provider_name()
        if provider == "mongodb":
            return await self._claim_mongodb(now, limit, lease_seconds)
        if provider == "sql":
            return await self._claim_sql(now, limit, lease_seconds)
        if provider == "neo4j":
            return await asyncio.to_thread(
                self._claim_neo4j,
                now,
                limit,
                lease_seconds,
            )
        raise ValueError(f"Unsupported Web Push dispatch provider: {provider}")

    async def complete(self, job: WebPushDispatchJob) -> bool:
        """Delete one successfully handled leased job.

        Args:
            job (WebPushDispatchJob): Claimed job and lease token.

        Returns:
            bool: True when this lease deleted the record.

        Side Effects:
            Deletes one provider record.
        """
        return await self._delete_leased(job)

    async def retry(
        self,
        job: WebPushDispatchJob,
        *,
        attempt_count: int,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> bool:
        """Release one lease with updated bounded retry metadata.

        Args:
            job (WebPushDispatchJob): Claimed job and lease token.
            attempt_count (int): Updated failure count.
            next_attempt_at (datetime): UTC-aware retry time.
            failure_code (str): Sanitized operational reason code.

        Returns:
            bool: True when this lease updated the record.

        Raises:
            ValueError: When the active provider is unsupported.

        Side Effects:
            Clears the lease and updates retry metadata.
        """
        provider = self._provider_name()
        if provider == "mongodb":
            return await self._retry_mongodb(
                job,
                attempt_count,
                next_attempt_at,
                failure_code,
            )
        if provider == "sql":
            return await self._retry_sql(
                job,
                attempt_count,
                next_attempt_at,
                failure_code,
            )
        if provider == "neo4j":
            return await asyncio.to_thread(
                self._retry_neo4j,
                job,
                attempt_count,
                next_attempt_at,
                failure_code,
            )
        raise ValueError(f"Unsupported Web Push dispatch provider: {provider}")

    async def discard(self, job: WebPushDispatchJob) -> bool:
        """Delete one expired or retry-exhausted leased job.

        Args:
            job (WebPushDispatchJob): Claimed job and lease token.

        Returns:
            bool: True when this lease deleted the record.

        Side Effects:
            Deletes one provider record.
        """
        return await self._delete_leased(job)

    def _provider_name(self) -> str:
        """Normalize the handler class to one provider family.

        Returns:
            str: ``mongodb``, ``sql``, ``neo4j``, or unknown class name.

        Side Effects:
            None.
        """
        handler_name = type(self.handler).__name__
        return {
            "MongoDBHandler": "mongodb",
            "SQLHandler": "sql",
            "Neo4jHandler": "neo4j",
        }.get(handler_name, handler_name)

    async def _replace_sql(
        self,
        user_id: str,
        drafts: list[WebPushDispatchDraft],
        *,
        now: datetime,
    ) -> WebPushScheduleReplaceResult:
        """Replace one SQL owner horizon transactionally.

        Args:
            user_id (str): Recipient account.
            drafts (list[WebPushDispatchDraft]): Desired occurrences.
            now (datetime): Replacement time.

        Returns:
            WebPushScheduleReplaceResult: Desired and removed counts.

        Side Effects:
            Deletes obsolete rows, upserts desired rows, and commits once.
        """
        table = self.names.sql_table
        desired = {draft.schedule_key: draft for draft in drafts}
        removed = 0
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                sql_text(
                    f"SELECT schedule_key FROM {table} "  # nosec B608
                    "WHERE user_id = :user_id "
                    "AND (lease_until IS NULL OR lease_until <= :now)"
                ),
                {"user_id": user_id, "now": now},
            )
            existing_keys = [
                str(row["schedule_key"]) for row in result.mappings().all()
            ]
            for schedule_key in existing_keys:
                if schedule_key not in desired:
                    removed += await self._delete_sql_key(
                        session,
                        user_id,
                        schedule_key,
                        now,
                    )
            for draft in drafts:
                await self._upsert_sql_draft(session, user_id, draft, now)
            await session.commit()
        return WebPushScheduleReplaceResult(len(drafts), removed)

    async def _delete_sql_key(
        self,
        session: Any,
        user_id: str,
        schedule_key: str,
        now: datetime,
    ) -> int:
        """Delete one obsolete unleased SQL occurrence.

        Args:
            session (Any): Active SQLAlchemy async session.
            user_id (str): Recipient account.
            schedule_key (str): Obsolete occurrence identity.
            now (datetime): Replacement time.

        Returns:
            int: Deleted row count.

        Side Effects:
            Deletes at most one SQL row.
        """
        result = await session.execute(
            sql_text(
                f"DELETE FROM {self.names.sql_table} "  # nosec B608
                "WHERE user_id = :user_id AND schedule_key = :schedule_key "
                "AND (lease_until IS NULL OR lease_until <= :now)"
            ),
            {"user_id": user_id, "schedule_key": schedule_key, "now": now},
        )
        return int(result.rowcount)

    async def _upsert_sql_draft(
        self,
        session: Any,
        user_id: str,
        draft: WebPushDispatchDraft,
        now: datetime,
    ) -> None:
        """Insert or reset one SQL occurrence.

        Args:
            session (Any): Active SQLAlchemy async session.
            user_id (str): Recipient account.
            draft (WebPushDispatchDraft): Desired occurrence.
            now (datetime): Replacement time.

        Returns:
            None.

        Side Effects:
            Inserts or updates one SQL row.
        """
        table = self.names.sql_table
        result = await session.execute(
            sql_text(
                f"SELECT job_id, lease_until FROM {table} "  # nosec B608
                "WHERE user_id = :user_id AND schedule_key = :schedule_key "
                "FOR UPDATE"
            ),
            {"user_id": user_id, "schedule_key": draft.schedule_key},
        )
        existing = result.mappings().one_or_none()
        if (
            existing
            and existing["lease_until"]
            and normalize_datetime(existing["lease_until"]) > now
        ):
            return
        job_id = existing["job_id"] if existing else None
        params = sql_draft_params(
            user_id,
            draft,
            now,
            job_id=str(job_id or uuid4()),
        )
        statement = sql_update_draft(table) if job_id else sql_insert_draft(table)
        await session.execute(sql_text(statement), params)

    async def _claim_sql(
        self,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[WebPushDispatchJob]:
        """Lease due SQL rows using transaction row locks.

        Args:
            now (datetime): Claim time.
            limit (int): Maximum claim count.
            lease_seconds (int): Lease duration.

        Returns:
            list[WebPushDispatchJob]: Claimed job snapshots.

        Side Effects:
            Locks, leases, and commits a bounded row batch.
        """
        table = self.names.sql_table
        token = str(uuid4())
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                sql_text(
                    "SELECT job_id, user_id, schedule_key, payload, due_at, "
                    f"expires_at, attempt_count FROM {table} "  # nosec B608
                    "WHERE due_at <= :now AND next_attempt_at <= :now "
                    "AND expires_at > :now "
                    "AND (lease_until IS NULL OR lease_until <= :now) "
                    "ORDER BY next_attempt_at ASC, due_at ASC "
                    "LIMIT :limit FOR UPDATE SKIP LOCKED"
                ),
                {"now": now, "limit": limit},
            )
            rows = result.mappings().all()
            for row in rows:
                await session.execute(
                    sql_text(
                        f"UPDATE {table} SET lease_token = :lease_token, "  # nosec B608
                        "lease_until = :lease_until, updated_at = :now "
                        "WHERE job_id = :job_id"
                    ),
                    {
                        "lease_token": token,
                        "lease_until": lease_until,
                        "now": now,
                        "job_id": row["job_id"],
                    },
                )
            await session.commit()
        return [job_from_mapping(row, lease_token=token) for row in rows]

    async def _retry_sql(
        self,
        job: WebPushDispatchJob,
        attempt_count: int,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> bool:
        """Release one SQL lease for retry.

        Args:
            job (WebPushDispatchJob): Claimed job.
            attempt_count (int): Updated failure count.
            next_attempt_at (datetime): Retry time.
            failure_code (str): Sanitized reason code.

        Returns:
            bool: True when this lease updated one row.

        Side Effects:
            Updates retry metadata, commits, and clears the lease.
        """
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                sql_text(
                    f"UPDATE {self.names.sql_table} SET "  # nosec B608
                    "attempt_count = :attempt_count, "
                    "next_attempt_at = :next_attempt_at, "
                    "last_failure_code = :failure_code, lease_token = NULL, "
                    "lease_until = NULL, updated_at = :updated_at "
                    "WHERE job_id = :job_id AND lease_token = :lease_token"
                ),
                {
                    "attempt_count": attempt_count,
                    "next_attempt_at": next_attempt_at,
                    "failure_code": failure_code,
                    "updated_at": utc_now(),
                    "job_id": job.job_id,
                    "lease_token": job.lease_token,
                },
            )
            await session.commit()
            return bool(result.rowcount)

    def _replace_neo4j(
        self,
        user_id: str,
        drafts: list[WebPushDispatchDraft],
        now: datetime,
    ) -> WebPushScheduleReplaceResult:
        """Replace one Neo4j owner horizon.

        Args:
            user_id (str): Recipient account.
            drafts (list[WebPushDispatchDraft]): Desired occurrences.
            now (datetime): Replacement time.

        Returns:
            WebPushScheduleReplaceResult: Desired and removed counts.

        Side Effects:
            Ensures a constraint, removes obsolete nodes, and merges desired.
        """
        label = self.names.neo4j_label
        now_text = iso_timestamp(now)
        desired_keys = [draft.schedule_key for draft in drafts]
        with self.handler.driver.session() as session:
            session.run(
                f"CREATE CONSTRAINT {self.names.neo4j_constraint} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE (n.user_id, n.schedule_key) IS UNIQUE"
            )
            record = session.run(
                f"""
                MATCH (j:{label} {{user_id: $user_id}})
                WHERE NOT j.schedule_key IN $desired_keys
                  AND (j.lease_until IS NULL OR j.lease_until <= $now)
                WITH collect(j) AS obsolete
                FOREACH (job IN obsolete | DELETE job)
                RETURN size(obsolete) AS removed
                """,
                user_id=user_id,
                desired_keys=desired_keys,
                now=now_text,
            ).single()
            for draft in drafts:
                self._upsert_neo4j_draft(session, user_id, draft, now_text)
        return WebPushScheduleReplaceResult(
            len(drafts),
            int(record["removed"] if record else 0),
        )

    def _upsert_neo4j_draft(
        self,
        session: Any,
        user_id: str,
        draft: WebPushDispatchDraft,
        now_text: str,
    ) -> None:
        """Merge and reset one Neo4j occurrence.

        Args:
            session (Any): Active Neo4j session.
            user_id (str): Recipient account.
            draft (WebPushDispatchDraft): Desired occurrence.
            now_text (str): Replacement timestamp.

        Returns:
            None.

        Side Effects:
            Creates or resets one dispatch node.
        """
        session.run(
            f"""
            MERGE (j:{self.names.neo4j_label} {{
                user_id: $user_id,
                schedule_key: $schedule_key
            }})
            ON CREATE SET j.job_id = $job_id, j.created_at = $now
            WITH j
            WHERE j.lease_until IS NULL OR j.lease_until <= $now
            SET j.payload = $payload,
                j.due_at = $due_at,
                j.expires_at = $expires_at,
                j.attempt_count = 0,
                j.next_attempt_at = $due_at,
                j.lease_token = null,
                j.lease_until = null,
                j.last_failure_code = null,
                j.updated_at = $now
            """,
            job_id=str(uuid4()),
            user_id=user_id,
            schedule_key=draft.schedule_key,
            payload=draft.payload,
            due_at=iso_timestamp(draft.due_at),
            expires_at=iso_timestamp(draft.expires_at),
            now=now_text,
        )

    def _claim_neo4j(
        self,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[WebPushDispatchJob]:
        """Lease one bounded due Neo4j batch.

        Args:
            now (datetime): Claim time.
            limit (int): Maximum claim count.
            lease_seconds (int): Lease duration.

        Returns:
            list[WebPushDispatchJob]: Claimed job snapshots.

        Side Effects:
            Writes one claim token to the selected nodes.
        """
        token = str(uuid4())
        with self.handler.driver.session() as session:
            records = session.run(
                f"""
                MATCH (j:{self.names.neo4j_label})
                WHERE j.due_at <= $now
                  AND j.next_attempt_at <= $now
                  AND j.expires_at > $now
                  AND (j.lease_until IS NULL OR j.lease_until <= $now)
                WITH j ORDER BY j.next_attempt_at ASC, j.due_at ASC
                LIMIT $limit
                SET j.lease_token = $lease_token,
                    j.lease_until = $lease_until,
                    j.updated_at = $now
                RETURN j.job_id AS job_id,
                       j.user_id AS user_id,
                       j.schedule_key AS schedule_key,
                       j.payload AS payload,
                       j.due_at AS due_at,
                       j.expires_at AS expires_at,
                       j.attempt_count AS attempt_count
                """,
                now=iso_timestamp(now),
                limit=limit,
                lease_token=token,
                lease_until=iso_timestamp(now + timedelta(seconds=lease_seconds)),
            )
            return [job_from_mapping(record, lease_token=token) for record in records]

    def _retry_neo4j(
        self,
        job: WebPushDispatchJob,
        attempt_count: int,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> bool:
        """Release one Neo4j lease for retry.

        Args:
            job (WebPushDispatchJob): Claimed job.
            attempt_count (int): Updated failure count.
            next_attempt_at (datetime): Retry time.
            failure_code (str): Sanitized reason code.

        Returns:
            bool: True when this lease updated one node.

        Side Effects:
            Updates retry metadata and clears the lease.
        """
        with self.handler.driver.session() as session:
            record = session.run(
                f"""
                MATCH (j:{self.names.neo4j_label} {{
                    job_id: $job_id,
                    lease_token: $lease_token
                }})
                SET j.attempt_count = $attempt_count,
                    j.next_attempt_at = $next_attempt_at,
                    j.last_failure_code = $failure_code,
                    j.lease_token = null,
                    j.lease_until = null,
                    j.updated_at = $updated_at
                RETURN count(j) AS updated
                """,
                job_id=job.job_id,
                lease_token=job.lease_token,
                attempt_count=attempt_count,
                next_attempt_at=iso_timestamp(next_attempt_at),
                failure_code=failure_code,
                updated_at=iso_timestamp(utc_now()),
            ).single()
        return bool(record and record["updated"])

    async def _delete_leased(self, job: WebPushDispatchJob) -> bool:
        """Delete one provider record only when its lease token still matches.

        Args:
            job (WebPushDispatchJob): Claimed job and lease token.

        Returns:
            bool: True when this lease deleted the record.

        Raises:
            ValueError: When the active provider is unsupported.

        Side Effects:
            Deletes at most one dispatch record.
        """
        provider = self._provider_name()
        if provider == "mongodb":
            collection = self.handler.database[self.names.mongo_collection]
            result = await collection.delete_one(
                {"job_id": job.job_id, "lease_token": job.lease_token}
            )
            return bool(result.deleted_count)
        if provider == "sql":
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(
                    sql_text(
                        f"DELETE FROM {self.names.sql_table} "  # nosec B608
                        "WHERE job_id = :job_id AND lease_token = :lease_token"
                    ),
                    {"job_id": job.job_id, "lease_token": job.lease_token},
                )
                await session.commit()
                return bool(result.rowcount)
        if provider == "neo4j":
            return await asyncio.to_thread(self._delete_leased_neo4j, job)
        raise ValueError(f"Unsupported Web Push dispatch provider: {provider}")

    def _delete_leased_neo4j(self, job: WebPushDispatchJob) -> bool:
        """Delete one matching leased Neo4j node.

        Args:
            job (WebPushDispatchJob): Claimed job and lease token.

        Returns:
            bool: True when a node was deleted.

        Side Effects:
            Deletes at most one Neo4j dispatch node.
        """
        with self.handler.driver.session() as session:
            record = session.run(
                f"""
                MATCH (j:{self.names.neo4j_label} {{
                    job_id: $job_id,
                    lease_token: $lease_token
                }})
                WITH collect(j) AS jobs
                FOREACH (job IN jobs | DELETE job)
                RETURN size(jobs) AS deleted
                """,
                job_id=job.job_id,
                lease_token=job.lease_token,
            ).single()
        return bool(record and record["deleted"])
