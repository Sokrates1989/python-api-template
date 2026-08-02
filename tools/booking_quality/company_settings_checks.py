"""Live BKG-200 company-settings checks for the disposable quality stack."""

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
class CompanySettingsCheckTools:
    """Bundle shared HTTP helpers without creating runtime-check imports.

    Attributes:
        request_json: Authenticated JSON request supporting method and payload.
        read_json: Authenticated JSON object reader.
        expect_status: Assertion helper for one expected HTTP failure.
    """

    request_json: Callable[..., Any]
    read_json: Callable[..., dict[str, Any]]
    expect_status: Callable[[Callable[[], object], int, str], None]


def _settings_url(runtime: QualityRuntime, organization_id: str) -> str:
    """Build one tenant-scoped company-settings endpoint.

    Args:
        runtime: Runtime containing the local API origin.
        organization_id: Exact tenant fixture identifier.

    Returns:
        str: Absolute loopback settings URL.
    """
    return (
        f"{runtime.api_origin}/v1/organizations/"
        f"{organization_id}/company-settings"
    )


def _replacement(settings: Mapping[str, Any], **changes: object) -> dict[str, Any]:
    """Build a complete update request from one settings response.

    Args:
        settings: Current company-settings response.
        **changes: Field overrides for the requested proof.

    Returns:
        dict[str, Any]: Complete optimistic replacement payload.
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
        "worker_selection_mode",
    )
    payload = {field: settings.get(field) for field in fields}
    payload["expected_revision"] = settings.get("revision")
    payload.update(changes)
    return payload


def _assert_read_and_scope_guards(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: CompanySettingsCheckTools,
) -> dict[str, Any]:
    """Prove member reads and denial of membership-free platform access.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.

    Returns:
        dict[str, Any]: Organization A settings observed by the administrator.

    Raises:
        BookingServiceQualityError: When defaults, placeholders, or scope drift.
    """
    url = _settings_url(runtime, QUALITY_ORGANIZATION_A_ID)
    settings = tools.read_json(url, tokens["organization_admin"])
    worker_view = tools.read_json(url, tokens["worker"])
    locations = settings.get("locations")
    if (
        settings.get("organization_id") != QUALITY_ORGANIZATION_A_ID
        or worker_view.get("revision") != settings.get("revision")
        or settings.get("payment_configuration_status") != "not_configured"
        or not isinstance(locations, list)
        or len(locations) != 1
    ):
        raise BookingServiceQualityError("Company-settings default projection drifted.")
    tools.expect_status(
        lambda: tools.read_json(url, tokens["platform_admin"]),
        404,
        "Membership-free platform role could read tenant company settings.",
    )
    return settings


def _assert_settings_mutation_guards(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: CompanySettingsCheckTools,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Prove validation, role denial, replacement, and stale protection.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.
        settings: Current organization A settings response.

    Returns:
        dict[str, Any]: Successfully updated settings response.

    Raises:
        BookingServiceQualityError: When update or revision behavior drifts.
    """
    url = _settings_url(runtime, QUALITY_ORGANIZATION_A_ID)
    valid = _replacement(settings, public_name="Booking Quality North Updated")
    tools.expect_status(
        lambda: tools.request_json(url, tokens["worker"], method="PUT", payload=valid),
        403,
        "Worker could mutate company settings.",
    )
    for field, value in (("currency", "ZZZ"), ("default_timezone", "Mars/Olympus")):
        tools.expect_status(
            lambda field=field, value=value: tools.request_json(
                url,
                tokens["organization_admin"],
                method="PUT",
                payload=_replacement(settings, **{field: value}),
            ),
            422,
            f"Unsupported company {field} passed validation.",
        )
    updated = tools.request_json(
        url,
        tokens["organization_admin"],
        method="PUT",
        payload=valid,
    )
    if not isinstance(updated, dict) or updated.get("revision") != settings.get("revision", 0) + 1:
        raise BookingServiceQualityError("Company-settings replacement drifted.")
    tools.expect_status(
        lambda: tools.request_json(
            url,
            tokens["organization_admin"],
            method="PUT",
            payload=valid,
        ),
        409,
        "Stale company-settings replacement did not conflict.",
    )
    return updated


def _location_payload(display_name: str) -> dict[str, Any]:
    """Build one valid neutral quality location payload.

    Args:
        display_name: Customer-visible location name.

    Returns:
        dict[str, Any]: Complete create/update location fields.
    """
    return {
        "display_name": display_name,
        "timezone": "Europe/Berlin",
        "address_line_1": "Quality Street 2",
        "address_line_2": None,
        "postal_code": "10115",
        "locality": "Berlin",
        "region": "Berlin",
        "country_code": "DE",
        "contact_email": None,
        "contact_phone": "+49 30 000000",
    }


