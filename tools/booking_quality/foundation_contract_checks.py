"""Verify live request correlation and authenticated account foundations.

This module keeps account/context contracts separate from the broader runtime
orchestrator. Tokens remain caller-owned and in memory; no function logs or
persists them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen

from booking_quality.config import (
    QUALITY_ORGANIZATION_A_ID,
    QUALITY_ORGANIZATION_B_ID,
    BookingServiceQualityError,
    QualityRuntime,
)


class BearerJsonRequester(Protocol):
    """Describe the authenticated JSON request helper used by live checks."""

    def __call__(
        self,
        url: str,
        access_token: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
        timeout_seconds: float = 5.0,
    ) -> Any:
        """Perform one authenticated request and return decoded JSON.

        Args:
            url: Loopback Booking API endpoint.
            access_token: Short-lived token retained only for this invocation.
            method: HTTP method, defaulting to ``GET``.
            payload: Optional JSON object sent as the request body.
            timeout_seconds: Per-request timeout, defaulting to five seconds.

        Returns:
            Decoded JSON object or list supplied by the live API.
        """


BearerJsonReader = Callable[[str, str], dict[str, Any]]
"""Read one authenticated JSON object from a loopback endpoint."""

ExpectedStatusAssertion = Callable[[Callable[[], object], int, str], None]
"""Require one operation to fail with an exact HTTP status."""


@dataclass(frozen=True)
class FoundationContractCheckTools:
    """Inject token-safe HTTP helpers into foundational live checks.

    Attributes:
        request_bearer_json: General authenticated JSON request helper.
        read_bearer_json: Authenticated object-only GET helper.
        expect_http_status: Exact safe HTTP-error assertion helper.
    """

    request_bearer_json: BearerJsonRequester
    read_bearer_json: BearerJsonReader
    expect_http_status: ExpectedStatusAssertion


def assert_request_correlation_contract(runtime: QualityRuntime) -> None:
    """Verify one safe client request ID is echoed by the live API.

    Args:
        runtime: Runtime containing the local API origin.

    Returns:
        None: Successful return proves browser-readable request correlation.

    Raises:
        BookingServiceQualityError: When the response omits or changes the ID.
        HTTPError: When the health request fails.
        URLError: When the local API cannot be reached.

    Side Effects:
        Performs one loopback HTTP health request.
    """

    request_id = "booking-quality-correlation"
    request = Request(
        f"{runtime.api_origin}/health",
        headers={"X-Request-ID": request_id},
        method="GET",
    )
    with urlopen(request, timeout=5.0) as response:
        response.read()
        observed = response.headers.get("X-Request-ID")
    if observed != request_id:
        raise BookingServiceQualityError("API request correlation contract drifted.")


def verify_account_foundations(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: FoundationContractCheckTools,
) -> None:
    """Verify context projection and per-subject preference behavior.

    Args:
        runtime: Runtime containing the local Booking API origin.
        tokens: Role-keyed short-lived tokens for distinct fixture subjects.
        tools: Injected authenticated request and status helpers.

    Returns:
        None: Successful return proves both foundational contracts.

    Raises:
        BookingServiceQualityError: When context, persistence, isolation, or
            optimistic concurrency behavior drifts.
    """

    _assert_context_memberships(runtime, tokens, tools.read_bearer_json)
    _assert_user_preferences(runtime, tokens, tools)


def _read_context(
    runtime: QualityRuntime,
    token: str,
    read_bearer_json: BearerJsonReader,
) -> dict[str, Any]:
    """Read one effective context using caller-owned [token].

    Args:
        runtime: Runtime containing the local Booking API origin.
        token: Short-lived fixture token retained only in request memory.
        read_bearer_json: Authenticated object-only GET helper.

    Returns:
        Parsed effective-context response.
    """

    return read_bearer_json(f"{runtime.api_origin}/v1/me/context", token)


def _assert_context_memberships(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    read_bearer_json: BearerJsonReader,
) -> None:
    """Prove platform dual-gating and active multi-tenant context projection.

    Args:
        runtime: Runtime containing the local Booking API origin.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        read_bearer_json: Authenticated object-only GET helper.

    Returns:
        None: Successful return means projections match seed policy.

    Raises:
        BookingServiceQualityError: When capabilities or scopes drift.
    """

    platform = _read_context(runtime, tokens["platform_admin"], read_bearer_json)
    if platform.get("platform_capabilities") != ["manage_platform_organizations"]:
        raise BookingServiceQualityError("Platform dual-gate capability proof failed.")
    expected_ids = {
        "organization_admin": [QUALITY_ORGANIZATION_A_ID, QUALITY_ORGANIZATION_B_ID],
        "worker": [QUALITY_ORGANIZATION_A_ID],
        "customer": [],
    }
    for role, organization_ids in expected_ids.items():
        projected = _read_context(
            runtime,
            tokens[role],
            read_bearer_json,
        ).get("organizations")
        if not isinstance(projected, list):
            raise BookingServiceQualityError("Organization context shape drifted.")
        observed = [
            item.get("organization", {}).get("organization_id")
            for item in projected
        ]
        if observed != organization_ids:
            raise BookingServiceQualityError("Organization context isolation proof failed.")


def _assert_user_preferences(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: FoundationContractCheckTools,
) -> None:
    """Prove locale persistence, account isolation, and stale protection.

    Args:
        runtime: Runtime containing the local Booking API origin.
        tokens: Role-keyed short-lived tokens for distinct subjects.
        tools: Injected authenticated request and status helpers.

    Returns:
        None: Successful return proves preferences remain subject-scoped.

    Raises:
        BookingServiceQualityError: When defaults, persistence, isolation, or
            optimistic concurrency drift.
    """

    url = f"{runtime.api_origin}/v1/me/preferences"
    admin_token = tokens["organization_admin"]
    initial = tools.read_bearer_json(url, admin_token)
    if initial != {"preferred_locale": "de", "revision": 1}:
        raise BookingServiceQualityError("User preference defaults drifted.")
    updated = tools.request_bearer_json(
        url,
        admin_token,
        method="PUT",
        payload={"expected_revision": 1, "preferred_locale": "en"},
    )
    if updated != {"preferred_locale": "en", "revision": 2}:
        raise BookingServiceQualityError("User preference update proof failed.")
    if tools.read_bearer_json(url, admin_token) != updated:
        raise BookingServiceQualityError("User preference persistence proof failed.")
    worker_preferences = tools.read_bearer_json(url, tokens["worker"])
    if worker_preferences != {"preferred_locale": "de", "revision": 1}:
        raise BookingServiceQualityError("User preference isolation proof failed.")
    tools.expect_http_status(
        lambda: tools.request_bearer_json(
            url,
            admin_token,
            method="PUT",
            payload={"expected_revision": 1, "preferred_locale": "de"},
        ),
        409,
        "Stale user preference update did not fail with conflict semantics.",
    )
