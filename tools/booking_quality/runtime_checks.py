"""Validate live API and Keycloak behavior for the disposable quality stack."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from booking_quality.config import (
    QUALITY_ORGANIZATION_A_ID,
    QUALITY_ORGANIZATION_B_ID,
    BookingServiceQualityError,
    QualityRuntime,
    SeedIdentity,
)
from booking_quality.company_settings_checks import (
    CompanySettingsCheckTools,
    verify_company_settings,
)
from booking_quality.membership_checks import (
    MembershipCheckTools,
    verify_membership_management,
)
from booking_quality.service_catalog_checks import (
    ServiceCatalogCheckTools,
    verify_service_catalog,
)


def read_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Fetch and parse one local JSON endpoint.

    Args:
        url: Loopback endpoint URL.
        timeout_seconds: Per-request timeout; defaults to five seconds.

    Returns:
        dict[str, Any]: Parsed JSON object.

    Raises:
        BookingServiceQualityError: When Keycloak rejects the credentials or
        returns a non-object response.
        HTTPError: When the endpoint returns an HTTP error.
        URLError: When the endpoint cannot be reached.

    Side Effects:
        Performs one loopback HTTP GET request.
    """
    with urlopen(url, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise BookingServiceQualityError("Quality endpoint returned a non-object payload.")
    return payload


def read_bearer_json(
    url: str,
    access_token: str,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Fetch one local JSON object with an in-memory bearer token.

    Args:
        url: Loopback Booking API endpoint.
        access_token: Short-lived fixture token retained only in request memory.
        timeout_seconds: Per-request timeout; defaults to five seconds.

    Returns:
        dict[str, Any]: Parsed JSON object.

    Raises:
        BookingServiceQualityError: When the response is not a JSON object.
        HTTPError: When the API rejects the token or request.
        URLError: When the API cannot be reached.

    Side Effects:
        Performs one loopback HTTP GET request without logging the token.
    """
    payload = _request_bearer_json(url, access_token, timeout_seconds=timeout_seconds)
    if not isinstance(payload, dict):
        raise BookingServiceQualityError("Identity endpoint returned a non-object payload.")
    return payload


def _request_bearer_json(
    url: str,
    access_token: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    timeout_seconds: float = 5.0,
) -> Any:
    """Perform one authenticated JSON request without logging its token.

    Args:
        url: Loopback Booking API endpoint.
        access_token: Short-lived fixture token retained only in request memory.
        method: HTTP method; defaults to ``GET``.
        payload: Optional JSON object encoded as the request body.
        timeout_seconds: Per-request timeout; defaults to five seconds.

    Returns:
        Any: Parsed JSON response, which may be an object or list.

    Raises:
        HTTPError: When the API returns an error status.
        URLError: When the local API cannot be reached.
        JSONDecodeError: When the response is not valid JSON.

    Side Effects:
        Performs one loopback HTTP request with an in-memory bearer token.
    """
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {access_token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health(runtime: QualityRuntime, timeout_seconds: float) -> dict[str, Any]:
    """Wait through transient socket failures for the selected API health.

    Args:
        runtime: Runtime containing the local API origin.
        timeout_seconds: Total startup wait bound.

    Returns:
        dict[str, Any]: First successful health object.

    Raises:
        BookingServiceQualityError: When the API remains unavailable.

    Side Effects:
        Performs bounded loopback requests and short sleeps.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            return read_json(f"{runtime.api_origin}/health")
        except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError):
            time.sleep(2.0)
    raise BookingServiceQualityError("Booking Service API did not become healthy in time.")


def assert_health_contract(
    payload: Mapping[str, Any],
    runtime: QualityRuntime,
) -> None:
    """Validate selected app, migration, route, and auth health diagnostics.

    Args:
        payload: API ``/health`` response.
        runtime: Expected local issuer and selected-app identity.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When any runtime contract field drifts.

    Side Effects:
        None.
    """
    expected = {
        "status": "OK",
        "app_profile": "booking_service",
        "backend_app_id": "booking_service",
        "build_backend_app_id": "booking_service",
        "backend_data_profile": "postgresql",
        "provider_profile": "sql",
        "migration_status": "success",
        "startup_complete": True,
        "auth_provider": "keycloak",
    }
    drift = {
        key: (value, payload.get(key))
        for key, value in expected.items()
        if payload.get(key) != value
    }
    keycloak = payload.get("keycloak")
    if drift or not isinstance(keycloak, Mapping):
        raise BookingServiceQualityError("API health identity or migration contract drifted.")
    expected_prefixes = [
        "/v1/me",
        "/v1/platform/organizations",
        "/v1/organizations",
    ]
    if payload.get("registered_route_prefixes") != expected_prefixes:
        raise BookingServiceQualityError("Booking route registration drifted.")
    if (
        keycloak.get("configured") is not True
        or keycloak.get("issuer") != runtime.issuer_url
        or keycloak.get("audience") != "keycloak"
        or keycloak.get("audience_enforced") is not True
    ):
        raise BookingServiceQualityError("API Keycloak health configuration drifted.")


def assert_openapi_contract(runtime: QualityRuntime) -> None:
    """Validate the selected Booking Service OpenAPI identity.

    Args:
        runtime: Runtime containing the local API origin.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When the schema omits or misbrands its
            public title or description.
        HTTPError: When the API rejects the schema request.
        URLError: When the API cannot be reached.

    Side Effects:
        Performs one loopback HTTP GET request to ``/openapi.json``.
    """
    payload = read_json(f"{runtime.api_origin}/openapi.json")
    info = payload.get("info")
    expected = {
        "title": "Booking Service",
        "description": (
            "A neutral multi-tenant foundation for general service booking."
        ),
    }
    if not isinstance(info, Mapping) or any(
        info.get(field) != value for field, value in expected.items()
    ):
        raise BookingServiceQualityError("Booking OpenAPI identity drifted.")


def _post_form_json(url: str, fields: Mapping[str, str]) -> dict[str, Any]:
    """Post URL-encoded fields and parse a JSON object response.

    Args:
        url: Local Keycloak token endpoint.
        fields: Form fields including private credentials.

    Returns:
        dict[str, Any]: Parsed token response retained only in memory.

    Raises:
        BookingServiceQualityError: When Keycloak rejects the credentials or
        returns a non-object response.

    Side Effects:
        Performs one loopback HTTP POST request.
    """
    request = Request(
        url,
        data=urlencode(fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            error_payload = json.loads(error.read().decode("utf-8"))
            raw_error_code = str(error_payload.get("error", ""))
            error_code = (
                raw_error_code
                if raw_error_code
                in {"invalid_client", "invalid_grant", "unauthorized_client"}
                else "keycloak_error"
            )
            description = str(error_payload.get("error_description", "")).lower()
            if "account is not fully set up" in description:
                error_code = f"{error_code}:account_incomplete"
            elif "invalid user credentials" in description:
                error_code = f"{error_code}:invalid_credentials"
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
            error_code = "http_error"
        raise BookingServiceQualityError(
            f"Keycloak token request was rejected ({error.code}:{error_code})."
        ) from error
    if not isinstance(payload, dict):
        raise BookingServiceQualityError("Keycloak returned a non-object token payload.")
    return payload


def _decode_token_payload(access_token: str) -> dict[str, Any]:
    """Decode one unverified fixture token solely for local seed assertions.

    Args:
        access_token: JWT issued directly by the isolated Keycloak fixture.

    Returns:
        dict[str, Any]: Decoded local payload used only as expected test input.

    Raises:
        BookingServiceQualityError: When the local fixture token is malformed.

    Note:
        This is not authorization. Production token verification remains in
        the backend auth boundary; BKG-004 uses decoding only for seed proof.
    """
    try:
        encoded_payload = access_token.split(".")[1]
        padding = "=" * (-len(encoded_payload) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload + padding))
    except (IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise BookingServiceQualityError("Keycloak returned a malformed fixture token.") from error
    if not isinstance(payload, dict):
        raise BookingServiceQualityError("Keycloak returned a non-object fixture token.")
    return payload


def _decode_client_roles(access_token: str, client_id: str) -> tuple[str, ...]:
    """Read sorted client roles from a local unverified fixture token.

    Args:
        access_token: JWT issued directly by the isolated Keycloak fixture.
        client_id: Exact client role container expected in ``resource_access``.

    Returns:
        tuple[str, ...]: Sorted role strings from the configured client.

    Raises:
        BookingServiceQualityError: When the fixture token shape is malformed.

    Note:
        This helper is not authorization. The API independently verifies the
        token before building its Booking principal.
    """
    try:
        roles = _decode_token_payload(access_token)["resource_access"][client_id]["roles"]
    except (KeyError, TypeError) as error:
        raise BookingServiceQualityError("Keycloak omitted Booking client roles.") from error
    if not isinstance(roles, list):
        raise BookingServiceQualityError("Keycloak returned malformed Booking client roles.")
    return tuple(sorted(str(role) for role in roles))


def _has_audience(payload: Mapping[str, Any], audience: str) -> bool:
    """Return whether one decoded fixture payload contains an audience.

    Args:
        payload: Decoded local JWT payload used only for expected assertions.
        audience: Exact audience required by the Booking API.

    Returns:
        bool: True for a matching string or list member; otherwise false.
    """
    raw_audience = payload.get("aud")
    if isinstance(raw_audience, str):
        return raw_audience == audience
    return isinstance(raw_audience, list) and audience in raw_audience


def _verify_seeded_identity(
    runtime: QualityRuntime,
    access_token: str,
    expected_role: str,
) -> None:
    """Verify one seeded client role through the real Booking API.

    Args:
        runtime: Runtime containing the local API origin.
        access_token: Short-lived Keycloak token retained only in memory.
        expected_role: Sole booking client role expected for the proof user.

    Raises:
        BookingServiceQualityError: When audience, claims, or projection drift.

    Side Effects:
        Performs one authenticated loopback request to ``/v1/me/identity``.
    """
    payload = _decode_token_payload(access_token)
    if expected_role not in _decode_client_roles(access_token, "keycloak"):
        raise BookingServiceQualityError("Seeded Keycloak client-role proof failed.")
    if not _has_audience(payload, "keycloak"):
        raise BookingServiceQualityError("Seeded Keycloak audience proof failed.")
    projection = read_bearer_json(
        f"{runtime.api_origin}/v1/me/identity",
        access_token,
    )
    if projection.get("subject_id") != payload.get("sub"):
        raise BookingServiceQualityError("Booking identity subject projection drifted.")
    if projection.get("roles") != [expected_role]:
        raise BookingServiceQualityError("Booking identity role projection drifted.")


def verify_keycloak(runtime: QualityRuntime) -> dict[str, str]:
    """Verify discovery identity and each seeded role without retaining tokens.

    Args:
        runtime: Runtime containing issuer and private proof identities.

    Returns:
        dict[str, str]: Safe mapping from each seeded role to the real Keycloak
        subject projected by the API. Tokens are not returned.

    Raises:
        BookingServiceQualityError: When issuer, token, or role seeding drifts.

    Side Effects:
        Fetches discovery and four short-lived local access tokens.
    """
    try:
        return _verify_keycloak_fixture(runtime)
    except BookingServiceQualityError:
        raise
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
        raise BookingServiceQualityError(
            "Keycloak fixture verification could not complete."
        ) from error


def _verify_keycloak_fixture(runtime: QualityRuntime) -> dict[str, str]:
    """Execute discovery and role-token checks for a reachable fixture.

    Args:
        runtime: Runtime containing issuer and private proof identities.

    Returns:
        dict[str, str]: Safe role-to-subject mapping used by tenancy seeding.

    Raises:
        BookingServiceQualityError: When issuer, token, or role seeding drifts.
        HTTPError: When Keycloak returns an unexpected HTTP error.
        URLError: When the local Keycloak endpoint is unavailable.

    Side Effects:
        Fetches discovery and four short-lived local access tokens.
    """
    discovery = read_json(f"{runtime.issuer_url}/.well-known/openid-configuration")
    if discovery.get("issuer") != runtime.issuer_url:
        raise BookingServiceQualityError("Keycloak discovery issuer drifted.")
    token_endpoint = discovery.get("token_endpoint")
    if not isinstance(token_endpoint, str) or not token_endpoint:
        raise BookingServiceQualityError("Keycloak discovery omitted token_endpoint.")
    try:
        read_json(f"{runtime.api_origin}/v1/me/identity")
    except HTTPError as error:
        if error.code != 401:
            raise BookingServiceQualityError(
                "Anonymous Booking identity request returned an unexpected status."
            ) from error
    else:
        raise BookingServiceQualityError("Anonymous Booking identity request did not fail closed.")
    subjects: dict[str, str] = {}
    for identity in runtime.identities:
        response = _post_form_json(
            token_endpoint,
            {
                "grant_type": "password",
                "client_id": "keycloak",
                "username": identity.username,
                "password": identity.password,
            },
        )
        token = response.get("access_token")
        if not isinstance(token, str):
            raise BookingServiceQualityError("Keycloak omitted a fixture access token.")
        _verify_seeded_identity(runtime, token, identity.role)
        subject_id = _decode_token_payload(token).get("sub")
        if not isinstance(subject_id, str) or not subject_id:
            raise BookingServiceQualityError("Keycloak omitted a fixture subject.")
        subjects[identity.role] = subject_id
    return subjects


def _access_token(runtime: QualityRuntime, identity: SeedIdentity) -> str:
    """Obtain one short-lived fixture token for a bounded live proof.

    Args:
        runtime: Runtime containing the local issuer endpoint.
        identity: Non-personal seeded identity and in-memory password.

    Returns:
        str: Short-lived access token retained only by the caller.

    Raises:
        BookingServiceQualityError: When Keycloak omits the token.

    Side Effects:
        Performs one local password-grant request to the disposable realm.
    """
    response = _post_form_json(
        f"{runtime.issuer_url}/protocol/openid-connect/token",
        {
            "grant_type": "password",
            "client_id": "keycloak",
            "username": identity.username,
            "password": identity.password,
        },
    )
    token = response.get("access_token")
    if not isinstance(token, str):
        raise BookingServiceQualityError("Keycloak omitted a fixture access token.")
    return token


def _context(runtime: QualityRuntime, token: str) -> dict[str, Any]:
    """Read one effective context through the real authenticated API.

    Args:
        runtime: Runtime containing the local API endpoint.
        token: Short-lived fixture token retained only in request memory.

    Returns:
        dict[str, Any]: Parsed effective context response.
    """
    return read_bearer_json(f"{runtime.api_origin}/v1/me/context", token)


def _assert_context_memberships(
    runtime: QualityRuntime,
    tokens: Mapping[str, str],
) -> None:
    """Prove platform dual-gating and active multi-tenant context projection.

    Args:
        runtime: Runtime containing the local API endpoint.
        tokens: Role-keyed short-lived tokens retained only for this proof.

    Returns:
        None: Successful return means context projections match seed policy.

    Raises:
        BookingServiceQualityError: When capabilities or membership scopes drift.
    """
    platform = _context(runtime, tokens["platform_admin"])
    if platform.get("platform_capabilities") != ["manage_platform_organizations"]:
        raise BookingServiceQualityError("Platform dual-gate capability proof failed.")
    expected_ids = {
        "organization_admin": [QUALITY_ORGANIZATION_A_ID, QUALITY_ORGANIZATION_B_ID],
        "worker": [QUALITY_ORGANIZATION_A_ID],
        "customer": [],
    }
    for role, organization_ids in expected_ids.items():
        projected = _context(runtime, tokens[role]).get("organizations")
        if not isinstance(projected, list):
            raise BookingServiceQualityError("Organization context shape drifted.")
        observed = [item.get("organization", {}).get("organization_id") for item in projected]
        if observed != organization_ids:
            raise BookingServiceQualityError("Organization context isolation proof failed.")


def _expect_http_status(
    operation: Callable[[], object],
    expected_status: int,
    message: str,
) -> None:
    """Require a callable HTTP proof to fail with one exact status.

    Args:
        operation: Zero-argument callable performing the local HTTP operation.
        expected_status: Exact safe response status required by the proof.
        message: Sanitized failure message raised when the status drifts.

    Returns:
        None: Successful return means the expected HTTP error was observed.

    Raises:
        BookingServiceQualityError: When no error or a different status occurs.
    """
    try:
        operation()
    except HTTPError as error:
        if error.code == expected_status:
            return
        raise BookingServiceQualityError(message) from error
    raise BookingServiceQualityError(message)


def _assert_member_isolation(runtime: QualityRuntime, worker_token: str) -> None:
    """Prove scoped reads allow one tenant and hide a guessed foreign tenant.

    Args:
        runtime: Runtime containing the local API endpoint.
        worker_token: Worker token with membership only in organization A.

    Returns:
        None: Successful return proves allowed and foreign read behavior.

    Raises:
        BookingServiceQualityError: When allowed read or safe 404 behavior drifts.
    """
    allowed = read_bearer_json(
        f"{runtime.api_origin}/v1/organizations/{QUALITY_ORGANIZATION_A_ID}",
        worker_token,
    )
    if allowed.get("organization_id") != QUALITY_ORGANIZATION_A_ID:
        raise BookingServiceQualityError("Authorized organization read proof failed.")
    _expect_http_status(
        lambda: read_bearer_json(
            f"{runtime.api_origin}/v1/organizations/{QUALITY_ORGANIZATION_B_ID}",
            worker_token,
        ),
        404,
        "Foreign organization lookup did not fail with safe not-found semantics.",
    )


def _assert_platform_lifecycle(
    runtime: QualityRuntime,
    platform_token: str,
    worker_token: str,
) -> None:
    """Prove audited lifecycle, stale protection, suspension, and restoration.

    Args:
        runtime: Runtime containing the local API endpoint.
        platform_token: Dual-authorized platform administrator token.
        worker_token: Worker token scoped to organization A.

    Returns:
        None: Successful return proves the lifecycle behavior end to end.

    Raises:
        BookingServiceQualityError: When lifecycle or suspension semantics drift.
    """
    base_url = f"{runtime.api_origin}/v1/platform/organizations"
    organizations = _request_bearer_json(base_url, platform_token)
    if not isinstance(organizations, list):
        raise BookingServiceQualityError("Platform organization list shape drifted.")
    organization_a = next(
        (item for item in organizations if item.get("organization_id") == QUALITY_ORGANIZATION_A_ID),
        None,
    )
    if not isinstance(organization_a, dict):
        raise BookingServiceQualityError("Seeded organization was not listed.")
    created = _request_bearer_json(
        base_url,
        platform_token,
        method="POST",
        payload={"display_name": "Booking Quality Created"},
    )
    if not isinstance(created, dict) or created.get("status") != "active":
        raise BookingServiceQualityError("Platform organization creation proof failed.")
    suspended = _request_bearer_json(
        f"{base_url}/{QUALITY_ORGANIZATION_A_ID}/suspend",
        platform_token,
        method="POST",
        payload={"expected_revision": organization_a.get("revision")},
    )
    if not isinstance(suspended, dict) or suspended.get("status") != "suspended":
        raise BookingServiceQualityError("Organization suspension proof failed.")
    if _context(runtime, worker_token).get("organizations") != []:
        raise BookingServiceQualityError("Suspended organization remained in context.")
    _expect_http_status(
        lambda: read_bearer_json(
            f"{runtime.api_origin}/v1/organizations/{QUALITY_ORGANIZATION_A_ID}", worker_token
        ),
        403,
        "Suspended organization operation did not fail closed.",
    )
    reactivated = _request_bearer_json(
        f"{base_url}/{QUALITY_ORGANIZATION_A_ID}/reactivate",
        platform_token,
        method="POST",
        payload={"expected_revision": suspended.get("revision")},
    )
    if not isinstance(reactivated, dict) or reactivated.get("status") != "active":
        raise BookingServiceQualityError("Organization reactivation proof failed.")
    if len(_context(runtime, worker_token).get("organizations", [])) != 1:
        raise BookingServiceQualityError("Reactivated organization context was not restored.")


def verify_tenancy(runtime: QualityRuntime) -> None:
    """Run real Keycloak/API/PostgreSQL BKG-101 authorization proofs.

    Args:
        runtime: Running disposable quality stack.

    Returns:
        None: Tokens leave scope after all assertions complete.

    Raises:
        BookingServiceQualityError: When context, isolation, or lifecycle drifts.

    Side Effects:
        Obtains short-lived local tokens and performs bounded API operations.
    """
    _expect_http_status(
        lambda: read_json(f"{runtime.api_origin}/v1/me/context"),
        401,
        "Anonymous Booking context request did not fail closed.",
    )
    tokens = {
        identity.role: _access_token(runtime, identity)
        for identity in runtime.identities
    }
    _assert_context_memberships(runtime, tokens)
    _assert_member_isolation(runtime, tokens["worker"])
    _assert_platform_lifecycle(
        runtime,
        tokens["platform_admin"],
        tokens["worker"],
    )
    membership_tools = MembershipCheckTools(
        _request_bearer_json, read_bearer_json, _expect_http_status, _decode_token_payload
    )
    verify_membership_management(runtime, tokens, membership_tools)
    company_tools = CompanySettingsCheckTools(
        _request_bearer_json,
        read_bearer_json,
        _expect_http_status,
    )
    verify_company_settings(runtime, tokens, company_tools)
    catalog_tools = ServiceCatalogCheckTools(
        _request_bearer_json,
        read_bearer_json,
        _expect_http_status,
    )
    verify_service_catalog(runtime, tokens, catalog_tools)
