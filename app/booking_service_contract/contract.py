"""Validate the Python-owned Booking Service pair compatibility contract.

The module is dependency-free so target-creation preflight can fail closed
before backend dependencies, generated targets, provider resources, or
credentials exist. It also renders the stable OpenAPI info-extension identity
that the future booking backend will publish.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit


CONTRACT_RELATIVE_PATH = "app/booking_service_contract/pair_contract.json"
SUPPORTED_CONTRACT_ID = "booking-service-pair"
SUPPORTED_CONTRACT_VERSION = 1
SUPPORTED_CONTRACT_REVISION = "1.0.0"
SUPPORTED_CONTRACT_SEMANTIC_SHA256 = (
    "b4ce3052502af7d2d7e9a82ecafc7c68ee76d66b0df1028d1f2028e207dc3250"
)
_MAX_CONTRACT_BYTES = 128_000
_APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_ANDROID_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_FORBIDDEN_FIELD_FRAGMENTS = (
    "access_token",
    "client_secret",
    "credential",
    "password",
    "private_key",
    "refresh_token",
)


class BookingServiceContractError(ValueError):
    """Report one or more sanitized pair-contract validation failures.

    Attributes:
        issues: Stable sorted diagnostics without contract values or paths.
    """

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        """Initialize an aggregate validation error.

        Args:
            issues: Non-empty validation diagnostics.

        Raises:
            ValueError: If no diagnostic is supplied.
        """

        normalized = tuple(sorted(set(issues)))
        if not normalized:
            raise ValueError("BookingServiceContractError requires an issue")
        self.issues = normalized
        super().__init__("\n".join(normalized))


@dataclass(frozen=True)
class BookingServiceContractIdentity:
    """Describe one validated, path-independent booking contract identity.

    Attributes:
        contract_id: Stable booking pair contract family.
        contract_version: Machine-readable schema version.
        contract_revision: Compatible semantic revision.
        manifest_sha256: SHA-256 of exact canonical manifest bytes.
        semantic_sha256: SHA-256 of canonical parsed JSON semantics.
        app_id: Immutable Flutter/backend application identifier.
        android_application_id: Permanent Android application identifier.
        api_origin: Public API origin without a service path prefix.
    """

    contract_id: str
    contract_version: int
    contract_revision: str
    manifest_sha256: str
    semantic_sha256: str
    app_id: str
    android_application_id: str
    api_origin: str


def _manifest_path(repository_root: Path | None) -> Path:
    """Resolve the canonical manifest in a checkout or installed app tree.

    Args:
        repository_root: Optional Python repository root. When omitted, the
            manifest adjacent to this module is used.

    Returns:
        Absolute manifest path.
    """

    if repository_root is None:
        return Path(__file__).resolve().with_name("pair_contract.json")
    return repository_root.resolve().joinpath(*CONTRACT_RELATIVE_PATH.split("/"))


def _read_manifest(repository_root: Path | None) -> tuple[dict[str, Any], bytes]:
    """Read the bounded UTF-8 JSON contract document.

    Args:
        repository_root: Optional repository root used for checkout validation.

    Returns:
        Parsed mapping and exact manifest bytes.

    Raises:
        BookingServiceContractError: If the manifest is absent or malformed.
    """

    path = _manifest_path(repository_root)
    try:
        content = path.read_bytes()
        if len(content) > _MAX_CONTRACT_BYTES:
            raise BookingServiceContractError(["contract: exceeds bounded size"])
        document = json.loads(content.decode("utf-8"))
    except BookingServiceContractError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BookingServiceContractError(["contract: expected valid UTF-8 JSON"]) from error
    if not isinstance(document, dict):
        raise BookingServiceContractError(["contract: expected an object"])
    return document, content


def _mapping(document: Mapping[str, Any], field: str) -> Mapping[str, Any] | None:
    """Return a nested mapping when the field has the expected type.

    Args:
        document: Mapping containing the requested field.
        field: Field name to read.

    Returns:
        Nested mapping, or ``None`` when the value is malformed.
    """

    value = document.get(field)
    return value if isinstance(value, Mapping) else None


def _semantic_sha256(document: Mapping[str, Any]) -> str:
    """Return a formatting-independent digest for the parsed contract.

    Args:
        document: Parsed pair contract.

    Returns:
        Lowercase SHA-256 of compact sorted JSON semantics.
    """

    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _identity_issues(document: Mapping[str, Any]) -> list[str]:
    """Return stable app, runtime, and authentication identity diagnostics.

    Args:
        document: Parsed pair contract.

    Returns:
        Compatibility diagnostics, or an empty list when identity is valid.
    """

    issues: list[str] = []
    expected_root = {
        "contract_id": SUPPORTED_CONTRACT_ID,
        "contract_version": SUPPORTED_CONTRACT_VERSION,
        "contract_revision": SUPPORTED_CONTRACT_REVISION,
    }
    for field, expected in expected_root.items():
        if document.get(field) != expected:
            issues.append(f"contract.{field}: unsupported value")
    application = _mapping(document, "application")
    runtime = _mapping(document, "runtime")
    if application is None or runtime is None:
        return [*issues, "contract: application and runtime objects are required"]
    issues.extend(_application_issues(application))
    issues.extend(_runtime_issues(runtime))
    return issues


def _application_issues(application: Mapping[str, Any]) -> list[str]:
    """Return immutable application-identity diagnostics.

    Args:
        application: Application section from the pair contract.

    Returns:
        Identity diagnostics, or an empty list when values match the v1 pin.
    """

    expected = {
        "app_id": "booking_service",
        "backend_profile": "booking_service",
        "dart_package": "booking_service",
        "display_name": "Booking Service",
        "organization_domain": "com.felicitaswisdom",
        "android_application_id": "com.felicitaswisdom.booking_service",
    }
    issues = [
        f"contract.application.{field}: unsupported value"
        for field, value in expected.items()
        if application.get(field) != value
    ]
    app_id = application.get("app_id")
    android_id = application.get("android_application_id")
    if not isinstance(app_id, str) or not _APP_ID_PATTERN.fullmatch(app_id):
        issues.append("contract.application.app_id: invalid identifier")
    if not isinstance(android_id, str) or not _ANDROID_ID_PATTERN.fullmatch(android_id):
        issues.append("contract.application.android_application_id: invalid identifier")
    return issues


def _runtime_issues(runtime: Mapping[str, Any]) -> list[str]:
    """Return public runtime and authentication diagnostics.

    Args:
        runtime: Runtime section from the pair contract.

    Returns:
        Runtime diagnostics, or an empty list when values match the v1 pin.
    """

    expected = {
        "deployment_topology": "shared_multi_tenant",
        "platforms": ["android", "web"],
        "python_requires": ">=3.13,<3.14",
        "backend_data_profile": "postgresql",
        "api_origin": "https://api.booking-service.example",
    }
    issues = [
        f"contract.runtime.{field}: unsupported value"
        for field, value in expected.items()
        if runtime.get(field) != value
    ]
    auth = _mapping(runtime, "authentication")
    expected_auth = {
        "provider": "keycloak",
        "issuer": "https://keycloak.fe-wi.com/realms/booking-service-example",
        "client_id": "keycloak",
        "audience": "keycloak",
        "audience_required": True,
    }
    if auth is None or dict(auth) != expected_auth:
        issues.append("contract.runtime.authentication: unsupported public identity")
    issues.extend(_public_url_issues(runtime.get("api_origin"), "api_origin", root_only=True))
    if auth is not None:
        issues.extend(_public_url_issues(auth.get("issuer"), "issuer", root_only=False))
    return issues


def _public_url_issues(value: Any, field: str, *, root_only: bool) -> list[str]:
    """Validate one HTTPS public URL without credentials or query state.

    Args:
        value: Candidate URL value.
        field: Stable field label used in diagnostics.
        root_only: Whether the path must be empty or `/`.

    Returns:
        URL diagnostics, or an empty list when safe.
    """

    if not isinstance(value, str):
        return [f"contract.runtime.{field}: expected HTTPS URL"]
    parsed = urlsplit(value)
    invalid = (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query or parsed.fragment)
        or (root_only and parsed.path not in {"", "/"})
    )
    return [f"contract.runtime.{field}: expected safe HTTPS URL"] if invalid else []


def _iter_named_values(value: Any, path: str = "contract") -> Iterator[tuple[str, Any]]:
    """Yield every nested mapping value with a stable dotted field path.

    Args:
        value: Arbitrary parsed JSON value.
        path: Current diagnostic path.

    Yields:
        Pairs of dotted field path and field value.
    """

    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, child
            yield from _iter_named_values(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_named_values(child, f"{path}[{index}]")


def _secret_field_issues(document: Mapping[str, Any]) -> list[str]:
    """Reject credential-shaped field names anywhere in the public contract.

    Args:
        document: Parsed pair contract.

    Returns:
        Sanitized secret-field diagnostics.
    """

    issues: list[str] = []
    for path, _ in _iter_named_values(document):
        field = path.rsplit(".", maxsplit=1)[-1].lower()
        if any(fragment in field for fragment in _FORBIDDEN_FIELD_FRAGMENTS):
            issues.append(f"{path}: credential-shaped fields are forbidden")
    return issues


def _normalized_route(value: str) -> str:
    """Return one normalized service-root-relative route path.

    Args:
        value: Literal route declared by the contract.

    Returns:
        POSIX-normalized route retaining a leading slash.
    """

    return posixpath.normpath(value)


def _route_issues(document: Mapping[str, Any]) -> list[str]:
    """Validate every declared route and the absolute no-`/api` policy.

    Args:
        document: Parsed pair contract.

    Returns:
        Route diagnostics, or an empty list when every route is safe.
    """

    issues: list[str] = []
    http = _mapping(document, "http")
    if http is None:
        return ["contract.http: expected an object"]
    policy = _mapping(http, "route_policy")
    expected_policy = {
        "routes_relative_to_api_origin": True,
        "forbid_api_service_prefix": True,
    }
    if policy is None or dict(policy) != expected_policy:
        issues.append("contract.http.route_policy: required relative-route policy is missing")
    for path, value in _iter_named_values(document):
        field = path.rsplit(".", maxsplit=1)[-1]
        if not isinstance(value, str) or "route" not in field:
            continue
        normalized = _normalized_route(value)
        if not value.startswith("/") or "?" in value or "#" in value:
            issues.append(f"{path}: expected a service-root-relative route")
        if normalized == "/api" or normalized.startswith("/api/"):
            issues.append(f"{path}: forbidden /api service prefix")
    return issues


def _semantic_issues(document: Mapping[str, Any]) -> list[str]:
    """Validate error, time, OpenAPI, capability, and ownership semantics.

    Args:
        document: Parsed pair contract.

    Returns:
        Semantic diagnostics, or an empty list for the supported v1 shape.
    """

    http = _mapping(document, "http") or {}
    time = _mapping(document, "time") or {}
    openapi = _mapping(document, "openapi") or {}
    ownership = _mapping(document, "ownership") or {}
    expected = (
        (http.get("product_route_prefix"), "/v1", "http.product_route_prefix"),
        (openapi.get("info_extension"), "x-booking-service-contract", "openapi.info_extension"),
        (time.get("utc_instant"), "rfc3339_utc_z", "time.utc_instant"),
        (time.get("timezone"), "iana_tzdb_identifier", "time.timezone"),
        (ownership.get("generated_files_change_via"), "managed_apply", "ownership.generated_files_change_via"),
        (ownership.get("unowned_files_default_to"), "handwritten", "ownership.unowned_files_default_to"),
    )
    issues = [f"contract.{field}: unsupported value" for actual, wanted, field in expected if actual != wanted]
    if ownership.get("detachment_required_before_manual_edit") is not True:
        issues.append("contract.ownership: detachment requirement is missing")
    errors = _mapping(http, "errors")
    capabilities = _mapping(http, "capability_discovery")
    if errors is None or errors.get("required_fields") != ["code", "message", "retryable", "correlation_id"]:
        issues.append("contract.http.errors: stable error envelope is required")
    if capabilities is None or capabilities.get("requires_authentication") is not True:
        issues.append("contract.http.capability_discovery: authenticated discovery is required")
    return issues


def validate_booking_service_pair_contract(
    repository_root: Path | None = None,
) -> BookingServiceContractIdentity:
    """Validate the complete Python-owned Booking Service pair contract.

    Args:
        repository_root: Optional Python repository root. Omit it when the
            packaged contract adjacent to this module should be validated.

    Returns:
        Path-independent validated contract identity.

    Raises:
        BookingServiceContractError: If any compatibility or safety rule fails.
    """

    document, content = _read_manifest(repository_root)
    semantic_sha256 = _semantic_sha256(document)
    issues = [
        *_identity_issues(document),
        *_route_issues(document),
        *_secret_field_issues(document),
        *_semantic_issues(document),
    ]
    if semantic_sha256 != SUPPORTED_CONTRACT_SEMANTIC_SHA256:
        issues.append("contract: semantic document differs from the supported revision")
    if issues:
        raise BookingServiceContractError(issues)
    application = document["application"]
    runtime = document["runtime"]
    return BookingServiceContractIdentity(
        contract_id=SUPPORTED_CONTRACT_ID,
        contract_version=SUPPORTED_CONTRACT_VERSION,
        contract_revision=SUPPORTED_CONTRACT_REVISION,
        manifest_sha256=hashlib.sha256(content).hexdigest(),
        semantic_sha256=semantic_sha256,
        app_id=application["app_id"],
        android_application_id=application["android_application_id"],
        api_origin=runtime["api_origin"],
    )


def render_openapi_contract_extension(
    identity: BookingServiceContractIdentity,
    implementation_version: str,
) -> dict[str, str | int]:
    """Render the stable OpenAPI info-extension payload for one implementation.

    Args:
        identity: Validated pair contract identity.
        implementation_version: Non-empty backend implementation version.

    Returns:
        Secret-free OpenAPI extension values.

    Raises:
        ValueError: If the implementation version is empty.
    """

    normalized_version = implementation_version.strip()
    if not normalized_version:
        raise ValueError("implementation_version must not be empty")
    return {
        "contract_id": identity.contract_id,
        "contract_version": identity.contract_version,
        "contract_revision": identity.contract_revision,
        "implementation_version": normalized_version,
    }
