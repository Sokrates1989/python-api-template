"""Validate live API and Keycloak behavior for the disposable quality stack."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from booking_quality.config import BookingServiceQualityError, QualityRuntime


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
    if payload.get("registered_route_prefixes") != []:
        raise BookingServiceQualityError("Detached product route prefixes are still registered.")
    if (
        keycloak.get("configured") is not True
        or keycloak.get("issuer") != runtime.issuer_url
        or keycloak.get("audience") != "keycloak"
        or keycloak.get("audience_enforced") is not True
    ):
        raise BookingServiceQualityError("API Keycloak health configuration drifted.")


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


def _decode_realm_roles(access_token: str) -> tuple[str, ...]:
    """Decode unverified roles solely to prove deterministic fixture seeding.

    Args:
        access_token: JWT issued directly by the isolated Keycloak fixture.

    Returns:
        tuple[str, ...]: Sorted realm roles embedded in the token payload.

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
        roles = payload["realm_access"]["roles"]
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise BookingServiceQualityError("Keycloak returned a malformed fixture token.") from error
    return tuple(sorted(str(role) for role in roles))


def verify_keycloak(runtime: QualityRuntime) -> None:
    """Verify discovery identity and each seeded role without retaining tokens.

    Args:
        runtime: Runtime containing issuer and private proof identities.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When issuer, token, or role seeding drifts.

    Side Effects:
        Fetches discovery and four short-lived local access tokens.
    """
    try:
        _verify_keycloak_fixture(runtime)
    except BookingServiceQualityError:
        raise
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
        raise BookingServiceQualityError(
            "Keycloak fixture verification could not complete."
        ) from error


def _verify_keycloak_fixture(runtime: QualityRuntime) -> None:
    """Execute discovery and role-token checks for a reachable fixture.

    Args:
        runtime: Runtime containing issuer and private proof identities.

    Returns:
        None.

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
        if not isinstance(token, str) or identity.role not in _decode_realm_roles(token):
            raise BookingServiceQualityError("Seeded Keycloak role proof failed.")
