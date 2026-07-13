"""Unit coverage for durable Web Push retry policy and lifecycle polling."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from backend.shared_services.web_push_delivery import WebPushDeliveryReport
from backend.shared_services.web_push_dispatch import (
    WebPushDispatchBackgroundService,
    WebPushDispatchDraft,
    WebPushDispatchJob,
    WebPushDispatchPolicy,
    WebPushDispatchRunReport,
    WebPushDispatchWorker,
    WebPushScheduleReplaceResult,
)

_NOW = datetime(2026, 7, 13, 20, 0, tzinfo=timezone.utc)


def _job(
    suffix: str,
    *,
    payload: str | None = None,
    attempt_count: int = 0,
    expires_at: datetime | None = None,
) -> WebPushDispatchJob:
    """Build one deterministic leased dispatch job.

    Args:
        suffix (str): Job/schedule/payload behavior identifier.
        payload (str | None): Optional dispatcher behavior override.
        attempt_count (int): Completed failure count, defaulting to zero.
        expires_at (datetime | None): Optional terminal expiry override.

    Returns:
        WebPushDispatchJob: Deterministic leased job fixture.
    """
    return WebPushDispatchJob(
        job_id=f"job-{suffix}",
        user_id="user-a",
        schedule_key=f"schedule-{suffix}",
        payload=payload or suffix,
        due_at=_NOW - timedelta(minutes=1),
        expires_at=expires_at or _NOW + timedelta(hours=1),
        attempt_count=attempt_count,
        lease_token=f"lease-{suffix}",
    )


class _Repository:
    """Record worker transitions for a deterministic claimed batch."""

    def __init__(self, jobs: list[WebPushDispatchJob]) -> None:
        """Create a fake repository with preclaimed jobs.

        Args:
            jobs (list[WebPushDispatchJob]): Jobs returned by the next claim.

        Returns:
            None.
        """
        self.jobs = list(jobs)
        self.claim_args: tuple[datetime, int, int] | None = None
        self.completed: list[str] = []
        self.discarded: list[str] = []
        self.retried: list[tuple[str, int, datetime, str]] = []

    async def replace_user_schedule(
        self,
        user_id: str,
        drafts: list[WebPushDispatchDraft],
        *,
        now: datetime,
    ) -> WebPushScheduleReplaceResult:
        """Reject unused replacement calls in worker-only tests.

        Args:
            user_id (str): Recipient account.
            drafts (list[WebPushDispatchDraft]): Desired jobs.
            now (datetime): Replacement time.

        Returns:
            WebPushScheduleReplaceResult: Never returned.

        Raises:
            AssertionError: Always, because worker tests do not replace jobs.
        """
        raise AssertionError((user_id, drafts, now))

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[WebPushDispatchJob]:
        """Return the configured claimed jobs once.

        Args:
            now (datetime): Worker claim time.
            limit (int): Batch limit.
            lease_seconds (int): Lease duration.

        Returns:
            list[WebPushDispatchJob]: Configured jobs, then an empty list.

        Side Effects:
            Records claim bounds and consumes the configured list.
        """
        self.claim_args = (now, limit, lease_seconds)
        jobs, self.jobs = self.jobs[:limit], []
        return jobs

    async def complete(self, job: WebPushDispatchJob) -> bool:
        """Record successful completion.

        Args:
            job (WebPushDispatchJob): Completed leased job.

        Returns:
            bool: Always True.
        """
        self.completed.append(job.job_id)
        return True

    async def retry(
        self,
        job: WebPushDispatchJob,
        *,
        attempt_count: int,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> bool:
        """Record one retry transition.

        Args:
            job (WebPushDispatchJob): Failed leased job.
            attempt_count (int): Updated failure count.
            next_attempt_at (datetime): Retry time.
            failure_code (str): Sanitized reason code.

        Returns:
            bool: Always True.
        """
        self.retried.append((job.job_id, attempt_count, next_attempt_at, failure_code))
        return True

    async def discard(self, job: WebPushDispatchJob) -> bool:
        """Record one terminal discard.

        Args:
            job (WebPushDispatchJob): Expired/exhausted leased job.

        Returns:
            bool: Always True.
        """
        self.discarded.append(job.job_id)
        return True


class _Dispatcher:
    """Return payload-selected delivery outcomes without network calls."""

    def __init__(self) -> None:
        """Create an empty dispatch observation list.

        Returns:
            None.
        """
        self.calls: list[tuple[str, str]] = []

    async def __call__(
        self,
        user_id: str,
        payload: str,
    ) -> WebPushDeliveryReport:
        """Dispatch one fake payload behavior.

        Args:
            user_id (str): Recipient account.
            payload (str): Behavior selector.

        Returns:
            WebPushDeliveryReport: Accepted or transient-failure report.

        Raises:
            RuntimeError: For the ``exception`` behavior.
        """
        self.calls.append((user_id, payload))
        if payload == "exception":
            raise RuntimeError("private details must not persist")
        if payload == "transient":
            return WebPushDeliveryReport(1, 0, 0, 0, 1)
        return WebPushDeliveryReport(1, 1, 0, 0, 0)


def _policy(**overrides: int) -> WebPushDispatchPolicy:
    """Build deterministic bounded retry policy.

    Args:
        **overrides (int): Field overrides for the default test policy.

    Returns:
        WebPushDispatchPolicy: Validated policy fixture.
    """
    values = {
        "batch_size": 10,
        "lease_seconds": 60,
        "max_attempts": 3,
        "retry_base_seconds": 10,
        "retry_max_seconds": 40,
        **overrides,
    }
    return WebPushDispatchPolicy(**values)


def test_dispatch_policy_rejects_unbounded_configuration() -> None:
    """Ensure unsafe batch, lease, attempt, and retry values fail closed.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="batch size"):
        WebPushDispatchPolicy(batch_size=0)
    with pytest.raises(ValueError, match="lease"):
        WebPushDispatchPolicy(lease_seconds=10)
    with pytest.raises(ValueError, match="attempts"):
        WebPushDispatchPolicy(max_attempts=13)
    with pytest.raises(ValueError, match="retry maximum"):
        WebPushDispatchPolicy(retry_base_seconds=30, retry_max_seconds=20)


