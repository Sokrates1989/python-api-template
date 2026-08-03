"""Live BKG-202 workforce and service-eligibility quality checks."""

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
class WorkforceCheckTools:
    """Bundle shared HTTP and token helpers without import cycles.

    Attributes:
        request_json: Authenticated request returning a JSON value.
        read_json: Authenticated JSON-object reader.
        expect_status: Assertion helper for one expected HTTP failure.
        decode_token: Local fixture decoder used only to locate the seed subject.
    """

    request_json: Callable[..., Any]
    read_json: Callable[..., dict[str, Any]]
    expect_status: Callable[[Callable[[], object], int, str], None]
    decode_token: Callable[[str], dict[str, Any]]


def _organization_url(runtime: QualityRuntime, organization_id: str) -> str:
    """Build one tenant-scoped Booking endpoint root.

    Args:
        runtime: Runtime containing the local API origin.
        organization_id: Exact tenant fixture identifier.

    Returns:
        str: Absolute tenant endpoint root.
    """
    return f"{runtime.api_origin}/v1/organizations/{organization_id}"


def _first_location(
    runtime: QualityRuntime,
    organization_id: str,
    token: str,
    tools: WorkforceCheckTools,
) -> str:
    """Return the first active location of one quality tenant.

    Args:
        runtime: Running disposable quality stack.
        organization_id: Tenant owning the expected location.
        token: Authorized organization-administrator token.
        tools: Shared authenticated request helpers.

    Returns:
        str: Active same-tenant location identifier.

    Raises:
        BookingServiceQualityError: When the seeded location disappeared.
    """
    settings = tools.read_json(
        f"{_organization_url(runtime, organization_id)}/company-settings",
        token,
    )
    locations = settings.get("locations")
    location_id = locations[0].get("location_id") if isinstance(locations, list) and locations else None
    if not isinstance(location_id, str):
        raise BookingServiceQualityError("Workforce location fixture disappeared.")
    return location_id


def _worker_membership_id(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
) -> str:
    """Resolve the seeded worker's app-owned membership identifier.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared HTTP and local token helpers.

    Returns:
        str: Same-tenant worker membership identifier.

    Raises:
        BookingServiceQualityError: When the worker membership is absent.
    """
    subject_id = tools.decode_token(tokens["worker"]).get("sub")
    rows = tools.request_json(
        f"{_organization_url(runtime, QUALITY_ORGANIZATION_A_ID)}/memberships",
        tokens["organization_admin"],
    )
    if not isinstance(rows, list):
        raise BookingServiceQualityError("Workforce membership list shape drifted.")
    membership = next(
        (item for item in rows if item.get("subject_id") == subject_id),
        None,
    )
    membership_id = membership.get("membership_id") if isinstance(membership, dict) else None
    if not isinstance(membership_id, str):
        raise BookingServiceQualityError("Seeded worker membership disappeared.")
    return membership_id


def _service_payload(location_id: str, **changes: object) -> dict[str, Any]:
    """Build one complete workforce-specific service request.

    Args:
        location_id: Explicit active same-tenant location.
        **changes: Field overrides for create or replacement proof.

    Returns:
        dict[str, Any]: Complete service payload.
    """
    payload: dict[str, Any] = {
        "name": "Specific quality massage",
        "description": "BKG-202 deterministic fixture",
        "category": "Wellness",
        "duration_minutes": 45,
        "setup_buffer_minutes": 5,
        "cleanup_buffer_minutes": 10,
        "slot_step_minutes": 15,
        "price_minor_units": 7_500,
        "currency": "EUR",
        "is_published": False,
        "worker_selection_mode": "specific_only",
        "location_ids": [location_id],
    }
    payload.update(changes)
    return payload


def _worker_payload(
    membership_id: str,
    location_id: str,
    service_id: str,
    **changes: object,
) -> dict[str, Any]:
    """Build one complete explicit worker configuration.

    Args:
        membership_id: Existing same-tenant worker membership.
        location_id: Explicit active worker location.
        service_id: Explicit active service qualification.
        **changes: Field overrides for the requested proof.

    Returns:
        dict[str, Any]: Complete create payload.
    """
    payload: dict[str, Any] = {
        "membership_id": membership_id,
        "public_name": "Quality Worker",
        "public_description": "Public quality fixture",
        "is_publicly_bookable": True,
        "location_ids": [location_id],
        "qualifications": [
            {
                "service_offering_id": service_id,
                "auto_eligible": True,
                "priority": 25,
            }
        ],
    }
    payload.update(changes)
    return payload


