"""Live BKG-203 authenticated discovery and privacy-minimization checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from booking_quality.config import (
    QUALITY_ORGANIZATION_A_ID,
    QUALITY_ORGANIZATION_B_ID,
    BookingServiceQualityError,
    QualityRuntime,
)


@dataclass(frozen=True)
class DiscoveryCheckTools:
    """Bundle shared authenticated HTTP helpers without import cycles.

    Attributes:
        request_json: Authenticated request returning a JSON value.
        read_json: Authenticated JSON-object reader.
        expect_status: Assertion helper for one expected HTTP failure.
    """

    request_json: Callable[..., Any]
    read_json: Callable[..., dict[str, Any]]
    expect_status: Callable[[Callable[[], object], int, str], None]


def _organization_url(runtime: QualityRuntime, organization_id: str) -> str:
    """Build one tenant-scoped Booking endpoint root.

    Args:
        runtime: Runtime containing the local API origin.
        organization_id: Exact tenant fixture identifier.

    Returns:
        str: Absolute tenant endpoint root.
    """
    return f"{runtime.api_origin}/v1/organizations/{organization_id}"


def _worker_replacement(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Build a complete update that makes the fixture worker public again.

    Args:
        profile: Current administrator worker response.

    Returns:
        dict[str, Any]: Complete optimistic worker update payload.
    """
    qualifications = []
    for item in profile.get("qualifications", []):
        qualification = dict(item)
        qualification.pop("is_individually_bookable", None)
        qualifications.append(qualification)
    return {
        "expected_revision": profile.get("revision"),
        "public_name": "Quality Worker",
        "public_description": "Customer-visible discovery fixture",
        "is_publicly_bookable": True,
        "location_ids": profile.get("location_ids"),
        "qualifications": qualifications,
    }


