"""Live BKG-103 membership-management checks for the disposable stack."""

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
class MembershipCheckTools:
    """Bundle shared HTTP/token helpers without creating import cycles.

    Attributes:
        request_json: Authenticated JSON request supporting method and payload.
        read_json: Authenticated JSON object reader.
        expect_status: Assertion helper for one expected HTTP failure.
        decode_token: Local decoder used only for the immutable fixture subject.
    """

    request_json: Callable[..., Any]
    read_json: Callable[..., dict[str, Any]]
    expect_status: Callable[[Callable[[], object], int, str], None]
    decode_token: Callable[[str], dict[str, Any]]


def _assert_scope_guards(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
) -> None:
    """Prove tenant, actor, and role-grant boundaries through the live API.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared request and assertion helpers.

    Returns:
        None: Successful return proves guarded requests fail safely.

    Raises:
        BookingServiceQualityError: When a scope or role boundary drifts.
    """
    base_url = f"{runtime.api_origin}/v1/organizations"
    foreign = tools.request_json(
        f"{runtime.api_origin}/v1/platform/organizations",
        tokens["platform_admin"],
        method="POST",
        payload={"display_name": "Booking Membership Foreign Scope"},
    )
    foreign_id = foreign.get("organization_id") if isinstance(foreign, dict) else None
    if not isinstance(foreign_id, str):
        raise BookingServiceQualityError("Foreign membership scope fixture failed.")
    tools.expect_status(
        lambda: tools.read_json(
            f"{base_url}/{foreign_id}/memberships",
            tokens["organization_admin"],
        ),
        404,
        "Organization admin could enumerate a foreign membership scope.",
    )
    tools.expect_status(
        lambda: tools.read_json(
            f"{base_url}/{QUALITY_ORGANIZATION_A_ID}/memberships",
            tokens["worker"],
        ),
        403,
        "Worker could list organization memberships.",
    )


def _assert_role_grant_guards(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
) -> None:
    """Reject tenant-admin escalation and any platform membership role.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared request, assertion, and token helpers.

    Returns:
        None: Successful return proves both role grants were rejected.

    Raises:
        BookingServiceQualityError: When a privilege boundary drifts.
    """
    url = (
        f"{runtime.api_origin}/v1/organizations/"
        f"{QUALITY_ORGANIZATION_B_ID}/memberships"
    )
    worker_subject = tools.decode_token(tokens["worker"]).get("sub")
    tools.expect_status(
        lambda: tools.request_json(
            url,
            tokens["organization_admin"],
            method="POST",
            payload={"subject_id": worker_subject, "roles": ["organization_admin"]},
        ),
        403,
        "Organization admin could grant an administrator membership.",
    )
    tools.expect_status(
        lambda: tools.request_json(
            url,
            tokens["platform_admin"],
            method="POST",
            payload={"subject_id": worker_subject, "roles": ["platform_admin"]},
        ),
        422,
        "Membership schema accepted platform-admin access.",
    )


def _assert_last_admin_lockout(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
) -> None:
    """Prove the sole active administrator cannot be revoked.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared request and assertion helpers.

    Returns:
        None: Successful return proves the lockout request was rejected.

    Raises:
        BookingServiceQualityError: When the administrator is absent or mutable.
    """
    base_url = (
        f"{runtime.api_origin}/v1/organizations/"
        f"{QUALITY_ORGANIZATION_A_ID}/memberships"
    )
    memberships = tools.request_json(base_url, tokens["platform_admin"])
    if not isinstance(memberships, list):
        raise BookingServiceQualityError("Membership list shape drifted.")
    administrator = next(
        (item for item in memberships if "organization_admin" in item.get("roles", [])),
        None,
    )
    if not isinstance(administrator, dict):
        raise BookingServiceQualityError("Seeded organization administrator was absent.")
    tools.expect_status(
        lambda: tools.request_json(
            f"{base_url}/{administrator.get('membership_id')}",
            tokens["platform_admin"],
            method="PUT",
            payload={
                "expected_revision": administrator.get("revision"),
                "status": "revoked",
                "roles": ["organization_admin"],
            },
        ),
        409,
        "The final active organization administrator could be revoked.",
    )


def _invite_active_customer(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
) -> tuple[str, dict[str, Any]]:
    """Create a customer membership through real Keycloak role delivery.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared request and token helpers.

    Returns:
        tuple[str, dict[str, Any]]: Customer subject and active response.

    Raises:
        BookingServiceQualityError: When provider delivery or activation drifts.
    """
    base_url = (
        f"{runtime.api_origin}/v1/organizations/"
        f"{QUALITY_ORGANIZATION_A_ID}/memberships"
    )
    subject_id = tools.decode_token(tokens["customer"]).get("sub")
    invited = tools.request_json(
        base_url,
        tokens["organization_admin"],
        method="POST",
        payload={"subject_id": subject_id, "roles": ["customer"]},
    )
    expected_sync = {
        "status": "succeeded",
        "retryable": False,
        "error_code": None,
    }
    if (
        not isinstance(subject_id, str)
        or not isinstance(invited, dict)
        or invited.get("status") != "active"
        or invited.get("identity_sync") != expected_sync
    ):
        raise BookingServiceQualityError("Keycloak-backed invitation activation drifted.")
    return subject_id, invited