def _worker_replacement(profile: Mapping[str, Any], **changes: object) -> dict[str, Any]:
    """Build an optimistic worker replacement from one response.

    Args:
        profile: Current worker response.
        **changes: Fields overriding current mutable state.

    Returns:
        dict[str, Any]: Complete worker update payload.
    """
    qualifications = [
        {
            "service_offering_id": item.get("service_offering_id"),
            "auto_eligible": item.get("auto_eligible"),
            "priority": item.get("priority"),
        }
        for item in profile.get("qualifications", [])
    ]
    payload: dict[str, Any] = {
        "expected_revision": profile.get("revision"),
        "public_name": profile.get("public_name"),
        "public_description": profile.get("public_description"),
        "is_publicly_bookable": profile.get("is_publicly_bookable"),
        "location_ids": profile.get("location_ids"),
        "qualifications": qualifications,
    }
    payload.update(changes)
    return payload


def _settings_replacement(settings: Mapping[str, Any], mode: str) -> dict[str, Any]:
    """Build a complete settings replacement with one selection-mode change.

    Args:
        settings: Current company-settings response.
        mode: Requested company worker-selection wire value.

    Returns:
        dict[str, Any]: Complete optimistic settings payload.
    """
    fields = (
        "public_name", "description", "contact_email", "contact_phone",
        "website_url", "default_timezone", "default_locale", "currency",
        "booking_horizon_days", "minimum_notice_minutes",
        "cancellation_notice_minutes", "reschedule_notice_minutes",
    )
    payload = {field: settings.get(field) for field in fields}
    payload.update(expected_revision=settings.get("revision"), worker_selection_mode=mode)
    return payload


def _location_payload() -> dict[str, Any]:
    """Build one complete location proving no implicit worker assignment.

    Returns:
        dict[str, Any]: Valid neutral location payload.
    """
    return {
        "display_name": "Unassigned workforce room",
        "timezone": "Europe/Berlin",
        "address_line_1": None,
        "address_line_2": None,
        "postal_code": None,
        "locality": None,
        "region": None,
        "country_code": None,
        "contact_email": None,
        "contact_phone": None,
    }


@dataclass(frozen=True)
class _WorkforceFixture:
    """Carry identifiers and first revisions across live proof steps.

    Attributes:
        organization_url: Tenant-scoped API root.
        services_url: Tenant-scoped service collection.
        workers_url: Tenant-scoped worker collection.
        location_id: Explicit worker/service location.
        service: Newly created unpublished specific-only service.
        profile: Newly created public worker profile.
    """

    organization_url: str
    services_url: str
    workers_url: str
    location_id: str
    service: dict[str, Any]
    profile: dict[str, Any]


def _create_workforce_fixture(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
) -> _WorkforceFixture:
    """Prove creation guards and create one valid workforce fixture.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request, assertion, and token helpers.

    Returns:
        _WorkforceFixture: Valid unpublished service and worker state.

    Raises:
        BookingServiceQualityError: When fixture creation or a guard drifts.
    """
    admin = tokens["organization_admin"]
    organization = _organization_url(runtime, QUALITY_ORGANIZATION_A_ID)
    location_id = _first_location(runtime, QUALITY_ORGANIZATION_A_ID, admin, tools)
    foreign = _first_location(runtime, QUALITY_ORGANIZATION_B_ID, admin, tools)
    membership_id = _worker_membership_id(runtime, tokens, tools)
    services_url = f"{organization}/services"
    service = tools.request_json(
        services_url, admin, method="POST", payload=_service_payload(location_id)
    )
    service_id = service.get("service_offering_id") if isinstance(service, dict) else None
    if not isinstance(service_id, str):
        raise BookingServiceQualityError("Workforce service fixture failed.")
    workers_url = f"{organization}/workers"
    _assert_creation_guards(
        tokens, tools, workers_url, membership_id, location_id, foreign, service_id
    )
    profile = tools.request_json(
        workers_url,
        admin,
        method="POST",
        payload=_worker_payload(membership_id, location_id, service_id),
    )
    if not isinstance(profile, dict) or profile.get("revision") != 1:
        raise BookingServiceQualityError("Worker creation projection drifted.")
    return _WorkforceFixture(
        organization, services_url, workers_url, location_id, service, profile
    )