def test_worker_completes_retries_and_discards_with_safe_backoff() -> None:
    """Ensure one poll distinguishes accepted, transient, and terminal work.

    Returns:
        None.
    """
    repository = _Repository(
        [
            _job("accepted"),
            _job("transient"),
            _job("exception", attempt_count=1),
            _job("expired", expires_at=_NOW),
            _job("exhausted", payload="exception", attempt_count=2),
        ]
    )
    dispatcher = _Dispatcher()
    worker = WebPushDispatchWorker(
        repository,
        dispatcher,
        _policy(),
        clock=lambda: _NOW,
    )

    report = asyncio.run(worker.run_once())

    assert report == WebPushDispatchRunReport(
        claimed=5,
        completed=1,
        retried=2,
        discarded=2,
        delivered=1,
        failed=1,
    )
    assert repository.claim_args == (_NOW, 10, 60)
    assert repository.completed == ["job-accepted"]
    assert repository.discarded == ["job-expired", "job-exhausted"]
    assert repository.retried == [
        ("job-transient", 1, _NOW + timedelta(seconds=10), "transient_delivery"),
        ("job-exception", 2, _NOW + timedelta(seconds=20), "RuntimeError"),
    ]
    assert dispatcher.calls == [
        ("user-a", "accepted"),
        ("user-a", "transient"),
        ("user-a", "exception"),
        ("user-a", "exception"),
    ]


def test_disabled_background_service_never_resolves_worker() -> None:
    """Ensure disabled deployments perform no provider or secret resolution.

    Returns:
        None.
    """
    calls = 0

    def factory() -> WebPushDispatchWorker:
        """Record an unexpected worker resolution.

        Returns:
            WebPushDispatchWorker: Never returned.

        Raises:
            AssertionError: Always when disabled startup is incorrect.
        """
        nonlocal calls
        calls += 1
        raise AssertionError("disabled service resolved worker")

    service = WebPushDispatchBackgroundService(
        "dispatch",
        enabled=False,
        poll_seconds=5,
        worker_factory=factory,
    )

    asyncio.run(service.start())
    asyncio.run(service.stop())

    assert calls == 0
    assert service.snapshot()["status"] == "disabled"


def test_enabled_background_service_polls_and_stops_cleanly() -> None:
    """Ensure lifecycle start performs a poll and shutdown wakes immediately.

    Returns:
        None.
    """
    repository = _Repository([])
    worker = WebPushDispatchWorker(
        repository,
        _Dispatcher(),
        _policy(),
        clock=lambda: _NOW,
    )
    service = WebPushDispatchBackgroundService(
        "dispatch",
        enabled=True,
        poll_seconds=30,
        worker_factory=lambda: worker,
    )

    async def exercise() -> None:
        """Start, yield until one poll, and stop the service.

        Returns:
            None.

        Side Effects:
            Runs the background service in the current event loop.
        """
        await service.start()
        for _ in range(20):
            if int(service.snapshot()["polls"]) >= 1:
                break
            await asyncio.sleep(0)
        await service.stop()

    asyncio.run(exercise())

    snapshot = service.snapshot()
    assert snapshot["status"] == "stopped"
    assert snapshot["polls"] == 1
    assert snapshot["last_claimed"] == 0
