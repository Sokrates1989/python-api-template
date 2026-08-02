"""Seed persistent Booking Service tenants from reconciled local identities.

The command reads the non-secret, environment-specific subject manifest written
by the persistent Keycloak reconciler and passes only validated opaque subject
identifiers to the app-owned seed module. It never authenticates demo users or
reads their credentials.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

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
KEYCLOAK_ORIGIN = "http://localhost:9090"
KEYCLOAK_REALM = "booking-service-example"
DEFAULT_SUBJECT_MANIFEST = (
    REPOSITORY_ROOT.parents[1]
    / "keycloak"
    / "data"
    / "local-realms"
    / KEYCLOAK_REALM
    / "demo-user-subjects.v1.json"
)


class BookingServiceLocalSeedError(RuntimeError):
    """Report a credential-safe local fixture-seeding failure."""


def _read_subject_manifest(path: Path) -> dict[str, Any]:
    """Read one regular JSON subject manifest from the reconciler.

    Args:
        path: Explicit or conventional ignored manifest path.

    Returns:
        Parsed JSON object.

    Raises:
        BookingServiceLocalSeedError: If the path is linked, absent, unreadable,
            malformed, or not an object.
    """

    try:
        if path.is_symlink() or not path.is_file():
            raise BookingServiceLocalSeedError(
                "Run the persistent Keycloak reconciliation before seeding."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BookingServiceLocalSeedError(
            "The local Keycloak subject manifest is unreadable or invalid."
        ) from error
    if not isinstance(payload, dict):
        raise BookingServiceLocalSeedError(
            "The local Keycloak subject manifest must be an object."
        )
    return payload


def _validate_manifest_identity(payload: Mapping[str, Any]) -> None:
    """Validate the stable persistent-realm identity of one manifest.

    Args:
        payload: Parsed subject-manifest object.

    Returns:
        None.

    Raises:
        BookingServiceLocalSeedError: If schema, target, realm, or fingerprint
            does not match the persistent local contract.
    """

    fingerprint = payload.get("contractFingerprint")
    valid_fingerprint = (
        isinstance(fingerprint, str)
        and len(fingerprint) == 64
        and all(character in "0123456789abcdef" for character in fingerprint)
    )
    if not (
        payload.get("schemaVersion") == 1
        and payload.get("kind") == "local-keycloak-demo-user-subjects"
        and payload.get("targetOrigin") == KEYCLOAK_ORIGIN
        and payload.get("realm") == KEYCLOAK_REALM
        and valid_fingerprint
    ):
        raise BookingServiceLocalSeedError(
            "The local Keycloak subject manifest identity is invalid."
        )


def collect_subjects(path: Path) -> dict[str, str]:
    """Load and validate role-to-subject mappings from reconciliation output.

    Args:
        path: Ignored subject-manifest path produced by Keycloak reconciliation.

    Returns:
        Four Booking roles mapped to opaque Keycloak subjects.

    Raises:
        BookingServiceLocalSeedError: If identities, roles, or subjects are
            incomplete, duplicated, or unexpected.
    """

    payload = _read_subject_manifest(path)
    _validate_manifest_identity(payload)
    raw_users = payload.get("users")
    if not isinstance(raw_users, list):
        raise BookingServiceLocalSeedError(
            "The local Keycloak subject manifest users are invalid."
        )
    users = {
        str(item.get("username")): item
        for item in raw_users
        if isinstance(item, dict)
    }
    expected_usernames = {spec[1] for spec in DEFAULT_IDENTITY_SPECS}
    if set(users) != expected_usernames or len(raw_users) != len(users):
        raise BookingServiceLocalSeedError(
            "The local Keycloak subject manifest users do not match the demo contract."
        )
    subjects: dict[str, str] = {}
    for _, username, _, role in DEFAULT_IDENTITY_SPECS:
        item = users[username]
        subject = item.get("subject")
        if (
            set(item) != {"roles", "subject", "username"}
            or item.get("roles") != [role]
            or not isinstance(subject, str)
            or not subject.strip()
        ):
            raise BookingServiceLocalSeedError(
                f"The reconciled identity for '{username}' is invalid."
            )
        subjects[role] = subject.strip()
    if len(set(subjects.values())) != len(subjects):
        raise BookingServiceLocalSeedError(
            "The local Keycloak subject manifest contains duplicate subjects."
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
        "--customer-organization-id",
        QUALITY_ORGANIZATION_A_ID,
    )


def run_seed_command(
    command: tuple[str, ...],
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> None:
    """Execute the bounded local seed command.

    Args:
        command: Exact bounded Compose argument vector.
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
    runner(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the persistent local seed argument parser.

    Returns:
        Parser with an overridable subject-manifest path.
    """

    parser = argparse.ArgumentParser(
        description="Seed Booking Service from reconciled local Keycloak subjects."
    )
    parser.add_argument(
        "--subject-manifest",
        type=Path,
        default=DEFAULT_SUBJECT_MANIFEST,
        help="Subject manifest written by booking_local_realm.py reconcile.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Load reconciled subjects and seed the persistent demo database.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        int: Zero on success and one after a sanitized recoverable failure.

    Side Effects:
        Reads one ignored non-secret manifest, runs Docker Compose, and prints a
        credential-free completion summary.
    """

    arguments = _build_parser().parse_args(argv)
    try:
        subjects = collect_subjects(arguments.subject_manifest)
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
