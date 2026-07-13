"""Durable Web Push dispatch policy, retry processing, and task lifecycle.

The module is product-neutral: backend apps provide opaque validated payloads,
provider storage, and a delivery callback. Jobs use expiring leases for bounded
multi-worker recovery. Delivery remains at-least-once across process crashes,
so app payloads should use stable browser tags when duplicate suppression is
important.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Awaitable, Callable, Protocol

from backend.observability import log_event
from backend.shared_services.web_push_delivery_types import WebPushDeliveryReport

logger = logging.getLogger("backend.web_push_dispatch")


@dataclass(frozen=True)
class WebPushDispatchDraft:
    """Represent one app-validated future delivery to persist.

    Attributes:
        schedule_key (str): Stable owner-scoped occurrence identity.
        payload (str): Opaque app-validated dispatch command.
        due_at (datetime): UTC-aware earliest delivery time.
        expires_at (datetime): UTC-aware terminal expiry time.
    """

    schedule_key: str
    payload: str
    due_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class WebPushDispatchJob:
    """Represent one leased durable delivery attempt.

    Attributes:
        job_id (str): Provider-independent job identity.
        user_id (str): Authorized account recipient.
        schedule_key (str): Stable app occurrence identity.
        payload (str): Opaque app-owned dispatch command.
        due_at (datetime): Earliest delivery time.
        expires_at (datetime): Time after which delivery is discarded.
        attempt_count (int): Completed retryable failures before this lease.
        lease_token (str): Claim token required for state transitions.
    """

    job_id: str
    user_id: str
    schedule_key: str
    payload: str
    due_at: datetime
    expires_at: datetime
    attempt_count: int
    lease_token: str


@dataclass(frozen=True)
class WebPushScheduleReplaceResult:
    """Summarize one account schedule replacement.

    Attributes:
        scheduled (int): Desired occurrences stored after replacement.
        removed (int): Obsolete unleased occurrences removed.
    """

    scheduled: int
    removed: int


class WebPushDispatchRepository(Protocol):
    """Describe persistence required by the reusable dispatch worker."""

    async def replace_user_schedule(
        self,
        user_id: str,
        drafts: list[WebPushDispatchDraft],
        *,
        now: datetime,
    ) -> WebPushScheduleReplaceResult:
        """Replace one account's unleased future occurrences.

        Args:
            user_id (str): Authorized recipient account.
            drafts (list[WebPushDispatchDraft]): Complete desired horizon.
            now (datetime): UTC-aware replacement timestamp.

        Returns:
            WebPushScheduleReplaceResult: Stored and removed counts.
        """
        ...

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[WebPushDispatchJob]:
        """Lease due, non-expired jobs for one worker pass.

        Args:
            now (datetime): UTC-aware claim time.
            limit (int): Maximum jobs to claim.
            lease_seconds (int): Crash-recovery lease duration.

        Returns:
            list[WebPushDispatchJob]: Claimed jobs with transition tokens.
        """
        ...

    async def complete(self, job: WebPushDispatchJob) -> bool:
        """Delete one successfully delivered leased job.

        Args:
            job (WebPushDispatchJob): Leased job and claim token.

        Returns:
            bool: True when this lease completed the job.
        """
        ...

    async def retry(
        self,
        job: WebPushDispatchJob,
        *,
        attempt_count: int,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> bool:
        """Release one leased job for a bounded later attempt.

        Args:
            job (WebPushDispatchJob): Leased job and claim token.
            attempt_count (int): Updated completed-failure count.
            next_attempt_at (datetime): UTC-aware retry time.
            failure_code (str): Privacy-safe bounded reason code.

        Returns:
            bool: True when this lease updated the job.
        """
        ...

    async def discard(self, job: WebPushDispatchJob) -> bool:
        """Delete one expired or retry-exhausted leased job.

        Args:
            job (WebPushDispatchJob): Leased job and claim token.

        Returns:
            bool: True when this lease discarded the job.
        """
        ...


@dataclass(frozen=True)
class WebPushDispatchPolicy:
    """Define bounded leasing, batching, and retry behavior.

    Attributes:
        batch_size (int): Maximum jobs claimed per poll.
        lease_seconds (int): Recovery lease duration.
        max_attempts (int): Retryable failures allowed before discard.
        retry_base_seconds (int): Initial exponential-backoff delay.
        retry_max_seconds (int): Maximum exponential-backoff delay.
    """

    batch_size: int = 25
    lease_seconds: int = 120
    max_attempts: int = 6
    retry_base_seconds: int = 30
    retry_max_seconds: int = 3600

    def __post_init__(self) -> None:
        """Reject unsafe dispatch bounds.

        Returns:
            None.

        Raises:
            ValueError: When batch, lease, attempt, or retry bounds are unsafe.

        Side Effects:
            None.
        """
        if not 1 <= self.batch_size <= 100:
            raise ValueError("Web Push dispatch batch size must be between 1 and 100.")
        if not 30 <= self.lease_seconds <= 900:
            raise ValueError("Web Push dispatch lease must be between 30 and 900s.")
        if not 1 <= self.max_attempts <= 12:
            raise ValueError("Web Push dispatch attempts must be between 1 and 12.")
        if not 1 <= self.retry_base_seconds <= 3600:
            raise ValueError("Web Push retry base must be between 1 and 3600s.")
        if not self.retry_base_seconds <= self.retry_max_seconds <= 86_400:
            raise ValueError("Web Push retry maximum must bound the base and one day.")


@dataclass(frozen=True)
class WebPushDispatchRunReport:
    """Summarize one worker poll without user or payload data.

    Attributes:
        claimed (int): Jobs leased for the pass.
        completed (int): Jobs deleted after accepted/stale delivery handling.
        retried (int): Jobs released with bounded backoff.
        discarded (int): Expired or retry-exhausted jobs deleted.
        delivered (int): Push-service acceptances across completed attempts.
        failed (int): Transient endpoint failures reported by delivery.
    """

    claimed: int = 0
    completed: int = 0
    retried: int = 0
    discarded: int = 0
    delivered: int = 0
    failed: int = 0


WebPushDispatchCallback = Callable[[str, str], Awaitable[WebPushDeliveryReport]]


class WebPushDispatchWorker:
    """Process leased dispatch jobs with bounded retry and expiry policy."""

    def __init__(
        self,
        repository: WebPushDispatchRepository,
        dispatcher: WebPushDispatchCallback,
        policy: WebPushDispatchPolicy,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create a worker over app-neutral persistence and delivery edges.

        Args:
            repository (WebPushDispatchRepository): Durable leased job store.
            dispatcher (WebPushDispatchCallback): App-owned payload dispatcher.
            policy (WebPushDispatchPolicy): Batch/lease/retry bounds.
            clock (Callable[[], datetime] | None): Optional UTC clock for tests.

        Returns:
            None.

        Side Effects:
            None.
        """
        self.repository = repository
        self.dispatcher = dispatcher
        self.policy = policy
        self._clock = clock or _utc_now

    async def run_once(self) -> WebPushDispatchRunReport:
        """Claim and process one bounded due-job batch.

        Returns:
            WebPushDispatchRunReport: Privacy-safe aggregate poll result.

        Side Effects:
            Leases jobs, performs encrypted delivery, and completes, retries,
            or discards durable records.
        """
        now = _require_aware(self._clock(), field_name="worker clock")
        jobs = await self.repository.claim_due(
            now=now,
            limit=self.policy.batch_size,
            lease_seconds=self.policy.lease_seconds,
        )
        counts = _MutableRunCounts(claimed=len(jobs))
        for job in jobs:
            await self._process_job(job, now, counts)
        return counts.freeze()

    async def _process_job(
        self,
        job: WebPushDispatchJob,
        now: datetime,
        counts: "_MutableRunCounts",
    ) -> None:
        """Process one lease and update aggregate counts.

        Args:
            job (WebPushDispatchJob): Claimed durable job.
            now (datetime): Poll timestamp used for expiry/backoff.
            counts (_MutableRunCounts): Mutable aggregate accumulator.

        Returns:
            None.

        Side Effects:
            Delivers one app payload and mutates its durable job state.
        """
        if job.expires_at <= now:
            counts.discarded += int(await self.repository.discard(job))
            return
        try:
            delivery = await self.dispatcher(job.user_id, job.payload)
        except Exception as exc:
            await self._retry_or_discard(job, now, type(exc).__name__, counts)
            return
        counts.delivered += delivery.delivered
        counts.failed += delivery.failed
        if delivery.failed:
            await self._retry_or_discard(job, now, "transient_delivery", counts)
            return
        counts.completed += int(await self.repository.complete(job))

    async def _retry_or_discard(
        self,
        job: WebPushDispatchJob,
        now: datetime,
        failure_code: str,
        counts: "_MutableRunCounts",
    ) -> None:
        """Apply retry limit, expiry, and capped exponential backoff.

        Args:
            job (WebPushDispatchJob): Failed leased job.
            now (datetime): Poll timestamp.
            failure_code (str): Safe exception type or delivery reason.
            counts (_MutableRunCounts): Mutable aggregate accumulator.

        Returns:
            None.

        Side Effects:
            Releases the lease for retry or deletes the exhausted job.
        """
        attempt_count = job.attempt_count + 1
        delay = min(
            self.policy.retry_base_seconds * (2 ** (attempt_count - 1)),
            self.policy.retry_max_seconds,
        )
        next_attempt_at = now + timedelta(seconds=delay)
        if (
            attempt_count >= self.policy.max_attempts
            or next_attempt_at >= job.expires_at
        ):
            counts.discarded += int(await self.repository.discard(job))
            return
        safe_code = _safe_failure_code(failure_code)
        counts.retried += int(
            await self.repository.retry(
                job,
                attempt_count=attempt_count,
                next_attempt_at=next_attempt_at,
                failure_code=safe_code,
            )
        )