def _assert_creation_guards(
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
    workers_url: str,
    membership_id: str,
    location_id: str,
    foreign_location: str,
    service_id: str,
) -> None:
    """Reject membership-free, worker-mutation, and foreign-location access.

    Args:
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request and assertion helpers.
        workers_url: Tenant-scoped worker collection.
        membership_id: Existing worker membership.
        location_id: Valid same-tenant location.
        foreign_location: Location owned by another tenant.
        service_id: Active same-tenant service.

    Returns:
        None: Successful return proves all creation guards.
    """
    tools.expect_status(
        lambda: tools.request_json(workers_url, tokens["platform_admin"]),
        404,
        "Membership-free platform role could read workforce state.",
    )
    tools.expect_status(
        lambda: tools.request_json(
            workers_url,
            tokens["worker"],
            method="POST",
            payload=_worker_payload(membership_id, location_id, service_id),
        ),
        403,
        "Worker could create a workforce profile.",
    )
    tools.expect_status(
        lambda: tools.request_json(
            workers_url,
            tokens["organization_admin"],
            method="POST",
            payload=_worker_payload(membership_id, foreign_location, service_id),
        ),
        422,
        "Foreign worker location escaped tenant scope.",
    )


def _publish_and_assert_self_summary(
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
    fixture: _WorkforceFixture,
) -> dict[str, Any]:
    """Publish the specific service and prove worker self-only projection.

    Args:
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.
        fixture: Created service and worker state.

    Returns:
        dict[str, Any]: Published next service revision.

    Raises:
        BookingServiceQualityError: When the worker summary drifts.
    """
    service_id = fixture.service["service_offering_id"]
    publish = _service_payload(fixture.location_id, is_published=True)
    publish["expected_revision"] = fixture.service.get("revision")
    published = tools.request_json(
        f"{fixture.services_url}/{service_id}",
        tokens["organization_admin"],
        method="PUT",
        payload=publish,
    )
    rows = tools.request_json(fixture.workers_url, tokens["worker"])
    qualification = rows[0].get("qualifications", [{}])[0] if isinstance(rows, list) and rows else {}
    if (
        not isinstance(published, dict)
        or len(rows) != 1
        or rows[0].get("worker_profile_id") != fixture.profile.get("worker_profile_id")
        or qualification.get("is_individually_bookable") is not True
    ):
        raise BookingServiceQualityError("Worker self-summary policy drifted.")
    return published


def _assert_stranding_guards(
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
    fixture: _WorkforceFixture,
) -> None:
    """Reject company and worker mutations that strand specific-only service.

    Args:
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request and assertion helpers.
        fixture: Published specific service and public worker state.

    Returns:
        None: Successful return proves both dependency guards.
    """
    admin = tokens["organization_admin"]
    settings_url = f"{fixture.organization_url}/company-settings"
    settings = tools.read_json(settings_url, admin)
    tools.expect_status(
        lambda: tools.request_json(
            settings_url,
            admin,
            method="PUT",
            payload=_settings_replacement(settings, "next_available_only"),
        ),
        409,
        "Company policy stranded a published specific-only service.",
    )
    item_url = f"{fixture.workers_url}/{fixture.profile['worker_profile_id']}"
    tools.expect_status(
        lambda: tools.request_json(
            item_url,
            admin,
            method="PUT",
            payload=_worker_replacement(
                fixture.profile,
                is_publicly_bookable=False,
            ),
        ),
        409,
        "Worker visibility mutation stranded a specific-only service.",
    )


