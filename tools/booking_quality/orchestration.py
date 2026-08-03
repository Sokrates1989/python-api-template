"""Own Docker Compose lifecycle and container checks for Booking quality."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from booking_quality.config import (
    QUALITY_ORGANIZATION_A_ID,
    QUALITY_ORGANIZATION_A_NAME,
    QUALITY_ORGANIZATION_B_ID,
    QUALITY_ORGANIZATION_B_NAME,
    BookingServiceQualityError,
    QualityRuntime,
)
from booking_quality.runtime_checks import (
    assert_health_contract,
    assert_openapi_contract,
    verify_keycloak,
    verify_tenancy,
    wait_for_health,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = (
    REPOSITORY_ROOT
    / "app"
    / "apps"
    / "booking_service"
    / "quality"
    / "compose.yml"
)
FOCUSED_TEST_MODULES = (
    "tests.test_template_v2_backend_foundation_contract",
    "tests.test_template_v2_backend_lifecycle",
    "tests.test_booking_service_pair_contract",
    "tests.test_booking_service_quality",
    "tests.test_booking_service_identity",
    "tests.test_booking_service_tenancy",
    "tests.test_booking_service_memberships",
    "tests.test_booking_service_company_settings",
    "tests.test_booking_service_catalog",
    "tests.test_booking_service_workforce",
    "tests.test_booking_service_discovery",
    "tests.test_booking_service_jwt_contract",
    "tests.test_keycloak_bootstrap_redaction",
    "tests.test_selected_app_route_guard",
)
API_PYTHON = "/app/.venv/bin/python"


def compose_command(runtime: QualityRuntime, *arguments: str) -> list[str]:
    """Build one exact Docker Compose argument vector.

    Args:
        runtime: Runtime containing the isolated project identity.
        arguments: Compose operation and operation-specific arguments.

    Returns:
        list[str]: Shell-free command vector with the fixed Compose file.

    Side Effects:
        None.
    """
    return [
        "docker",
        "compose",
        "--project-name",
        runtime.project_name,
        "--file",
        str(COMPOSE_FILE),
        *arguments,
    ]


def run_compose(
    runtime: QualityRuntime,
    *arguments: str,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run Docker Compose without a shell or command/environment logging.

    Args:
        runtime: Invocation-local Compose environment.
        arguments: Compose operation arguments.
        capture_output: Capture output for private scanning when ``True``.

    Returns:
        subprocess.CompletedProcess[str]: Successful completed process.

    Raises:
        subprocess.CalledProcessError: When Docker Compose exits non-zero.

    Side Effects:
        May create, inspect, execute in, or remove isolated Docker resources.
    """
    return subprocess.run(
        compose_command(runtime, *arguments),
        cwd=REPOSITORY_ROOT,
        env=runtime.environment,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _run_container_checks(runtime: QualityRuntime) -> None:
    """Run route guards and focused repository tests inside Python 3.13.

    Args:
        runtime: Running Compose project.

    Returns:
        None.

    Raises:
        subprocess.CalledProcessError: When a route or focused test fails.

    Side Effects:
        Executes read-only checks inside the selected API container.
    """
    run_compose(
        runtime,
        "exec",
        "-T",
        "api",
        API_PYTHON,
        "/app/tools/validate_selected_app_routes.py",
        "--expected-app-id",
        "booking_service",
        "--forbid-prefix",
        "/records",
    )
    run_compose(
        runtime,
        "exec",
        "-T",
        "api",
        API_PYTHON,
        "-m",
        "unittest",
        *FOCUSED_TEST_MODULES,
    )


def _seed_tenancy(runtime: QualityRuntime, subjects: dict[str, str]) -> None:
    """Seed non-secret tenant fixtures inside the selected API container.

    Args:
        runtime: Running Compose project.
        subjects: Role-to-subject mapping returned by real identity projection.

    Returns:
        None: The standalone seed command commits its fixture transaction.

    Raises:
        subprocess.CalledProcessError: When the seed command fails.

    Side Effects:
        Executes the app-owned seed module inside the disposable API container.
    """
    run_compose(
        runtime,
        "exec",
        "-T",
        "api",
        API_PYTHON,
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


def _assert_logs_redacted(runtime: QualityRuntime) -> None:
    """Fail when any invocation secret appears in retained service logs.

    Args:
        runtime: Running Compose project and sensitive-value inventory.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When a known secret appears in logs.
        subprocess.CalledProcessError: When logs cannot be collected.

    Side Effects:
        Reads service logs into process memory without printing them.
    """
    completed = run_compose(
        runtime,
        "logs",
        "--no-color",
        capture_output=True,
    )
    logs = f"{completed.stdout}\n{completed.stderr}"
    generated_secret = _read_generated_identity_secret(runtime)
    sensitive_values = (*runtime.sensitive_values, generated_secret)
    if any(secret and secret in logs for secret in sensitive_values):
        raise BookingServiceQualityError("Runtime logs contain a secret-bearing value.")


def _read_generated_identity_secret(runtime: QualityRuntime) -> str:
    """Read the ephemeral identity-admin secret only for redaction scanning.

    Args:
        runtime: Running Compose project containing the read-only API mount.

    Returns:
        str: Non-empty generated secret retained only in quality-process memory.

    Raises:
        BookingServiceQualityError: When the disposable handoff is absent.
        subprocess.CalledProcessError: When the bounded container read fails.

    Side Effects:
        Reads one file through the API container without printing its value.
    """
    completed = run_compose(
        runtime,
        "exec",
        "-T",
        "api",
        API_PYTHON,
        "-c",
        (
            "from pathlib import Path; "
            "print(Path('/run/booking-quality-secrets/identity-admin-client').read_text())"
        ),
        capture_output=True,
    )
    secret = completed.stdout.strip()
    if not secret:
        raise BookingServiceQualityError(
            "Generated identity administration secret was unavailable."
        )
    return secret


def start_stack(runtime: QualityRuntime, timeout_seconds: float) -> None:
    """Build/start the isolated stack and validate initial API health.

    Args:
        runtime: Invocation-local Compose environment.
        timeout_seconds: Bounded API readiness wait.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When health does not match the contract.
        subprocess.CalledProcessError: When Compose startup fails.

    Side Effects:
        Builds images and starts isolated containers, network, and volume.
    """
    run_compose(runtime, "up", "--detach", "--build")
    assert_health_contract(wait_for_health(runtime, timeout_seconds), runtime)


def verify_stack(runtime: QualityRuntime, timeout_seconds: float) -> None:
    """Run health, identity, route, test, and log-redaction gates.

    Args:
        runtime: Running quality stack.
        timeout_seconds: Bounded API readiness wait.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When any semantic gate fails.
        subprocess.CalledProcessError: When a container check fails.

    Side Effects:
        Performs local HTTP requests, executes container checks, and reads logs.
    """
    assert_health_contract(wait_for_health(runtime, timeout_seconds), runtime)
    assert_openapi_contract(runtime)
    subjects = verify_keycloak(runtime)
    _seed_tenancy(runtime, subjects)
    verify_tenancy(runtime)
    _run_container_checks(runtime)
    _assert_logs_redacted(runtime)


def stop_stack(runtime: QualityRuntime) -> None:
    """Remove all Compose resources owned by the isolated project.

    Args:
        runtime: Runtime whose project name selects exact Docker resources.

    Returns:
        None.

    Raises:
        subprocess.CalledProcessError: When deterministic teardown fails.

    Side Effects:
        Removes containers, networks, volumes, orphans, and locally built images.
    """
    run_compose(
        runtime,
        "down",
        "--volumes",
        "--remove-orphans",
        "--rmi",
        "local",
    )


def print_summary(runtime: QualityRuntime, status: str) -> None:
    """Print a sanitized endpoint and proof-identity summary.

    Args:
        runtime: Runtime containing public endpoints and identity metadata.
        status: Stable operation outcome label.

    Returns:
        None.

    Side Effects:
        Writes credential-free JSON to stdout.
    """
    print(
        json.dumps(
            {
                "api_origin": runtime.api_origin,
                "identity_count": len(runtime.identities),
                "issuer_url": runtime.issuer_url,
                "project_name": runtime.project_name,
                "roles": [identity.role for identity in runtime.identities],
                "status": status,
                "usernames": [identity.username for identity in runtime.identities],
            },
            sort_keys=True,
        )
    )


def run_with_teardown(runtime: QualityRuntime, timeout_seconds: float) -> None:
    """Start, verify, and always tear down one automated quality stack.

    Args:
        runtime: Ephemeral automated runtime.
        timeout_seconds: Bounded API readiness wait.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When a semantic gate fails.
        subprocess.CalledProcessError: When Compose or a container check fails.

    Side Effects:
        Creates and then removes all isolated Compose resources.
    """
    try:
        start_stack(runtime, timeout_seconds)
        verify_stack(runtime, timeout_seconds)
    finally:
        stop_stack(runtime)
    print_summary(runtime, "verified_and_removed")