class WebPushDispatchBackgroundService:
    """Poll one dispatch worker under selected-app lifespan ownership."""

    def __init__(
        self,
        name: str,
        *,
        enabled: bool,
        poll_seconds: float,
        worker_factory: Callable[[], WebPushDispatchWorker],
    ) -> None:
        """Create a disabled or lazily configured dispatch loop.

        Args:
            name (str): App-unique health snapshot key.
            enabled (bool): Whether startup should validate/create the worker.
            poll_seconds (float): Delay between completed polls.
            worker_factory (Callable[[], WebPushDispatchWorker]): Deferred
                provider/secret-aware worker factory.

        Returns:
            None.

        Raises:
            ValueError: When the name or poll interval is unsafe.

        Side Effects:
            None.
        """
        if not name or len(name) > 80:
            raise ValueError("Background service name must be non-empty and bounded.")
        if not 1 <= poll_seconds <= 300:
            raise ValueError("Web Push dispatch poll interval must be 1-300s.")
        self._name = name
        self.enabled = enabled
        self.poll_seconds = poll_seconds
        self._worker_factory = worker_factory
        self._worker: WebPushDispatchWorker | None = None
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._status = "disabled" if not enabled else "created"
        self._polls = 0
        self._last_report = WebPushDispatchRunReport()
        self._last_error_code: str | None = None

    @property
    def name(self) -> str:
        """Return the stable health-diagnostic service name.

        Returns:
            str: App-owned dispatch service name.
        """
        return self._name

    async def start(self) -> None:
        """Validate enabled configuration and start the poll task.

        Returns:
            None.

        Raises:
            Exception: Propagates enabled worker configuration failures.

        Side Effects:
            Creates one asynchronous polling task when enabled.
        """
        if not self.enabled:
            return
        if self._task is not None:
            return
        self._worker = self._worker_factory()
        self._stop_event.clear()
        self._status = "running"
        self._task = asyncio.create_task(
            self._run_loop(),
            name=f"background:{self.name}",
        )

    async def stop(self) -> None:
        """Signal and await the active poll task.

        Returns:
            None.

        Side Effects:
            Stops the owned task and publishes a stopped health state.
        """
        task = self._task
        if task is None:
            return
        self._stop_event.set()
        await task
        self._task = None
        self._status = "stopped"

    def snapshot(self) -> dict[str, object]:
        """Return privacy-safe loop status and latest aggregate counts.

        Returns:
            dict[str, object]: Enabled/status/poll/count/error-code metadata.

        Side Effects:
            None.
        """
        return {
            "enabled": self.enabled,
            "status": self._status,
            "polls": self._polls,
            "last_claimed": self._last_report.claimed,
            "last_completed": self._last_report.completed,
            "last_retried": self._last_report.retried,
            "last_discarded": self._last_report.discarded,
            "last_error_code": self._last_error_code,
        }

    async def _run_loop(self) -> None:
        """Poll until shutdown while containing per-pass failures.

        Returns:
            None.

        Raises:
            RuntimeError: When lifecycle startup failed to assign a worker.

        Side Effects:
            Runs durable dispatch polls and emits aggregate-only events.
        """
        worker = self._worker
        if worker is None:
            raise RuntimeError("Web Push dispatch loop requires a configured worker.")
        while not self._stop_event.is_set():
            await self._run_poll(worker)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.poll_seconds,
                )
            except TimeoutError:
                continue

    async def _run_poll(self, worker: WebPushDispatchWorker) -> None:
        """Run one contained poll and update safe health state.

        Args:
            worker (WebPushDispatchWorker): Configured durable worker.

        Returns:
            None.

        Side Effects:
            Mutates health counters and emits no user/payload metadata.
        """
        try:
            report = await worker.run_once()
            self._last_report = report
            self._last_error_code = None
            self._polls += 1
            log_event(
                logger,
                logging.INFO,
                "web_push.dispatch.poll",
                service=self.name,
                claimed=report.claimed,
                completed=report.completed,
                retried=report.retried,
                discarded=report.discarded,
            )
        except Exception as exc:
            self._last_error_code = type(exc).__name__
            self._polls += 1
            log_event(
                logger,
                logging.ERROR,
                "web_push.dispatch.poll_failed",
                service=self.name,
                error_code=self._last_error_code,
            )


