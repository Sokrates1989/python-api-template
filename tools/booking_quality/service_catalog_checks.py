"""Live BKG-201 service-catalog checks for the disposable quality stack."""

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
class ServiceCatalogCheckTools:
    """Bundle shared HTTP helpers without creating runtime-check imports.

    Attributes:
        request_json: Authenticated request returning a JSON object or list.
        read_json: Authenticated JSON-object reader.
        expect_status: Assertion helper for one expected HTTP failure.
    """

    request_json: Callable[..., Any]
    read_json: Callable[..., dict[str, Any]]
    expect_status: Callable[[Callable[[], object], int, str], None]


def _catalog_url(runtime: QualityRuntime, organization_id: str) -> str:
    """Build one tenant-scoped service collection endpoint.

    Args:
        runtime: Runtime containing the local API origin.
        organization_id: Exact tenant fixture identifier.

    Returns:
        str: Absolute loopback catalog URL.
    """
    return f"{runtime.api_origin}/v1/organizations/{organization_id}/services"


def _service_payload(location_id: str, **changes: object) -> dict[str, Any]:
    """Build one valid complete service request.

    Args:
        location_id: Active same-tenant location assignment.
        **changes: Field overrides for the requested proof.

    Returns:
        dict[str, Any]: Complete create/update payload.
    """
    payload: dict[str, Any] = {
        "name": "Quality massage",
        "description": "A deterministic catalog fixture",
        "category": "Wellness",
        "duration_minutes": 60,
        "setup_buffer_minutes": 10,
        "cleanup_buffer_minutes": 15,
        "slot_step_minutes": 15,
        "price_minor_units": 8_500,
        "currency": "EUR",
        "is_published": True,
        "location_ids": [location_id],
    }
    payload.update(changes)
    return payload


def _first_location(
    runtime: QualityRuntime,
    organization_id: str,
    token: str,
    tools: ServiceCatalogCheckTools,
) -> str:
    """Read the first configured location for a quality tenant.

    Args:
        runtime: Running disposable quality stack.
        organization_id: Tenant owning the expected location.
        token: Authorized tenant-administrator token.
        tools: Shared authenticated request helpers.

    Returns:
        str: Stable location identifier.

    Raises:
        BookingServiceQualityError: When company fixtures are missing.
    """
    settings = tools.read_json(
        f"{runtime.api_origin}/v1/organizations/{organization_id}/company-settings",
        token,
    )
    locations = settings.get("locations")
    if not isinstance(locations, list) or not locations:
        raise BookingServiceQualityError("Catalog location fixture disappeared.")
    location_id = locations[0].get("location_id")
    if not isinstance(location_id, str) or not location_id:
        raise BookingServiceQualityError("Catalog location identifier drifted.")
    return location_id


def verify_service_catalog(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: ServiceCatalogCheckTools,
) -> None:
    """Run the live BKG-201 authorization, validation, and lifecycle proof.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request and assertion helpers.

    Returns:
        None: Successful return means every catalog invariant passes.

    Raises:
        BookingServiceQualityError: When any BKG-201 behavior drifts.
    """
    north = _first_location(
        runtime,
        QUALITY_ORGANIZATION_A_ID,
        tokens["organization_admin"],
        tools,
    )
    south = _first_location(
        runtime,
        QUALITY_ORGANIZATION_B_ID,
        tokens["organization_admin"],
        tools,
    )
    collection = _catalog_url(runtime, QUALITY_ORGANIZATION_A_ID)
    tools.expect_status(
        lambda: tools.request_json(collection, tokens["platform_admin"]),
        404,
        "Membership-free platform role could read the service catalog.",
    )
    tools.expect_status(
        lambda: tools.request_json(
            collection,
            tokens["worker"],
            method="POST",
            payload=_service_payload(north),
        ),
        403,
        "Worker could create a service offering.",
    )
    for invalid in (
        _service_payload(north, slot_step_minutes=7),
        _service_payload(north, currency="USD"),
        _service_payload(south),
    ):
        tools.expect_status(
            lambda invalid=invalid: tools.request_json(
                collection,
                tokens["organization_admin"],
                method="POST",
                payload=invalid,
            ),
            422,
            "Invalid service policy or location was accepted.",
        )
    created = tools.request_json(
        collection,
        tokens["organization_admin"],
        method="POST",
        payload=_service_payload(north),
    )
    if not isinstance(created, dict) or created.get("revision") != 1:
        raise BookingServiceQualityError("Service creation projection drifted.")
    service_id = created.get("service_offering_id")
    item = f"{collection}/{service_id}"
    worker_rows = tools.request_json(collection, tokens["worker"])
    if not (
        isinstance(worker_rows, list)
        and len(worker_rows) == 1
        and worker_rows[0].get("service_offering_id") == service_id
    ):
        raise BookingServiceQualityError("Published member catalog drifted.")
    tools.expect_status(
        lambda: tools.request_json(collection, tokens["customer"]),
        403,
        "Membership-free customer bypassed the tenant catalog boundary.",
    )
    foreign_item = f"{_catalog_url(runtime, QUALITY_ORGANIZATION_B_ID)}/{service_id}"
    tools.expect_status(
        lambda: tools.request_json(foreign_item, tokens["organization_admin"]),
        404,
        "Service identifier escaped tenant scope.",
    )
    replacement = _service_payload(north, name="Quality massage updated")
    replacement["expected_revision"] = created.get("revision")
    updated = tools.request_json(
        item,
        tokens["organization_admin"],
        method="PUT",
        payload=replacement,
    )
    tools.expect_status(
        lambda: tools.request_json(
            item,
            tokens["organization_admin"],
            method="PUT",
            payload=replacement,
        ),
        409,
        "Stale service replacement did not conflict.",
    )
    archived = tools.request_json(
        f"{item}?expected_revision={updated.get('revision')}",
        tokens["organization_admin"],
        method="DELETE",
    )
    if archived.get("status") != "archived" or archived.get("is_published"):
        raise BookingServiceQualityError("Service archive did not unpublish safely.")
    if tools.request_json(collection, tokens["worker"]):
        raise BookingServiceQualityError("Archived service remained member-visible.")
    admin_rows = tools.request_json(collection, tokens["organization_admin"])
    if not isinstance(admin_rows, list) or admin_rows[0].get("status") != "archived":
        raise BookingServiceQualityError("Archived service recovery view drifted.")
    reactivated = tools.request_json(
        f"{item}/reactivate",
        tokens["organization_admin"],
        method="POST",
        payload={"expected_revision": archived.get("revision")},
    )
    if reactivated.get("status") != "active" or reactivated.get("is_published"):
        raise BookingServiceQualityError("Service reactivation was not safely unpublished.")