def _assert_worker_customer_transition(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
    subject_id: str,
    invited: dict[str, Any],
) -> None:
    """Preserve identity ownership through a live customer-to-worker change.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared request helper.
        subject_id: Immutable invited customer subject.
        invited: Initial active customer membership response.

    Returns:
        None: Successful return proves identity and membership IDs stay stable.

    Raises:
        BookingServiceQualityError: When transition or role delivery drifts.
    """
    base_url = (
        f"{runtime.api_origin}/v1/organizations/"
        f"{QUALITY_ORGANIZATION_A_ID}/memberships"
    )
    membership_id = invited.get("membership_id")
    transitioned = tools.request_json(
        f"{base_url}/{membership_id}",
        tokens["organization_admin"],
        method="PUT",
        payload={
            "expected_revision": invited.get("revision"),
            "status": "active",
            "roles": ["worker"],
        },
    )
    if (
        transitioned.get("membership_id") != membership_id
        or transitioned.get("subject_id") != subject_id
        or transitioned.get("roles") != ["worker"]
        or transitioned.get("identity_sync", {}).get("status") != "succeeded"
    ):
        raise BookingServiceQualityError("Worker/customer ownership transition drifted.")


def _assert_failed_invitation_recovery(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
) -> None:
    """Prove database-first invitation, role transition, and compensation.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared request and assertion helpers.

    Returns:
        None: Successful return proves recoverable app-owned state.

    Raises:
        BookingServiceQualityError: When provider recovery semantics drift.
    """
    base_url = (
        f"{runtime.api_origin}/v1/organizations/"
        f"{QUALITY_ORGANIZATION_B_ID}/memberships"
    )
    subject_id = "quality-missing-provider-subject"
    invited = tools.request_json(
        base_url,
        tokens["organization_admin"],
        method="POST",
        payload={"subject_id": subject_id, "roles": ["customer"]},
    )
    expected_failure = {
        "status": "failed",
        "retryable": False,
        "error_code": "identity_subject_not_found",
    }
    if (
        not isinstance(invited, dict)
        or invited.get("status") != "invited"
        or invited.get("identity_sync") != expected_failure
    ):
        raise BookingServiceQualityError("Database-first invitation recovery drifted.")
    membership_id = invited.get("membership_id")
    retry_url = (
        f"{runtime.api_origin}/v1/organizations/{QUALITY_ORGANIZATION_B_ID}"
        f"/memberships/{membership_id}/retry-identity-sync"
    )
    tools.expect_status(
        lambda: tools.request_json(
            retry_url,
            tokens["organization_admin"],
            method="POST",
        ),
        409,
        "Non-retryable provider configuration failure was retried.",
    )
    _compensate_failed_invitation(
        base_url, tokens, tools, subject_id, invited
    )


def _compensate_failed_invitation(
    base_url: str,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
    subject_id: str,
    invited: dict[str, Any],
) -> None:
    """Revoke one failed invitation while retaining opaque ownership IDs.

    Args:
        base_url: Tenant-scoped membership collection endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared authenticated request helper.
        subject_id: Missing provider subject retained by the invitation.
        invited: Failed invitation response carrying ID and revision.

    Returns:
        None: Successful return proves explicit compensation completed.

    Raises:
        BookingServiceQualityError: When revocation or ownership state drifts.
    """
    membership_id = invited.get("membership_id")
    revoked = tools.request_json(
        f"{base_url}/{membership_id}",
        tokens["organization_admin"],
        method="PUT",
        payload={
            "expected_revision": invited.get("revision"),
            "status": "revoked",
            "roles": ["customer"],
        },
    )
    if (
        revoked.get("status") != "revoked"
        or revoked.get("membership_id") != membership_id
        or revoked.get("subject_id") != subject_id
        or revoked.get("identity_sync", {}).get("status") != "cancelled"
    ):
        raise BookingServiceQualityError("Failed invitation compensation drifted.")


def verify_membership_management(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
    tools: MembershipCheckTools,
) -> None:
    """Run the complete live BKG-103 membership security proof.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.
        tools: Shared request, assertion, and token helpers.

    Returns:
        None: Successful return means all membership gates pass.

    Raises:
        BookingServiceQualityError: When any scoped invariant drifts.
    """
    _assert_scope_guards(runtime, tokens, tools)
    _assert_role_grant_guards(runtime, tokens, tools)
    _assert_last_admin_lockout(runtime, tokens, tools)
    subject_id, invited = _invite_active_customer(runtime, tokens, tools)
    _assert_worker_customer_transition(
        runtime, tokens, tools, subject_id, invited
    )
    _assert_failed_invitation_recovery(runtime, tokens, tools)
