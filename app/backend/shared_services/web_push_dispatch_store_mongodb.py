"""MongoDB adapter methods for the durable Web Push dispatch store.

The mixin keeps MongoDB index, replacement, atomic claim, and retry mechanics
separate from the provider-neutral facade. Replacement never mutates an active
lease, preserving an in-flight worker's ownership token.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.shared_services.web_push_dispatch import (
    WebPushDispatchDraft,
    WebPushDispatchJob,
    WebPushScheduleReplaceResult,
)
from backend.shared_services.web_push_dispatch_store_support import (
    WebPushDispatchStorageNames,
    iso_timestamp,
    job_from_mapping,
    utc_now,
)


class MongoWebPushDispatchStoreMixin:
    """Provide MongoDB persistence operations to the dispatch-store facade.

    Attributes:
        names (WebPushDispatchStorageNames): Validated provider identifiers.
        handler (Any): Active MongoDB database handler.
    """

    names: WebPushDispatchStorageNames
    handler: Any

    async def _replace_mongodb(
        self,
        user_id: str,
        drafts: list[WebPushDispatchDraft],
        *,
        now: datetime,
    ) -> WebPushScheduleReplaceResult:
        """Replace one MongoDB owner horizon without disturbing active leases.

        Args:
            user_id (str): Recipient account.
            drafts (list[WebPushDispatchDraft]): Desired occurrences.
            now (datetime): Replacement time.

        Returns:
            WebPushScheduleReplaceResult: Desired and removed counts.

        Side Effects:
            Creates indexes, deletes obsolete jobs, and upserts desired jobs.
        """
        collection = self.handler.database[self.names.mongo_collection]
        await self._ensure_mongodb_indexes(collection)
        now_text = iso_timestamp(now)
        desired_keys = [draft.schedule_key for draft in drafts]
        obsolete = {"user_id": user_id, **_available_lease_filter(now_text)}
        if desired_keys:
            obsolete["schedule_key"] = {"$nin": desired_keys}
        removed = await collection.delete_many(obsolete)
        for draft in drafts:
            await self._upsert_mongodb_draft(collection, user_id, draft, now)
        return WebPushScheduleReplaceResult(
            scheduled=len(drafts),
            removed=int(removed.deleted_count),
        )

    async def _ensure_mongodb_indexes(self, collection: Any) -> None:
        """Ensure MongoDB uniqueness and due-claim indexes.

        Args:
            collection (Any): Motor collection facade.

        Returns:
            None.

        Side Effects:
            Creates two idempotent collection indexes.
        """
        await collection.create_index(
            [("user_id", 1), ("schedule_key", 1)],
            unique=True,
            name=f"idx_{self.names.mongo_collection}_owner_key",
        )
        await collection.create_index(
            [("next_attempt_at", 1), ("due_at", 1), ("lease_until", 1)],
            name=f"idx_{self.names.mongo_collection}_due_lease",
        )

    async def _upsert_mongodb_draft(
        self,
        collection: Any,
        user_id: str,
        draft: WebPushDispatchDraft,
        now: datetime,
    ) -> None:
        """Insert or reset one unleased MongoDB occurrence.

        Args:
            collection (Any): Motor collection facade.
            user_id (str): Recipient account.
            draft (WebPushDispatchDraft): Desired occurrence.
            now (datetime): UTC replacement timestamp.

        Returns:
            None.

        Side Effects:
            Inserts a job or resets it only while no worker owns its lease.
        """
        now_text = iso_timestamp(now)
        identity = {"user_id": user_id, "schedule_key": draft.schedule_key}
        mutable_identity = {**identity, **_available_lease_filter(now_text)}
        values = _mongodb_draft_values(draft, now_text)
        result = await collection.update_one(
            mutable_identity,
            {"$set": values},
            upsert=False,
        )
        if result.matched_count:
            return

        # An existing row is actively leased; leave its worker snapshot intact.
        if await collection.find_one(identity, {"_id": 1}):
            return

        try:
            await collection.insert_one(
                {
                    **identity,
                    **values,
                    "job_id": str(uuid4()),
                    "created_at": now_text,
                }
            )
        except Exception:
            # A concurrent scheduler may have won the unique owner/key race.
            # Confirm that durable state exists before containing the error.
            if await collection.find_one(identity, {"_id": 1}):
                return
            raise

    async def _claim_mongodb(
        self,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[WebPushDispatchJob]:
        """Atomically lease due MongoDB documents one at a time.

        Args:
            now (datetime): Claim time.
            limit (int): Maximum claim count.
            lease_seconds (int): Lease duration.

        Returns:
            list[WebPushDispatchJob]: Claimed job snapshots.

        Side Effects:
            Writes unique lease tokens and expiries.
        """
        # Import the optional provider dependency only for an active Mongo app.
        from pymongo import ReturnDocument

        collection = self.handler.database[self.names.mongo_collection]
        await self._ensure_mongodb_indexes(collection)
        claimed: list[WebPushDispatchJob] = []
        for _ in range(limit):
            token = str(uuid4())
            document = await collection.find_one_and_update(
                _due_filter(iso_timestamp(now)),
                {
                    "$set": {
                        "lease_token": token,
                        "lease_until": iso_timestamp(
                            now + timedelta(seconds=lease_seconds)
                        ),
                        "updated_at": iso_timestamp(now),
                    }
                },
                sort=[("next_attempt_at", 1), ("due_at", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if document is None:
                break
            claimed.append(job_from_mapping(document, lease_token=token))
        return claimed

    async def _retry_mongodb(
        self,
        job: WebPushDispatchJob,
        attempt_count: int,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> bool:
        """Release one MongoDB lease for retry.

        Args:
            job (WebPushDispatchJob): Claimed job.
            attempt_count (int): Updated failure count.
            next_attempt_at (datetime): Retry time.
            failure_code (str): Sanitized reason code.

        Returns:
            bool: True when this lease updated one document.

        Side Effects:
            Updates retry metadata and clears the lease.
        """
        collection = self.handler.database[self.names.mongo_collection]
        result = await collection.update_one(
            {"job_id": job.job_id, "lease_token": job.lease_token},
            {
                "$set": {
                    "attempt_count": attempt_count,
                    "next_attempt_at": iso_timestamp(next_attempt_at),
                    "last_failure_code": failure_code,
                    "lease_token": None,
                    "lease_until": None,
                    "updated_at": iso_timestamp(utc_now()),
                }
            },
        )
        return bool(result.modified_count)


def _mongodb_draft_values(
    draft: WebPushDispatchDraft,
    now_text: str,
) -> dict[str, Any]:
    """Build reset values for one MongoDB dispatch occurrence.

    Args:
        draft (WebPushDispatchDraft): Desired occurrence.
        now_text (str): UTC replacement timestamp.

    Returns:
        dict[str, Any]: Mutable job values without identity fields.
    """
    return {
        "payload": draft.payload,
        "due_at": iso_timestamp(draft.due_at),
        "expires_at": iso_timestamp(draft.expires_at),
        "attempt_count": 0,
        "next_attempt_at": iso_timestamp(draft.due_at),
        "lease_token": None,
        "lease_until": None,
        "last_failure_code": None,
        "updated_at": now_text,
    }


def _available_lease_filter(now_text: str) -> dict[str, Any]:
    """Return a MongoDB filter for absent or elapsed leases.

    Args:
        now_text (str): UTC ISO timestamp.

    Returns:
        dict[str, Any]: MongoDB ``$or`` lease filter.
    """
    return {
        "$or": [
            {"lease_until": None},
            {"lease_until": {"$lte": now_text}},
        ]
    }


def _due_filter(now_text: str) -> dict[str, Any]:
    """Return the MongoDB due/non-expired/available claim filter.

    Args:
        now_text (str): UTC ISO claim timestamp.

    Returns:
        dict[str, Any]: MongoDB claim filter.
    """
    return {
        "due_at": {"$lte": now_text},
        "next_attempt_at": {"$lte": now_text},
        "expires_at": {"$gt": now_text},
        **_available_lease_filter(now_text),
    }