@dataclass
class _MutableRunCounts:
    """Accumulate one dispatch poll before returning an immutable report."""

    claimed: int = 0
    completed: int = 0
    retried: int = 0
    discarded: int = 0
    delivered: int = 0
    failed: int = 0

    def freeze(self) -> WebPushDispatchRunReport:
        """Return the immutable aggregate snapshot.

        Returns:
            WebPushDispatchRunReport: Current poll counts.
        """
        return WebPushDispatchRunReport(
            claimed=self.claimed,
            completed=self.completed,
            retried=self.retried,
            discarded=self.discarded,
            delivered=self.delivered,
            failed=self.failed,
        )


def _safe_failure_code(value: str) -> str:
    """Return a bounded alphanumeric operational reason code.

    Args:
        value (str): Exception type or internal delivery reason.

    Returns:
        str: Sanitized code with no error message or payload content.
    """
    safe = "".join(
        character for character in value if character.isalnum() or character == "_"
    )
    return (safe or "dispatch_failure")[:64]


def _require_aware(value: datetime, *, field_name: str) -> datetime:
    """Normalize one timezone-aware timestamp to UTC.

    Args:
        value (datetime): Candidate timestamp.
        field_name (str): Safe validation label.

    Returns:
        datetime: UTC-normalized timestamp.

    Raises:
        ValueError: When the timestamp lacks timezone information.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    Returns:
        datetime: Current UTC time.
    """
    return datetime.now(timezone.utc)