def _settings_replacement(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Build a complete update disabling individual worker presentation.

    Args:
        settings: Current organization settings response.

    Returns:
        dict[str, Any]: Complete optimistic settings update payload.
    """
    fields = (
        "public_name",
        "description",
        "contact_email",
        "contact_phone",
        "website_url",
        "default_timezone",
        "default_locale",
        "currency",
        "booking_horizon_days",
        "minimum_notice_minutes",
        "cancellation_notice_minutes",
        "reschedule_notice_minutes",
    )
    payload = {field: settings.get(field) for field in fields}
    payload.update(
        expected_revision=settings.get("revision"),
        worker_selection_mode="next_available_only",
    )
    return payload


def _make_worker_visible(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: DiscoveryCheckTools,
) -> None:
    """Restore the workforce fixture to individually visible discovery state.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.

    Returns:
        None: The fixture worker is public and selectable after success.

    Raises:
        BookingServiceQualityError: When the workforce fixture is absent.
    """
    workers_url = f"{_organization_url(runtime, QUALITY_ORGANIZATION_A_ID)}/workers"
    profiles = tools.request_json(workers_url, tokens["organization_admin"])
    if not isinstance(profiles, list) or len(profiles) != 1:
        raise BookingServiceQualityError("Discovery workforce fixture disappeared.")
    profile = profiles[0]
    tools.request_json(
        f"{workers_url}/{profile['worker_profile_id']}",
        tokens["organization_admin"],
        method="PUT",
        payload=_worker_replacement(profile),
    )


def _assert_privacy_shape(catalog: Mapping[str, Any]) -> None:
    """Require the exact privacy-minimized discovery response keys.

    Args:
        catalog: Published catalog response returned by the live API.

    Returns:
        None: Successful return proves the stable public response shape.

    Raises:
        BookingServiceQualityError: When private or required fields drift.
    """
    expected_catalog = {
        "organization_id",
        "public_name",
        "description",
        "default_locale",
        "currency",
        "locations",
        "services",
    }
    service = catalog.get("services", [{}])[0]
    worker = service.get("workers", [{}])[0] if isinstance(service, dict) else {}
    if set(catalog) != expected_catalog:
        raise BookingServiceQualityError("Discovery organization privacy shape drifted.")
    forbidden = {
        "membership_id",
        "subject_id",
        "revision",
        "priority",
        "auto_eligible",
        "setup_buffer_minutes",
        "cleanup_buffer_minutes",
        "slot_step_minutes",
    }
    serialized = {**catalog, **service, **worker}
    if forbidden.intersection(serialized):
        raise BookingServiceQualityError("Discovery exposed an internal field.")


def _assert_membership_free_discovery(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: DiscoveryCheckTools,
) -> dict[str, Any]:
    """Prove a membership-free authenticated customer sees published content.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.

    Returns:
        dict[str, Any]: North organization public catalog.

    Raises:
        BookingServiceQualityError: When visibility or privacy policy drifts.
    """
    discovery_url = f"{runtime.api_origin}/v1/discovery/organizations"
    rows = tools.request_json(discovery_url, tokens["customer"])
    if not isinstance(rows, list) or len(rows) != 1:
        raise BookingServiceQualityError("Published discovery tenant filtering drifted.")
    catalog = rows[0]
    services = catalog.get("services", [])
    if (
        catalog.get("organization_id") != QUALITY_ORGANIZATION_A_ID
        or not services
        or not any(service.get("workers") for service in services)
    ):
        raise BookingServiceQualityError("Membership-free discovery content drifted.")
    _assert_privacy_shape(catalog)
    tools.expect_status(
        lambda: tools.request_json(
            f"{discovery_url}/{QUALITY_ORGANIZATION_B_ID}",
            tokens["customer"],
        ),
        404,
        "Organization without a published service was discoverable.",
    )
    return catalog


def _assert_preview_and_policy_hiding(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: DiscoveryCheckTools,
    public_catalog: Mapping[str, Any],
) -> None:
    """Prove admin preview parity and company-level worker hiding.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.
        public_catalog: Customer projection before hiding workers.

    Returns:
        None: Successful return proves preview parity and effective policy.
    """
    organization_url = _organization_url(runtime, QUALITY_ORGANIZATION_A_ID)
    preview_url = f"{organization_url}/discovery-preview"
    preview = tools.read_json(preview_url, tokens["organization_admin"])
    if preview != public_catalog:
        raise BookingServiceQualityError("Admin preview differs from customer projection.")
    tools.expect_status(
        lambda: tools.request_json(preview_url, tokens["customer"]),
        403,
        "Customer could open tenant admin preview.",
    )
    settings_url = f"{organization_url}/company-settings"
    settings = tools.read_json(settings_url, tokens["organization_admin"])
    tools.request_json(
        settings_url,
        tokens["organization_admin"],
        method="PUT",
        payload=_settings_replacement(settings),
    )
    hidden = tools.read_json(
        f"{runtime.api_origin}/v1/discovery/organizations/{QUALITY_ORGANIZATION_A_ID}",
        tokens["customer"],
    )
    if any(service.get("workers") for service in hidden.get("services", [])):
        raise BookingServiceQualityError("Company policy did not hide public workers.")


def verify_discovery(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: DiscoveryCheckTools,
) -> None:
    """Run live authentication, publication, privacy, and preview proofs.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request and expected-status helpers.

    Returns:
        None: Successful return means every BKG-203 invariant passes.

    Raises:
        BookingServiceQualityError: When any discovery behavior drifts.
    """
    tools.expect_status(
        lambda: tools.request_json(
            f"{runtime.api_origin}/v1/discovery/organizations",
            "",
        ),
        401,
        "Anonymous published discovery did not fail closed.",
    )
    _make_worker_visible(runtime, tokens, tools)
    public_catalog = _assert_membership_free_discovery(runtime, tokens, tools)
    _assert_preview_and_policy_hiding(runtime, tokens, tools, public_catalog)
