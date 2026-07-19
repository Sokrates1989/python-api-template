"""Validate the versioned Template V2 backend-foundation compatibility contract.

The validator is intentionally standard-library-only. It verifies the canonical
manifest, declared source digest, dependency profiles, required composition
surfaces, and the absolute prohibition on API-service routes beginning with
``/api``. Diagnostics contain portable paths and never source or secret values.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


CONTRACT_RELATIVE_PATH = "template_v2/backend_foundation_contract.json"
SUPPORTED_CONTRACT_ID = "template-v2-backend-foundation"
SUPPORTED_CONTRACT_VERSION = 1
SUPPORTED_FOUNDATION_REVISION = "1.0.0"
SUPPORTED_PYTHON_REQUIREMENT = ">=3.13,<3.14"
_DIGEST_DOMAIN = b"template-v2-backend-foundation-source-v1\0"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ROUTE_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put"})


class BackendFoundationContractError(ValueError):
    """Report one or more content-free backend-foundation contract failures.

    Attributes:
        issues: Stable sorted diagnostics using repository-relative paths.
    """

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        """Initialize an aggregate validation failure.

        Args:
            issues: Non-empty validation diagnostics.

        Raises:
            ValueError: If no diagnostic is supplied.
        """

        normalized = tuple(sorted(set(issues)))
        if not normalized:
            raise ValueError("BackendFoundationContractError requires an issue")
        self.issues = normalized
        super().__init__("\n".join(normalized))


@dataclass(frozen=True)
class BackendFoundationIdentity:
    """Describe one validated, path-independent backend foundation identity.

    Attributes:
        contract_id: Stable contract family identifier.
        contract_version: Machine-contract schema version.
        foundation_revision: Compatible backend-foundation revision.
        manifest_sha256: SHA-256 of the exact canonical manifest bytes.
        source_sha256: SHA-256 of canonical declared source bytes.
        source_file_count: Number of source files covered by the digest.
    """

    contract_id: str
    contract_version: int
    foundation_revision: str
    manifest_sha256: str
    source_sha256: str
    source_file_count: int


def _read_manifest(root: Path) -> tuple[dict[str, Any], bytes]:
    """Read and parse the bounded backend foundation manifest.

    Args:
        root: Python API template repository root.

    Returns:
        Parsed manifest mapping and exact manifest bytes.

    Raises:
        BackendFoundationContractError: If the manifest is absent or invalid.
    """

    path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
    try:
        content = path.read_bytes()
        document = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackendFoundationContractError(
            [f"{CONTRACT_RELATIVE_PATH}: expected valid UTF-8 JSON"]
        ) from error
    if not isinstance(document, dict):
        raise BackendFoundationContractError([f"{CONTRACT_RELATIVE_PATH}: expected an object"])
    return document, content


def _string_list(document: dict[str, Any], field: str) -> tuple[str, ...]:
    """Return one required non-empty unique string list.

    Args:
        document: Mapping containing the field.
        field: Field name used in diagnostics.

    Returns:
        Immutable ordered string values.

    Raises:
        BackendFoundationContractError: If the field is malformed.
    """

    value = document.get(field)
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise BackendFoundationContractError([f"contract.{field}: expected non-empty strings"])
    values = tuple(value)
    if len(set(values)) != len(values):
        raise BackendFoundationContractError([f"contract.{field}: duplicate values are forbidden"])
    return values


def _portable_source_paths(document: dict[str, Any]) -> tuple[str, ...]:
    """Validate and return sorted repository-relative source paths.

    Args:
        document: Parsed contract manifest.

    Returns:
        Sorted portable source paths covered by the digest.

    Raises:
        BackendFoundationContractError: If paths are unsafe or unordered.
    """

    paths = _string_list(document, "source_files")
    issues: list[str] = []
    for value in paths:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or path.as_posix() != value:
            issues.append(f"contract.source_files: unsafe path {value}")
    if tuple(sorted(paths, key=str.casefold)) != paths:
        issues.append("contract.source_files: paths must be case-insensitively sorted")
    if issues:
        raise BackendFoundationContractError(issues)
    return paths


def _canonical_source_bytes(path: Path, relative_path: str) -> bytes:
    """Read one regular source file and normalize text line endings.

    Args:
        path: Absolute candidate source path.
        relative_path: Portable path used in diagnostics.

    Returns:
        UTF-8 bytes with CRLF normalized to LF.

    Raises:
        BackendFoundationContractError: If the source is unsafe or unreadable.
    """

    if path.is_symlink() or not path.is_file():
        raise BackendFoundationContractError([f"backend source {relative_path}: expected a regular file"])
    try:
        content = path.read_bytes()
        content.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BackendFoundationContractError([f"backend source {relative_path}: expected UTF-8 text"]) from error
    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def calculate_source_sha256(root: Path, source_paths: tuple[str, ...]) -> str:
    """Calculate the canonical path-independent foundation source digest.

    Args:
        root: Python API template repository root.
        source_paths: Sorted portable source paths from the manifest.

    Returns:
        Lowercase SHA-256 covering paths, sizes, and normalized source bytes.

    Raises:
        BackendFoundationContractError: If any declared source is unreadable.
    """

    digest = hashlib.sha256(_DIGEST_DOMAIN)
    for relative_path in source_paths:
        content = _canonical_source_bytes(root.joinpath(*relative_path.split("/")), relative_path)
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _identity_issues(document: dict[str, Any]) -> list[str]:
    """Return contract identity and supported-profile diagnostics.

    Args:
        document: Parsed contract manifest.

    Returns:
        Stable compatibility diagnostics.
    """

    issues: list[str] = []
    expected = {
        "contract_id": SUPPORTED_CONTRACT_ID,
        "contract_version": SUPPORTED_CONTRACT_VERSION,
        "foundation_revision": SUPPORTED_FOUNDATION_REVISION,
        "requires_python": SUPPORTED_PYTHON_REQUIREMENT,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            issues.append(f"contract.{field}: unsupported value")
    standard = document.get("standard_connected_profile")
    if standard != {"auth_provider": "keycloak", "backend": "postgresql"}:
        issues.append("contract.standard_connected_profile: expected Keycloak/PostgreSQL")
    retained = document.get("retained_compatibility")
    if retained != {"auth_providers": ["cognito"], "backends": ["mongodb"]}:
        issues.append("contract.retained_compatibility: unsupported compatibility declaration")
    return issues


def _surface_marker_issues(root: Path, document: dict[str, Any], source_paths: tuple[str, ...]) -> list[str]:
    """Return diagnostics for required source-surface markers.

    Args:
        root: Python API template repository root.
        document: Parsed contract manifest.
        source_paths: Validated source file paths.

    Returns:
        Stable missing-marker diagnostics.
    """

    markers = document.get("surface_markers")
    if not isinstance(markers, dict):
        return ["contract.surface_markers: expected an object"]
    issues: list[str] = []
    for relative_path, required in markers.items():
        if relative_path not in source_paths or not isinstance(required, list):
            issues.append(f"contract.surface_markers: invalid source {relative_path}")
            continue
        content = _canonical_source_bytes(root.joinpath(*relative_path.split("/")), relative_path).decode("utf-8")
        if any(not isinstance(marker, str) or not marker or marker not in content for marker in required):
            issues.append(f"backend contract: {relative_path} surface drifted")
    return issues


def _provider_profile_issues(root: Path, document: dict[str, Any]) -> list[str]:
    """Return provider dependency and support-classification diagnostics.

    Args:
        root: Python API template repository root.
        document: Parsed contract manifest.

    Returns:
        Stable provider-profile diagnostics.
    """

    profiles = document.get("provider_profiles")
    if not isinstance(profiles, dict) or set(profiles) != {"mongodb", "postgresql"}:
        return ["contract.provider_profiles: expected mongodb and postgresql"]
    issues: list[str] = []
    for backend, profile in profiles.items():
        if not isinstance(profile, dict):
            issues.append(f"contract.provider_profiles.{backend}: expected an object")
            continue
        source_app_id = profile.get("source_app_id")
        dependencies = profile.get("dependencies")
        support = profile.get("support")
        expected = {
            "mongodb": ("retained", "mongodb_template", "mongodb", "local-deployment/base/mongodb.compose.yml"),
            "postgresql": ("standard", "postgres_template", "postgres", "local-deployment/base/postgres.compose.yml"),
        }[backend]
        declared = (
            support,
            source_app_id,
            profile.get("service_name"),
            profile.get("base_compose_path"),
        )
        if declared != expected or not isinstance(dependencies, list):
            issues.append(f"contract.provider_profiles.{backend}: invalid profile")
            continue
        project_path = root / "app" / "apps" / source_app_id / "pyproject.toml"
        try:
            project = tomllib.loads(_canonical_source_bytes(project_path, project_path.relative_to(root).as_posix()).decode("utf-8"))
        except tomllib.TOMLDecodeError:
            issues.append(f"backend dependency source: {backend} pyproject is invalid")
            continue
        project_data = project.get("project", {})
        if project_data.get("name") != source_app_id or project_data.get("requires-python") != SUPPORTED_PYTHON_REQUIREMENT:
            issues.append(f"backend dependency source: {backend} identity drifted")
        if project_data.get("dependencies") != dependencies:
            issues.append(f"backend dependency source: {backend} dependencies drifted")
    return issues


def _literal_string(call: ast.Call, keyword: str, positional: int | None = None) -> str | None:
    """Return one literal string argument from an AST call.

    Args:
        call: Call expression to inspect.
        keyword: Preferred keyword name.
        positional: Optional positional fallback index.

    Returns:
        Literal string value, or ``None`` for dynamic/absent values.
    """

    for item in call.keywords:
        if item.arg == keyword and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            return item.value.value
    if positional is not None and len(call.args) > positional:
        value = call.args[positional]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _route_prefixes(tree: ast.AST) -> tuple[str, ...]:
    """Collect literal route prefixes and decorator paths from Python AST.

    Args:
        tree: Parsed Python module syntax tree.

    Returns:
        Literal service-route path values found in known FastAPI calls.
    """

    prefixes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        value: str | None = None
        if name in {"APIRouter", "include_router"}:
            value = _literal_string(node, "prefix")
        elif name in _ROUTE_METHODS:
            value = _literal_string(node, "path", 0)
        elif name == "RouteRegistration":
            value = _literal_string(node, "external_prefix")
        if value:
            prefixes.append(value)
    return tuple(prefixes)


def _route_policy_issues(root: Path, document: dict[str, Any]) -> list[str]:
    """Return diagnostics for forbidden redundant API route prefixes.

    Args:
        root: Python API template repository root.
        document: Parsed contract manifest.

    Returns:
        Portable route-policy and syntax diagnostics.
    """

    policy = document.get("route_policy")
    if policy != {"forbid_api_service_prefix": True}:
        return ["contract.route_policy: redundant /api prefix prohibition is required"]
    route_sources = {
        *root.glob("app/api/routes/**/*.py"),
        *root.glob("app/api/shared_routes/**/*.py"),
        *root.glob("app/apps/*/routes/**/*.py"),
        *root.glob("app/apps/*/definition.py"),
    }
    issues: list[str] = []
    for path in sorted(route_sources):
        if path.is_symlink():
            continue
        relative_path = path.relative_to(root).as_posix()
        try:
            source = _canonical_source_bytes(path, relative_path).decode("utf-8")
            tree = ast.parse(source.removeprefix("\ufeff"), filename=relative_path)
        except SyntaxError:
            issues.append(f"backend route policy: invalid Python source {relative_path}")
            continue
        if any(prefix == "/api" or prefix.startswith("/api/") for prefix in _route_prefixes(tree)):
            issues.append(f"backend route policy: forbidden /api prefix in {relative_path}")
    return issues


def validate_backend_foundation(root: Path) -> BackendFoundationIdentity:
    """Validate the complete backend foundation contract at a repository root.

    Args:
        root: Candidate Python API template repository root.

    Returns:
        Path-independent validated contract and source identity.

    Raises:
        BackendFoundationContractError: If compatibility or source proof fails.
    """

    resolved_root = root.resolve()
    document, manifest_content = _read_manifest(resolved_root)
    source_paths = _portable_source_paths(document)
    source_sha256 = calculate_source_sha256(resolved_root, source_paths)
    declared_sha256 = document.get("source_sha256")
    issues = [
        *_identity_issues(document),
        *_surface_marker_issues(resolved_root, document, source_paths),
        *_provider_profile_issues(resolved_root, document),
        *_route_policy_issues(resolved_root, document),
    ]
    if not isinstance(declared_sha256, str) or not _SHA256_PATTERN.fullmatch(declared_sha256):
        issues.append("contract.source_sha256: expected lowercase SHA-256")
    elif source_sha256 != declared_sha256:
        issues.append("contract.source_sha256: declared foundation source drifted")
    if issues:
        raise BackendFoundationContractError(issues)
    return BackendFoundationIdentity(
        contract_id=SUPPORTED_CONTRACT_ID,
        contract_version=SUPPORTED_CONTRACT_VERSION,
        foundation_revision=SUPPORTED_FOUNDATION_REVISION,
        manifest_sha256=hashlib.sha256(manifest_content).hexdigest(),
        source_sha256=source_sha256,
        source_file_count=len(source_paths),
    )
