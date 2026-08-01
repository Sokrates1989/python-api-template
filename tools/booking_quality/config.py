"""Build private in-memory configuration for the Booking Service runtime."""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass


PROJECT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
DEFAULT_PROJECT_NAME = "booking-service-quality"
DEFAULT_REALM = "booking-service-example"
DEFAULT_IDENTITY_SPECS = (
    (
        "BOOKING_QUALITY_PLATFORM_ADMIN_USER",
        "booking-platform-admin",
        "BOOKING_QUALITY_PLATFORM_ADMIN_PASSWORD",
        "platform_admin",
    ),
    (
        "BOOKING_QUALITY_ORGANIZATION_ADMIN_USER",
        "booking-organization-admin",
        "BOOKING_QUALITY_ORGANIZATION_ADMIN_PASSWORD",
        "organization_admin",
    ),
    (
        "BOOKING_QUALITY_WORKER_USER",
        "booking-worker",
        "BOOKING_QUALITY_WORKER_PASSWORD",
        "worker",
    ),
    (
        "BOOKING_QUALITY_CUSTOMER_USER",
        "booking-customer",
        "BOOKING_QUALITY_CUSTOMER_PASSWORD",
        "customer",
    ),
)


class BookingServiceQualityError(RuntimeError):
    """Report a safe Booking Service quality-runtime failure."""


@dataclass(frozen=True)
class SeedIdentity:
    """Describe one non-personal Keycloak proof identity.

    Attributes:
        username: Environment-owned neutral login name.
        password: Private password retained only in process memory.
        role: Single booking client role expected in the issued token.
    """

    username: str
    password: str
    role: str


@dataclass(frozen=True)
class QualityRuntime:
    """Hold one invocation's Compose environment and proof identities.

    Attributes:
        environment: Process environment supplied only to Docker Compose.
        identities: Four seeded role identities used by auth verification.
        project_name: Isolated Compose project name used for teardown.
        api_port: Public host port for the selected API.
        keycloak_port: Public host port for the Keycloak fixture.
        sensitive_values: Secret values scanned against retained logs.
    """

    environment: dict[str, str]
    identities: tuple[SeedIdentity, ...]
    project_name: str
    api_port: int
    keycloak_port: int
    sensitive_values: tuple[str, ...]

    @property
    def api_origin(self) -> str:
        """Return the public local API origin.

        Returns:
            str: Loopback HTTP origin using the configured API port.
        """
        return f"http://localhost:{self.api_port}"

    @property
    def issuer_url(self) -> str:
        """Return the public local Keycloak issuer.

        Returns:
            str: Realm issuer used by Flutter and API diagnostics.
        """
        return f"http://localhost:{self.keycloak_port}/realms/{DEFAULT_REALM}"


def _secret_value(environment: Mapping[str, str], name: str) -> str:
    """Resolve an environment secret or generate a strong ephemeral value.

    Args:
        environment: Operator environment considered for an explicit value.
        name: Secret variable name.

    Returns:
        str: Existing non-empty value or a URL-safe generated secret.

    Side Effects:
        Uses the operating-system cryptographic random source when generating.
    """
    explicit = environment.get(name, "").strip()
    return explicit or secrets.token_urlsafe(32)


def _validated_port(environment: Mapping[str, str], name: str, default: int) -> int:
    """Resolve and validate one public quality-runtime port.

    Args:
        environment: Operator environment containing optional overrides.
        name: Public port variable name.
        default: Port used when the variable is absent.

    Returns:
        int: Valid TCP port from 1 through 65535.

    Raises:
        BookingServiceQualityError: When the value is not a valid port.

    Side Effects:
        None.
    """
    raw_value = environment.get(name, str(default)).strip()
    try:
        port = int(raw_value)
    except ValueError as error:
        raise BookingServiceQualityError(f"{name} must be an integer.") from error
    if not 1 <= port <= 65535:
        raise BookingServiceQualityError(f"{name} must be between 1 and 65535.")
    return port


def _build_identities(
    environment: Mapping[str, str],
    require_explicit_passwords: bool,
) -> tuple[SeedIdentity, ...]:
    """Build the four role identities without persisting credentials.

    Args:
        environment: Operator environment supplying optional names/passwords.
        require_explicit_passwords: Require passwords for interactive commands.

    Returns:
        tuple[SeedIdentity, ...]: Platform-admin, organization-admin, worker,
        and customer identities in deterministic order.

    Raises:
        BookingServiceQualityError: When interactive passwords are missing or
        a delimiter would make the Keycloak user specification ambiguous.

    Side Effects:
        Generates ephemeral passwords for automated runs when needed.
    """
    identities: list[SeedIdentity] = []
    for user_key, default_user, password_key, role in DEFAULT_IDENTITY_SPECS:
        username = environment.get(user_key, default_user).strip() or default_user
        explicit_password = environment.get(password_key, "").strip()
        if require_explicit_passwords and not explicit_password:
            raise BookingServiceQualityError(
                f"{password_key} is required for interactive up/verify operations."
            )
        password = explicit_password or secrets.token_urlsafe(24)
        if any(delimiter in username or delimiter in password for delimiter in ":;"):
            raise BookingServiceQualityError(
                f"{user_key} and {password_key} must not contain ':' or ';'."
            )
        if len(password) < 12:
            raise BookingServiceQualityError(
                f"{password_key} must contain at least 12 characters."
            )
        identities.append(SeedIdentity(username, password, role))
    return tuple(identities)