def _hide_worker_after_relaxing_service(
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
    fixture: _WorkforceFixture,
    published: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove hidden workers retain explicit automatic participation.

    Args:
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.
        fixture: Created service and worker state.
        published: Published specific-only service revision.

    Returns:
        dict[str, Any]: Hidden next worker revision.

    Raises:
        BookingServiceQualityError: When visibility changes auto eligibility.
    """
    admin = tokens["organization_admin"]
    service_id = fixture.service["service_offering_id"]
    relaxed = _service_payload(
        fixture.location_id,
        is_published=True,
        worker_selection_mode="specific_or_auto",
    )
    relaxed["expected_revision"] = published.get("revision")
    tools.request_json(
        f"{fixture.services_url}/{service_id}", admin, method="PUT", payload=relaxed
    )
    item_url = f"{fixture.workers_url}/{fixture.profile['worker_profile_id']}"
    hidden = tools.request_json(
        item_url,
        admin,
        method="PUT",
        payload=_worker_replacement(fixture.profile, is_publicly_bookable=False),
    )
    qualification = hidden.get("qualifications", [{}])[0]
    if qualification.get("auto_eligible") is not True or qualification.get(
        "is_individually_bookable"
    ) is not False:
        raise BookingServiceQualityError("Hidden worker automatic eligibility drifted.")
    return hidden


def _assert_assignment_revision_scope_and_lifecycle(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
    fixture: _WorkforceFixture,
    hidden: Mapping[str, Any],
) -> None:
    """Prove explicit locations, stale protection, scope, and lifecycle.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request and assertion helpers.
        fixture: Created service and first worker revision.
        hidden: Hidden current worker revision.

    Returns:
        None: Successful return means remaining workforce invariants pass.

    Raises:
        BookingServiceQualityError: When assignment or lifecycle behavior drifts.
    """
    admin = tokens["organization_admin"]
    worker_id = fixture.profile["worker_profile_id"]
    item_url = f"{fixture.workers_url}/{worker_id}"
    tools.request_json(
        f"{fixture.organization_url}/locations",
        admin,
        method="POST",
        payload=_location_payload(),
    )
    unchanged = tools.read_json(item_url, admin)
    if unchanged.get("location_ids") != [fixture.location_id]:
        raise BookingServiceQualityError("New location assigned a worker implicitly.")
    disabled = _disable_auto_eligibility(admin, tools, item_url, hidden)
    tools.expect_status(
        lambda: tools.request_json(
            item_url, admin, method="PUT", payload=_worker_replacement(hidden)
        ),
        409,
        "Stale worker replacement did not conflict.",
    )
    foreign = f"{_organization_url(runtime, QUALITY_ORGANIZATION_B_ID)}/workers/{worker_id}"
    tools.expect_status(
        lambda: tools.request_json(foreign, admin),
        404,
        "Worker identifier escaped tenant scope.",
    )
    _assert_worker_lifecycle(admin, tools, item_url, disabled)


def _disable_auto_eligibility(
    admin_token: str,
    tools: WorkforceCheckTools,
    item_url: str,
    hidden: Mapping[str, Any],
) -> dict[str, Any]:
    """Disable automatic participation through one complete replacement.

    Args:
        admin_token: Organization-administrator access token.
        tools: Shared authenticated request helpers.
        item_url: Exact worker endpoint.
        hidden: Current hidden worker response.

    Returns:
        dict[str, Any]: Next worker revision with auto eligibility disabled.
    """
    qualification = dict(hidden.get("qualifications", [{}])[0], auto_eligible=False)
    qualification.pop("is_individually_bookable", None)
    return tools.request_json(
        item_url,
        admin_token,
        method="PUT",
        payload=_worker_replacement(hidden, qualifications=[qualification]),
    )


def _assert_worker_lifecycle(
    admin_token: str,
    tools: WorkforceCheckTools,
    item_url: str,
    current: Mapping[str, Any],
) -> None:
    """Prove reversible workforce activation without deleting configuration.

    Args:
        admin_token: Organization-administrator access token.
        tools: Shared authenticated request helpers.
        item_url: Exact worker endpoint.
        current: Active current worker response.

    Returns:
        None: Successful return proves deactivate/reactivate lifecycle.

    Raises:
        BookingServiceQualityError: When lifecycle projections drift.
    """
    inactive = tools.request_json(
        f"{item_url}?expected_revision={current.get('revision')}",
        admin_token,
        method="DELETE",
    )
    reactivated = tools.request_json(
        f"{item_url}/reactivate",
        admin_token,
        method="POST",
        payload={"expected_revision": inactive.get("revision")},
    )
    if inactive.get("status") != "inactive" or reactivated.get("status") != "active":
        raise BookingServiceQualityError("Worker lifecycle proof drifted.")


def verify_workforce(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: WorkforceCheckTools,
) -> None:
    """Run live BKG-202 tenancy, policy, visibility, and lifecycle proofs.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request, assertion, and token helpers.

    Returns:
        None: Successful return means every workforce invariant passes.

    Raises:
        BookingServiceQualityError: When any BKG-202 behavior drifts.
    """
    fixture = _create_workforce_fixture(runtime, tokens, tools)
    published = _publish_and_assert_self_summary(tokens, tools, fixture)
    _assert_stranding_guards(tokens, tools, fixture)
    hidden = _hide_worker_after_relaxing_service(
        tokens,
        tools,
        fixture,
        published,
    )
    _assert_assignment_revision_scope_and_lifecycle(
        runtime,
        tokens,
        tools,
        fixture,
        hidden,
    )
