"""Relational validation helpers for production API runtime configuration.

The module validates public browser and Keycloak identity without embedding a
deployment-specific realm, domain, or client ID. Application identity and
secret-file requirements remain owned by :mod:`api.settings`.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import SplitResult, urlsplit


# Keycloak deployment identifiers follow the same conservative grammar as the
# site-profile wizard so independently selected values remain interoperable.
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SAFE_HOSTNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
RESERVED_KEYCLOAK_CLIENT_IDS = frozenset(
    {
        "account",
        "account-console",
        "admin-cli",
        "broker",
        "realm-management",
        "security-admin-console",
    }
)


def _parse_runtime_url(
    value: str,
    field: str,
    *,
    allowed_schemes: frozenset[str],
    public_host_required: bool,
    origin_only: bool,
    exact_origin: bool = False,
) -> tuple[SplitResult | None, list[str]]:
    """Parse one URL and collect production-safe structural violations.

    Args:
        value: Already trimmed URL value.
        field: Environment-field name used in diagnostics.
        allowed_schemes: Permitted lowercase URL schemes.
        public_host_required: Reject local and non-routable IP hosts when true.
        origin_only: Reject non-root paths when true.
        exact_origin: Also reject a trailing slash so browser origins compare
            exactly as emitted by the ``Origin`` header.

    Returns:
        Parsed URL when structurally available and a list of violations.
    """

    errors: list[str] = []
    if not value:
        return None, errors
    if any(character in value for character in ("\\", "\x00", "\r", "\n")):
        return None, [f"{field} contains unsafe characters"]
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        return None, [f"{field} is not a structurally valid URL"]
    if parsed.scheme.lower() not in allowed_schemes or not hostname:
        schemes = " or ".join(sorted(s.upper() for s in allowed_schemes))
        errors.append(f"{field} must be an absolute {schemes} URL")
        return parsed, errors
    if parsed.username or parsed.password:
        errors.append(f"{field} must not contain credentials")
    if parsed.query or parsed.fragment:
        errors.append(f"{field} must not contain a query or fragment")
    try:
        parsed.port
    except ValueError:
        errors.append(f"{field} contains an invalid port")
    hostname = hostname.lower()
    if not SAFE_HOSTNAME_PATTERN.fullmatch(hostname) or ".." in hostname:
        errors.append(f"{field} contains an unsafe hostname")
    if "*" in value or hostname.endswith(".invalid"):
        errors.append(f"{field} must not contain wildcards or placeholders")
    if public_host_required and _host_is_non_public(hostname):
        errors.append(f"{field} must use a public, non-local hostname")
    if origin_only and parsed.path not in {"", "/"}:
        errors.append(f"{field} must be an origin without a path")
    if exact_origin and parsed.path:
        errors.append(f"{field} must not include a trailing slash or path")
    return parsed, errors


def _host_is_non_public(hostname: str) -> bool:
    """Return whether a production hostname is local or non-routable.

    Args:
        hostname: Lowercase hostname parsed from a URL.

    Returns:
        True for localhost names and private, loopback, link-local, reserved,
        or unspecified IP addresses; otherwise false.
    """

    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _identifier_errors(
    value: str,
    field: str,
    *,
    forbidden: frozenset[str] = frozenset(),
) -> list[str]:
    """Collect conservative identifier-format and reserved-name violations.

    Args:
        value: Trimmed realm, client, or audience identifier.
        field: Environment-field name used in diagnostics.
        forbidden: Exact identifiers that the field must not use.

    Returns:
        A list containing zero or one validation message.
    """

    if not value:
        return []
    if not SAFE_IDENTIFIER_PATTERN.fullmatch(value):
        return [
            f"{field} must be a lowercase safe identifier using letters, "
            "digits, dots, underscores, or hyphens"
        ]
    if value in forbidden:
        return [f"{field} uses a protected Keycloak identifier"]
    return []


def collect_production_cors_errors(origins: list[str]) -> list[str]:
    """Validate one or more exact public HTTPS browser origins.

    Args:
        origins: Parsed ``CORS_ORIGINS`` values in operator order.

    Returns:
        Production CORS violations, or an empty list for safe origins.
    """

    if not origins:
        return ["CORS_ORIGINS must contain at least one public HTTPS origin"]
    errors: list[str] = []
    if len(set(origins)) != len(origins):
        errors.append("CORS_ORIGINS must not contain duplicate origins")
    for index, origin in enumerate(origins):
        _, origin_errors = _parse_runtime_url(
            origin,
            f"CORS_ORIGINS[{index}]",
            allowed_schemes=frozenset({"https"}),
            public_host_required=True,
            origin_only=True,
            exact_origin=True,
        )
        errors.extend(origin_errors)
    return errors


def collect_production_keycloak_errors(
    *,
    server_url: str,
    internal_url: str,
    realm: str,
    frontend_client_id: str,
    issuer_url: str,
    jwks_url: str,
    enforce_audience: bool,
    audience: str,
    backend_client_id: str,
    backend_secret_file: str,
) -> list[str]:
    """Validate strict Keycloak fields through safety and relationships.

    Args:
        server_url: Public Keycloak origin.
        internal_url: Optional private-network Keycloak origin used for JWKS.
        realm: Operator-selected application realm.
        frontend_client_id: Public WebApp/mobile client identifier.
        issuer_url: Explicit public issuer URL.
        jwks_url: Explicit JWKS endpoint used by the API.
        enforce_audience: Whether bearer-token audience checks are enabled.
        audience: Required API token audience.
        backend_client_id: Confidential service-account client identifier.
        backend_secret_file: Mounted backend-client secret path.

    Returns:
        Keycloak contract violations, or an empty list when the complete
        non-default identity is coherent and production-safe.
    """

    values = {
        "KEYCLOAK_SERVER_URL": server_url,
        "KEYCLOAK_REALM": realm,
        "KEYCLOAK_CLIENT_ID": frontend_client_id,
        "KEYCLOAK_ISSUER_URL": issuer_url,
        "KEYCLOAK_JWKS_URL": jwks_url,
        "KEYCLOAK_AUDIENCE": audience,
        "KEYCLOAK_ADMIN_CLIENT_ID": backend_client_id,
        "KEYCLOAK_ADMIN_CLIENT_SECRET_FILE": backend_secret_file,
    }
    missing = [name for name, value in values.items() if not value]
    errors = (
        ["missing production Keycloak settings: " + ", ".join(missing)]
        if missing
        else []
    )
    _, server_errors = _parse_runtime_url(
        server_url,
        "KEYCLOAK_SERVER_URL",
        allowed_schemes=frozenset({"https"}),
        public_host_required=True,
        origin_only=True,
    )
    errors.extend(server_errors)
    if internal_url:
        _, internal_errors = _parse_runtime_url(
            internal_url,
            "KEYCLOAK_INTERNAL_URL",
            allowed_schemes=frozenset({"http", "https"}),
            public_host_required=False,
            origin_only=True,
        )
        errors.extend(internal_errors)
    errors.extend(
        _collect_keycloak_identity_errors(
            realm=realm,
            frontend_client_id=frontend_client_id,
            audience=audience,
            backend_client_id=backend_client_id,
        )
    )
    errors.extend(
        _collect_keycloak_endpoint_errors(
            server_url=server_url,
            internal_url=internal_url,
            realm=realm,
            issuer_url=issuer_url,
            jwks_url=jwks_url,
        )
    )
    if not enforce_audience:
        errors.append("KEYCLOAK_ENFORCE_AUDIENCE must be enabled")
    return errors


def _collect_keycloak_identity_errors(
    *,
    realm: str,
    frontend_client_id: str,
    audience: str,
    backend_client_id: str,
) -> list[str]:
    """Validate realm/client syntax and identity separation.

    Args:
        realm: Selected application realm.
        frontend_client_id: Public WebApp/mobile client identifier.
        audience: Required API token audience.
        backend_client_id: Confidential service-account client identifier.

    Returns:
        Identifier safety and relational-separation violations.
    """

    errors = _identifier_errors(
        realm,
        "KEYCLOAK_REALM",
        forbidden=frozenset({"master"}),
    )
    for value, field in (
        (frontend_client_id, "KEYCLOAK_CLIENT_ID"),
        (backend_client_id, "KEYCLOAK_ADMIN_CLIENT_ID"),
        (audience, "KEYCLOAK_AUDIENCE"),
    ):
        errors.extend(
            _identifier_errors(
                value,
                field,
                forbidden=RESERVED_KEYCLOAK_CLIENT_IDS,
            )
        )
    if frontend_client_id and frontend_client_id == backend_client_id:
        errors.append("Keycloak frontend and backend client IDs must differ")
    if frontend_client_id and frontend_client_id == audience:
        errors.append("KEYCLOAK_AUDIENCE must differ from the frontend client ID")
    return errors


def _collect_keycloak_endpoint_errors(
    *,
    server_url: str,
    internal_url: str,
    realm: str,
    issuer_url: str,
    jwks_url: str,
) -> list[str]:
    """Validate issuer and JWKS URLs against their selected base and realm.

    Args:
        server_url: Public Keycloak origin.
        internal_url: Optional internal Keycloak origin.
        realm: Selected realm identifier.
        issuer_url: Public token issuer.
        jwks_url: Token-verification key endpoint.

    Returns:
        Endpoint safety and relationship violations.
    """

    errors: list[str] = []
    if issuer_url:
        _, issuer_errors = _parse_runtime_url(
            issuer_url,
            "KEYCLOAK_ISSUER_URL",
            allowed_schemes=frozenset({"https"}),
            public_host_required=True,
            origin_only=False,
        )
        errors.extend(issuer_errors)
    if jwks_url:
        _, jwks_errors = _parse_runtime_url(
            jwks_url,
            "KEYCLOAK_JWKS_URL",
            allowed_schemes=(
                frozenset({"http", "https"})
                if internal_url
                else frozenset({"https"})
            ),
            public_host_required=not bool(internal_url),
            origin_only=False,
        )
        errors.extend(jwks_errors)
    if server_url and realm and issuer_url:
        expected_issuer = f"{server_url.rstrip('/')}/realms/{realm}"
        if issuer_url != expected_issuer:
            errors.append(
                "KEYCLOAK_ISSUER_URL must match KEYCLOAK_SERVER_URL and "
                "KEYCLOAK_REALM"
            )
    if (internal_url or server_url) and realm and jwks_url:
        key_base = (internal_url or server_url).rstrip("/")
        expected_jwks = (
            f"{key_base}/realms/{realm}/protocol/openid-connect/certs"
        )
        if jwks_url != expected_jwks:
            errors.append(
                "KEYCLOAK_JWKS_URL must match the selected Keycloak base "
                "URL and KEYCLOAK_REALM"
            )
    return errors
