"""Seed persistent Booking Service development tenants from local Keycloak.

The command authenticates the four neutral demo users only against the fixed
``localhost:9090`` realm, validates their Booking client-role projections, and
passes only opaque subject identifiers to the existing app-owned seed module.
The demo password remains in process memory and is removed from the Docker
Compose child environment.
"""

from __future__ import annotations

import base64
import getpass
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from booking_quality.config import (
    DEFAULT_IDENTITY_SPECS,
    QUALITY_ORGANIZATION_A_ID,
    QUALITY_ORGANIZATION_A_NAME,
    QUALITY_ORGANIZATION_B_ID,
    QUALITY_ORGANIZATION_B_NAME,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_ROOT = REPOSITORY_ROOT / "app" / "apps" / "booking_service" / "development"
COMPOSE_FILE = DEVELOPMENT_ROOT / "compose.yml"
COMPOSE_ENV_FILE = DEVELOPMENT_ROOT / ".env"
KEYCLOAK_ISSUER = "http://localhost:9090/realms/booking-service-example"
TOKEN_URL = f"{KEYCLOAK_ISSUER}/protocol/openid-connect/token"
FRONTEND_CLIENT_ID = "keycloak"
DEMO_PASSWORD_ENV = "BOOKING_LOCAL_DEMO_PASSWORD"


class BookingServiceLocalSeedError(RuntimeError):
    """Report a credential-safe local fixture-seeding failure."""


TokenRequester = Callable[[str, str], str]


def _decode_claims(access_token: str) -> dict[str, Any]:
    """Decode the payload of one local Keycloak JWT.

    Args:
        access_token: Compact JWT retained only in process memory.

    Returns:
        dict[str, Any]: Parsed token-claim object.

    Raises:
        BookingServiceLocalSeedError: When the token payload is malformed.
    """

    try:
        payload = access_token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        claims = json.loads(decoded)
    except (IndexError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise BookingServiceLocalSeedError(
            "Local Keycloak returned a malformed access token."
        ) from error
    if not isinstance(claims, dict):
        raise BookingServiceLocalSeedError(
            "Local Keycloak returned a non-object token payload."
        )
    return claims


def _request_access_token(
    username: str,
    password: str,
    timeout_seconds: float = 10.0,
) -> str:
    """Request one demo-user token from the fixed loopback realm.

    Args:
        username: Neutral reconciler-owned demo username.
        password: Local-only password retained in request memory.
        timeout_seconds: Loopback request timeout; defaults to ten seconds.

    Returns:
        str: Compact access token used only to derive safe claims.

    Raises:
        BookingServiceLocalSeedError: When login fails or no token is returned.

    Side Effects:
        Performs one password-grant request to ``localhost:9090``.
    """

    request = Request(
        TOKEN_URL,
        data=urlencode(
            {
                "client_id": FRONTEND_CLIENT_ID,
                "grant_type": "password",
                "username": username,
                "password": password,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, UnicodeError, json.JSONDecodeError) as error:
        raise BookingServiceLocalSeedError(
            f"Local login failed for demo user '{username}'."
        ) from error
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise BookingServiceLocalSeedError(
            f"Local login returned no access token for demo user '{username}'."
        )
    return token


def _validated_subject(claims: Mapping[str, Any], expected_role: str) -> str:
    """Validate one token projection and return its opaque subject.

    Args:
        claims: Decoded local Keycloak access-token claims.
        expected_role: Booking client role required for this demo persona.

    Returns:
        str: Non-empty opaque Keycloak subject identifier.

    Raises:
        BookingServiceLocalSeedError: When issuer, audience, role, or subject
            claims do not match the persistent realm contract.
    """

    audience = claims.get("aud")
    audience_matches = audience == FRONTEND_CLIENT_ID or (
        isinstance(audience, list) and FRONTEND_CLIENT_ID in audience
    )
    resource_access = claims.get("resource_access")
    client_access = (
        resource_access.get(FRONTEND_CLIENT_ID)
        if isinstance(resource_access, Mapping)
        else None
    )
    roles = client_access.get("roles") if isinstance(client_access, Mapping) else None
    subject = claims.get("sub")
    valid = (
        claims.get("iss") == KEYCLOAK_ISSUER
        and audience_matches
        and isinstance(roles, list)
        and expected_role in roles
        and isinstance(subject, str)
        and bool(subject.strip())
    )
    if not valid:
        raise BookingServiceLocalSeedError(
            f"Local token projection did not match role '{expected_role}'."
        )
    return subject.strip()


def collect_subjects(
    password: str,
    requester: TokenRequester = _request_access_token,
) -> dict[str, str]:
    """Authenticate every demo persona and collect role-to-subject mappings.

    Args:
        password: Shared local-only demo password retained in memory.
        requester: Injectable token requester used by unit tests.

    Returns:
        dict[str, str]: Four Booking roles mapped to opaque Keycloak subjects.

    Raises:
        BookingServiceLocalSeedError: When any login or role projection fails.

    Side Effects:
        Performs four loopback token requests through the default requester.
    """

    subjects: dict[str, str] = {}
    for _, username, _, role in DEFAULT_IDENTITY_SPECS:
        subjects[role] = _validated_subject(
            _decode_claims(requester(username, password)),
            role,
        )
    return subjects


def build_seed_command(subjects: Mapping[str, str]) -> tuple[str, ...]:
    """Build the bounded Compose command for deterministic tenant seeding.

    Args:
        subjects: Complete role-to-Keycloak-subject mapping.

    Returns:
        tuple[str, ...]: Exact Docker Compose argument vector.

    Raises:
        BookingServiceLocalSeedError: When a required subject is absent.
    """

    required_roles = ("platform_admin", "organization_admin", "worker", "customer")
    if any(not str(subjects.get(role, "")).strip() for role in required_roles):
        raise BookingServiceLocalSeedError("All four local demo subjects are required.")
    return (
        "docker",
        "compose",
        "--project-name",
        "booking-service-local",
        "--env-file",
        str(COMPOSE_ENV_FILE),
        "--file",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "api",
        "/app/.venv/bin/python",
        "-m",
        "apps.booking_service.quality.seed_tenancy",
        "--platform-subject",
        subjects["platform_admin"],
        "--organization-admin-subject",
        subjects["organization_admin"],
        "--worker-subject",
        subjects["worker"],
        "--customer-subject",
        subjects["customer"],
        "--organization-a-id",
        QUALITY_ORGANIZATION_A_ID,
        "--organization-a-name",
        QUALITY_ORGANIZATION_A_NAME,
        "--organization-b-id",
        QUALITY_ORGANIZATION_B_ID,
        "--organization-b-name",
        QUALITY_ORGANIZATION_B_NAME,
    )


def run_seed_command(
    command: tuple[str, ...],
    source_environment: Mapping[str, str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> None:
    """Execute the local seed command without forwarding the demo password.

    Args:
        command: Exact bounded Compose argument vector.
        source_environment: Optional process environment; defaults to ``os.environ``.
        runner: Injectable subprocess boundary used by unit tests.

    Returns:
        None: The running API container commits the idempotent fixture.

    Raises:
        BookingServiceLocalSeedError: When the ignored Compose environment is absent.
        subprocess.CalledProcessError: When Compose or the seed module fails.

    Side Effects:
        Executes Docker Compose against the fixed local development project.
    """

    if not COMPOSE_ENV_FILE.is_file():
        raise BookingServiceLocalSeedError(
            "Create app/apps/booking_service/development/.env before seeding."
        )
    child_environment = dict(source_environment or os.environ)
    child_environment.pop(DEMO_PASSWORD_ENV, None)
    runner(
        command,
        cwd=REPOSITORY_ROOT,
        env=child_environment,
        check=True,
    )


def _resolve_password(
    environment: Mapping[str, str],
    prompt: Callable[[str], str] = getpass.getpass,
) -> str:
    """Resolve a sufficiently long local password from memory or a prompt.

    Args:
        environment: Process environment containing an optional local password.
        prompt: Hidden interactive password prompt used when the variable is absent.

    Returns:
        str: Local-only password retained by the current process.

    Raises:
        BookingServiceLocalSeedError: When the value is shorter than twelve characters.

    Side Effects:
        Prompts on the controlling terminal when no environment value exists.
    """

    password = environment.get(DEMO_PASSWORD_ENV, "").strip()
    if not password:
        password = prompt("Booking local demo password: ").strip()
    if len(password) < 12:
        raise BookingServiceLocalSeedError(
            "BOOKING_LOCAL_DEMO_PASSWORD must contain at least 12 characters."
        )
    return password


def main() -> int:
    """Authenticate local personas and seed the persistent demo database.

    Returns:
        int: Zero on success and one after a sanitized recoverable failure.

    Side Effects:
        Prompts for a password, contacts loopback Keycloak, runs Docker Compose,
        and prints a secret-free completion summary.
    """

    try:
        password = _resolve_password(os.environ)
        subjects = collect_subjects(password)
        run_seed_command(build_seed_command(subjects))
    except (BookingServiceLocalSeedError, OSError, subprocess.CalledProcessError) as error:
        print(f"Booking local seed failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "identityCount": len(subjects),
                "organizations": [
                    QUALITY_ORGANIZATION_A_NAME,
                    QUALITY_ORGANIZATION_B_NAME,
                ],
                "status": "seeded",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
