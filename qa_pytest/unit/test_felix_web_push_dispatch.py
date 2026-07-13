"""Unit coverage for Felix fixed-kind scheduling and authenticated routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json

from fastapi import HTTPException
import pytest
from pydantic import ValidationError

from apps.felix.routes import web_push
from apps.felix.schemas.web_push_dispatch import FelixWebPushScheduleReplaceRequest
from apps.felix.services.web_push_dispatch_service import (
    FelixWebPushDispatchService,
    FelixWebPushDispatchUnavailable,
    FelixWebPushScheduledOccurrence,
)
from apps.felix.services.web_push_service import FelixWebPushMessage
from backend.shared_services.web_push_delivery import WebPushDeliveryReport
from backend.shared_services.web_push_dispatch import (
    WebPushDispatchDraft,
    WebPushScheduleReplaceResult,
)

_NOW = datetime(2026, 7, 13, 20, 0, tzinfo=timezone.utc)


class _Store:
    """Capture one account-owned rolling schedule replacement."""

    def __init__(self) -> None:
        """Create an empty replacement observation.

        Returns:
            None.
        """
        self.user_id: str | None = None
        self.drafts: list[WebPushDispatchDraft] = []
        self.now: datetime | None = None

    async def replace_user_schedule(
        self,
        user_id: str,
        drafts: list[WebPushDispatchDraft],
        *,
        now: datetime,
    ) -> WebPushScheduleReplaceResult:
        """Record one full desired horizon.

        Args:
            user_id (str): Recipient account.
            drafts (list[WebPushDispatchDraft]): Desired durable jobs.
            now (datetime): Replacement timestamp.

        Returns:
            WebPushScheduleReplaceResult: Deterministic count result.

        Side Effects:
            Stores owner, drafts, and timestamp for assertions.
        """
        self.user_id = user_id
        self.drafts = list(drafts)
        self.now = now
        return WebPushScheduleReplaceResult(len(drafts), 2)


class _Delivery:
    """Capture one rendered Felix message without network delivery."""

    def __init__(self) -> None:
        """Create empty delivery observations.

        Returns:
            None.
        """
        self.user_id: str | None = None
        self.message: FelixWebPushMessage | None = None

    async def deliver(
        self,
        user_id: str,
        message: FelixWebPushMessage,
    ) -> WebPushDeliveryReport:
        """Record one rendered account delivery.

        Args:
            user_id (str): Recipient account.
            message (FelixWebPushMessage): Fixed backend-rendered message.

        Returns:
            WebPushDeliveryReport: One accepted fake delivery.

        Side Effects:
            Stores the owner and message for assertions.
        """
        self.user_id = user_id
        self.message = message
        return WebPushDeliveryReport(1, 1, 0, 0, 0)


def _occurrence(
    *,
    key: str = "checkin-evening-2026-07-14",
    kind: str = "checkin",
    due_at: datetime | None = None,
    locale: str = "de",
) -> FelixWebPushScheduledOccurrence:
    """Build one deterministic Felix occurrence.

    Args:
        key (str): Stable occurrence identity.
        kind (str): Fixed backend template key.
        due_at (datetime | None): Optional delivery-time override.
        locale (str): Supported backend copy locale.

    Returns:
        FelixWebPushScheduledOccurrence: Test occurrence.
    """
    return FelixWebPushScheduledOccurrence(
        schedule_key=key,
        kind=kind,
        due_at=due_at or _NOW + timedelta(hours=1),
        locale=locale,
    )


def _service(
    store: _Store | None = None,
    *,
    enabled: bool = True,
    delivery: _Delivery | None = None,
) -> FelixWebPushDispatchService:
    """Build a deterministic Felix dispatch service.

    Args:
        store (_Store | None): Optional fake store.
        enabled (bool): Deployment enablement result.
        delivery (_Delivery | None): Optional fake encrypted delivery edge.

    Returns:
        FelixWebPushDispatchService: Configured service under test.
    """
    return FelixWebPushDispatchService(
        store=store or _Store(),  # type: ignore[arg-type]
        web_push_service=delivery or _Delivery(),  # type: ignore[arg-type]
        enabled_loader=lambda: enabled,
        clock=lambda: _NOW,
    )


def test_schedule_schema_forbids_visible_copy_routes_and_naive_times() -> None:
    """Ensure callers cannot turn scheduling into arbitrary message sending.

    Returns:
        None.
    """
    with pytest.raises(ValidationError, match="Extra inputs"):
        FelixWebPushScheduleReplaceRequest.model_validate(
            {
                "occurrences": [
                    {
                        "scheduleKey": "checkin-1",
                        "kind": "checkin",
                        "dueAt": "2026-07-14T20:00:00Z",
                        "locale": "de",
                        "title": "Caller supplied",
                        "route": "https://evil.test",
                    }
                ]
            }
        )
    with pytest.raises(ValidationError, match="timezone"):
        FelixWebPushScheduleReplaceRequest.model_validate(
            {
                "occurrences": [
                    {
                        "scheduleKey": "checkin-1",
                        "kind": "checkin",
                        "dueAt": "2026-07-14T20:00:00",
                    }
                ]
            }
        )


def test_schedule_replacement_persists_only_fixed_command_metadata() -> None:
    """Ensure validated occurrences become bounded opaque durable commands.

    Returns:
        None.
    """
    store = _Store()
    service = _service(store)

    result = asyncio.run(
        service.replace_schedule(
            "user-a",
            [_occurrence(kind="breathing", locale="en")],
        )
    )

    assert result == WebPushScheduleReplaceResult(scheduled=1, removed=2)
    assert store.user_id == "user-a"
    assert store.now == _NOW
    assert len(store.drafts) == 1
    draft = store.drafts[0]
    assert json.loads(draft.payload) == {"kind": "breathing", "locale": "en"}
    assert draft.due_at == _NOW + timedelta(hours=1)
    assert draft.expires_at == draft.due_at + timedelta(days=1)
    assert "title" not in draft.payload
    assert "route" not in draft.payload


def test_schedule_replacement_rejects_disabled_duplicate_and_unsafe_horizon() -> None:
    """Ensure enablement, idempotency keys, and rolling horizon fail closed.

    Returns:
        None.
    """
    with pytest.raises(FelixWebPushDispatchUnavailable):
        asyncio.run(_service(enabled=False).replace_schedule("user-a", []))
    with pytest.raises(ValueError, match="unique"):
        asyncio.run(
            _service().replace_schedule(
                "user-a",
                [_occurrence(), _occurrence()],
            )
        )
    with pytest.raises(ValueError, match="too soon"):
        asyncio.run(
            _service().replace_schedule(
                "user-a",
                [_occurrence(due_at=_NOW + timedelta(seconds=20))],
            )
        )
    with pytest.raises(ValueError, match="rolling horizon"):
        asyncio.run(
            _service().replace_schedule(
                "user-a",
                [_occurrence(due_at=_NOW + timedelta(days=9))],
            )
        )
    with pytest.raises(ValueError, match="key is invalid"):
        asyncio.run(
            _service().replace_schedule(
                "user-a",
                [_occurrence(key="unsafe/key")],
            )
        )
    with pytest.raises(ValueError, match="exceeds 60"):
        asyncio.run(
            _service().replace_schedule(
                "user-a",
                [_occurrence(key=f"occurrence-{index}") for index in range(61)],
            )
        )


def test_dispatch_command_renders_backend_owned_copy_and_route() -> None:
    """Ensure persisted kind/locale commands render fixed Felix messages.

    Returns:
        None.
    """
    delivery = _Delivery()
    service = _service(delivery=delivery)

    report = asyncio.run(
        service.dispatch_command(
            "user-a",
            '{"kind":"gratitude","locale":"en"}',
        )
    )

    assert report.delivered == 1
    assert delivery.user_id == "user-a"
    assert delivery.message == FelixWebPushMessage(
        title="Gratitude prompt",
        body="What was one small good moment today?",
        tag="felix-gratitude",
        route="/wellness/gratitude",
    )
    with pytest.raises(ValueError, match="Malformed"):
        asyncio.run(
            service.dispatch_command(
                "user-a",
                '{"kind":"gratitude","locale":"en","body":"override"}',
            )
        )


def test_authenticated_schedule_route_keeps_owner_and_returns_counts() -> None:
    """Ensure the route forwards only current-account predefined occurrences.

    Returns:
        None.
    """
    store = _Store()
    service = _service(store)
    request = FelixWebPushScheduleReplaceRequest.model_validate(
        {
            "occurrences": [
                {
                    "scheduleKey": "checkin-1",
                    "kind": "checkin",
                    "dueAt": "2026-07-13T21:00:00Z",
                    "locale": "de",
                }
            ]
        }
    )

    response = asyncio.run(
        web_push.replace_web_push_schedule(
            request=request,
            current_user_id="user-a",
            service=service,
        )
    )

    assert store.user_id == "user-a"
    assert response.data.scheduled == 1
    assert response.data.removed == 2
    assert response.data.dispatch_enabled is True


def test_schedule_route_maps_disabled_deployment_to_retryable_503() -> None:
    """Ensure disabled dispatch is explicit rather than accepting silent work.

    Returns:
        None.
    """
    request = FelixWebPushScheduleReplaceRequest(occurrences=[])

    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            web_push.replace_web_push_schedule(
                request=request,
                current_user_id="user-a",
                service=_service(enabled=False),
            )
        )

    assert captured.value.status_code == 503
    assert "not enabled" in str(captured.value.detail)