def _assert_location_lifecycle(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: CompanySettingsCheckTools,
    settings: Mapping[str, Any],
) -> None:
    """Prove create, scoped update, archive, and final-location protection.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.
        settings: Updated organization A settings containing its first location.

    Returns:
        None: Successful return means the location lifecycle is safe.

    Raises:
        BookingServiceQualityError: When tenant or lifecycle invariants drift.
    """
    collection = (
        f"{runtime.api_origin}/v1/organizations/"
        f"{QUALITY_ORGANIZATION_A_ID}/locations"
    )
    created = tools.request_json(
        collection,
        tokens["organization_admin"],
        method="POST",
        payload=_location_payload("Quality South Room"),
    )
    if not isinstance(created, dict) or created.get("status") != "active":
        raise BookingServiceQualityError("Location creation drifted.")
    location_id = created.get("location_id")
    update_payload = _location_payload("Quality South Room Updated")
    update_payload["expected_revision"] = created.get("revision")
    foreign_url = (
        f"{runtime.api_origin}/v1/organizations/{QUALITY_ORGANIZATION_B_ID}"
        f"/locations/{location_id}"
    )
    tools.expect_status(
        lambda: tools.request_json(
            foreign_url,
            tokens["organization_admin"],
            method="PUT",
            payload=update_payload,
        ),
        404,
        "Location identifier escaped its tenant scope.",
    )
    updated = tools.request_json(
        f"{collection}/{location_id}",
        tokens["organization_admin"],
        method="PUT",
        payload=update_payload,
    )
    _archive_and_assert_final_guard(runtime, tokens, tools, settings, updated)


def _archive_and_assert_final_guard(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: CompanySettingsCheckTools,
    settings: Mapping[str, Any],
    updated: Mapping[str, Any],
) -> None:
    """Archive the second location and reject archival of the remaining one.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared authenticated request helpers.
        settings: Settings response containing the initial location.
        updated: Updated second location response.

    Returns:
        None: Successful return proves reversible and final-place behavior.

    Raises:
        BookingServiceQualityError: When archive state or guard behavior drifts.
    """
    base = f"{runtime.api_origin}/v1/organizations/{QUALITY_ORGANIZATION_A_ID}/locations"
    archived = tools.request_json(
        f"{base}/{updated.get('location_id')}?expected_revision={updated.get('revision')}",
        tokens["organization_admin"],
        method="DELETE",
    )
    if not isinstance(archived, dict) or archived.get("status") != "archived":
        raise BookingServiceQualityError("Location soft archive drifted.")
    settings_url = _settings_url(runtime, QUALITY_ORGANIZATION_A_ID)
    administrator_locations = tools.read_json(
        settings_url,
        tokens["organization_admin"],
    ).get("locations", [])
    worker_locations = tools.read_json(settings_url, tokens["worker"]).get(
        "locations",
        [],
    )
    archived_id = archived.get("location_id")
    if (
        not any(item.get("location_id") == archived_id for item in administrator_locations)
        or any(item.get("location_id") == archived_id for item in worker_locations)
    ):
        raise BookingServiceQualityError("Archived location visibility drifted.")
    first = settings.get("locations", [None])[0]
    if not isinstance(first, dict):
        raise BookingServiceQualityError("Initial location proof fixture disappeared.")
    tools.expect_status(
        lambda: tools.request_json(
            f"{base}/{first.get('location_id')}?expected_revision={first.get('revision')}",
            tokens["organization_admin"],
            method="DELETE",
        ),
        409,
        "Final active location could be archived.",
    )
    reactivated = tools.request_json(
        f"{base}/{archived.get('location_id')}/reactivate",
        tokens["organization_admin"],
        method="POST",
        payload={"expected_revision": archived.get("revision")},
    )
    if not isinstance(reactivated, dict) or reactivated.get("status") != "active":
        raise BookingServiceQualityError("Location reactivation drifted.")


def verify_company_settings(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: CompanySettingsCheckTools,
) -> None:
    """Run the complete live BKG-200 backend security and lifecycle proof.

    Args:
        runtime: Running disposable quality stack.
        tokens: Role-keyed short-lived access tokens.
        tools: Shared request and assertion helpers.

    Returns:
        None: Successful return means all company-settings gates pass.

    Raises:
        BookingServiceQualityError: When any BKG-200 invariant drifts.
    """
    settings = _assert_read_and_scope_guards(runtime, tokens, tools)
    updated = _assert_settings_mutation_guards(runtime, tokens, tools, settings)
    _assert_location_lifecycle(runtime, tokens, tools, updated)