def _populate_public_environment(
    environment: dict[str, str],
    identities: tuple[SeedIdentity, ...],
    api_port: int,
    keycloak_port: int,
    postgres_port: int,
    redis_port: int,
) -> None:
    """Populate public ports and neutral identity names for Compose.

    Args:
        environment: Mutable subprocess environment.
        identities: Ordered seeded identities.
        api_port: Selected public API port.
        keycloak_port: Selected public Keycloak port.
        postgres_port: Selected public PostgreSQL port.
        redis_port: Selected public Redis port.

    Returns:
        None.

    Side Effects:
        Mutates the invocation-local environment mapping.
    """
    environment["BOOKING_QUALITY_API_PORT"] = str(api_port)
    environment["BOOKING_QUALITY_KEYCLOAK_PORT"] = str(keycloak_port)
    environment["BOOKING_QUALITY_POSTGRES_PORT"] = str(postgres_port)
    environment["BOOKING_QUALITY_REDIS_PORT"] = str(redis_port)
    for identity, (user_key, _, password_key, _) in zip(
        identities, DEFAULT_IDENTITY_SPECS, strict=True
    ):
        environment[user_key] = identity.username
        environment[password_key] = identity.password


def _populate_private_environment(
    environment: dict[str, str],
    require_explicit_secrets: bool,
) -> tuple[str, ...]:
    """Populate infrastructure secrets and return their variable names.

    Args:
        environment: Mutable subprocess environment.
        require_explicit_secrets: Require every infrastructure secret to be
            supplied by an interactive caller.

    Returns:
        tuple[str, ...]: Secret keys populated for Compose and log scanning.

    Side Effects:
        Mutates the invocation-local environment mapping.
    """
    secret_keys = (
        "BOOKING_QUALITY_DB_PASSWORD",
        "BOOKING_QUALITY_KEYCLOAK_ADMIN_PASSWORD",
        "BOOKING_QUALITY_ADMIN_API_KEY",
        "BOOKING_QUALITY_RESTORE_API_KEY",
        "BOOKING_QUALITY_DELETE_API_KEY",
    )
    for key in secret_keys:
        if require_explicit_secrets and not environment.get(key, "").strip():
            raise BookingServiceQualityError(
                f"{key} is required for interactive up/verify operations."
            )
        environment[key] = _secret_value(environment, key)
    database_password = environment["BOOKING_QUALITY_DB_PASSWORD"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,}", database_password):
        raise BookingServiceQualityError(
            "BOOKING_QUALITY_DB_PASSWORD must be a 16+ character URL-safe value."
        )
    return secret_keys


def build_quality_runtime(
    require_explicit_secrets: bool = False,
    source_environment: Mapping[str, str] | None = None,
) -> QualityRuntime:
    """Construct one secret-bearing in-memory Compose environment.

    Args:
        require_explicit_secrets: Require proof passwords and infrastructure
            secrets for interactive commands. Automated ``run`` and cleanup
            generate them in memory.
        source_environment: Optional environment seam used by unit tests.

    Returns:
        QualityRuntime: Validated runtime identity, ports, and private values.

    Raises:
        BookingServiceQualityError: When project, port, username, or password
        inputs violate the bounded runtime contract.

    Side Effects:
        Generates cryptographically random ephemeral secrets when absent.
    """
    source = dict(os.environ if source_environment is None else source_environment)
    project_name = source.get("BOOKING_QUALITY_PROJECT_NAME", DEFAULT_PROJECT_NAME)
    if not PROJECT_NAME_PATTERN.fullmatch(project_name):
        raise BookingServiceQualityError(
            "BOOKING_QUALITY_PROJECT_NAME must use 3-63 lowercase project characters."
        )
    api_port = _validated_port(source, "BOOKING_QUALITY_API_PORT", 8084)
    keycloak_port = _validated_port(source, "BOOKING_QUALITY_KEYCLOAK_PORT", 9094)
    postgres_port = _validated_port(source, "BOOKING_QUALITY_POSTGRES_PORT", 5544)
    redis_port = _validated_port(source, "BOOKING_QUALITY_REDIS_PORT", 6384)
    identities = _build_identities(source, require_explicit_secrets)
    environment = dict(source)
    _populate_public_environment(
        environment,
        identities,
        api_port,
        keycloak_port,
        postgres_port,
        redis_port,
    )
    secret_keys = _populate_private_environment(environment, require_explicit_secrets)
    sensitive_values = tuple(
        [identity.password for identity in identities]
        + [environment[key] for key in secret_keys]
    )
    return QualityRuntime(
        environment=environment,
        identities=identities,
        project_name=project_name,
        api_port=api_port,
        keycloak_port=keycloak_port,
        sensitive_values=sensitive_values,
    )
