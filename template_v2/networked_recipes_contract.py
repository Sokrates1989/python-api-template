"""Validate the Python-owned Template V2 B4 networked recipe catalog.

The catalog declares bounded compatibility metadata only. Renderable source is
added recipe by recipe after checksum, selected/absent, and removal gates pass.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


CONTRACT_RELATIVE_PATH = "template_v2/networked_recipes_contract.json"
SUPPORTED_CONTRACT_ID = "template-v2-networked-recipes"
SUPPORTED_CONTRACT_VERSION = 3
SUPPORTED_CATALOG_REVISION = "0.5.0"
_MAX_FILE_BYTES = 1_000_000
_CONFIG_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RECIPE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
_SUPPORTED_METHODS = frozenset({"DELETE", "GET", "POST", "PUT"})
_SUPPORTED_DEPENDENCIES = frozenset(
    {
        "account_erasure",
        "ai_chat",
        "authenticated_web_push",
        "hybrid_sync",
        "keycloak_auth",
        "records_starter",
    }
)
_EXPECTED_RECIPES = (
    ("hybrid_sync", "1.0.0", "hybrid_sync", "1.0.0"),
    ("authenticated_web_push", "1.0.0", "pwa_web", "1.0.0"),
    ("ai_chat", "1.0.0", "ai_chat", "1.0.0"),
    ("account_erasure", "1.0.0", "account_erasure", "1.0.0"),
)
_EXPECTED_SOURCE_CONTRACTS = {
    "hybrid_sync": "template_v2/networked_recipes/hybrid_sync/recipe.json",
    "authenticated_web_push": (
        "template_v2/networked_recipes/authenticated_web_push/recipe.json"
    ),
    "ai_chat": "template_v2/networked_recipes/ai_chat/recipe.json",
    "account_erasure": "template_v2/networked_recipes/account_erasure/recipe.json",
}
_EXPECTED_PYTHON_DEPENDENCY_PROFILES = {
    "hybrid_sync": (None, (), None),
    "authenticated_web_push": (
        "postgresql_web_push",
        ("pywebpush>=2.3.0,<2.4.0",),
        "02d69f7505d75c6b2e75ef6931274854ee35e9090abbd82dc4bf8691f071a6d8",
    ),
    "ai_chat": (None, (), None),
    "account_erasure": (None, (), None),
}
_RECIPE_FIELDS = frozenset(
    {
        "backend_recipe_id",
        "backend_revision",
        "depends_on",
        "flutter_recipe_id",
        "flutter_recipe_version",
        "implementation_status",
        "migration_paths",
        "public_configuration_keys",
        "python_dependencies",
        "python_dependency_lock_sha256",
        "python_dependency_profile",
        "removal_paths",
        "routes",
        "secret_configuration_keys",
        "service_paths",
        "source_contract",
    }
)


class NetworkedRecipesContractError(ValueError):
    """Report sorted content-free catalog validation failures.

    Attributes:
        issues: Stable unique validation diagnostics.
    """

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        """Store at least one normalized catalog issue.

        Args:
            issues: Validation diagnostics without machine-local paths.

        Raises:
            ValueError: If no issue is supplied.
        """

        normalized = tuple(sorted(set(issues)))
        if not normalized:
            raise ValueError("NetworkedRecipesContractError requires an issue")
        self.issues = normalized
        super().__init__("\n".join(normalized))


@dataclass(frozen=True)
class NetworkedRecipeRoute:
    """Describe one API-service-relative networked recipe route.

    Attributes:
        method: Uppercase HTTP method.
        path: Absolute service path without a redundant `/api` prefix.
    """

    method: str
    path: str


@dataclass(frozen=True)
class NetworkedRecipeContract:
    """Describe one planned backend recipe and its removal boundary.

    Attributes:
        backend_recipe_id: Python-owned recipe identifier.
        backend_revision: Semantic backend recipe revision.
        flutter_recipe_id: Matching Flutter recipe identifier.
        flutter_recipe_version: Matching Flutter recipe version.
        implementation_status: Contract-only or later renderable state.
        depends_on: Deterministically ordered prerequisite recipe ids.
        routes: Ordered authenticated service routes.
        migration_paths: App-relative generated migration paths.
        service_paths: App-relative generated implementation paths.
        public_configuration_keys: Non-secret deployment configuration names.
        python_dependencies: Additional selected-only direct dependencies.
        python_dependency_lock_sha256: Exact selected lock digest, if required.
        python_dependency_profile: Python-owned lock profile, if required.
        secret_configuration_keys: Secret or secret-reference setting names.
        removal_paths: Complete paths removed with the recipe.
        source_contract: Optional repository-relative checksum manifest.
    """

    backend_recipe_id: str
    backend_revision: str
    flutter_recipe_id: str
    flutter_recipe_version: str
    implementation_status: str
    depends_on: tuple[str, ...]
    routes: tuple[NetworkedRecipeRoute, ...]
    migration_paths: tuple[str, ...]
    service_paths: tuple[str, ...]
    public_configuration_keys: tuple[str, ...]
    python_dependencies: tuple[str, ...]
    python_dependency_lock_sha256: str | None
    python_dependency_profile: str | None
    secret_configuration_keys: tuple[str, ...]
    removal_paths: tuple[str, ...]
    source_contract: str | None


@dataclass(frozen=True)
class NetworkedRecipesCatalog:
    """Hold the validated B4 catalog identity and ordered recipes.

    Attributes:
        contract_version: Machine-readable schema version.
        catalog_revision: Semantic catalog revision.
        manifest_sha256: SHA-256 of exact manifest bytes.
        recipes: Stable dependency-aware recipe order.
    """

    contract_version: int
    catalog_revision: str
    manifest_sha256: str
    recipes: tuple[NetworkedRecipeContract, ...]


def _read_contract(root: Path) -> tuple[dict[str, Any], bytes]:
    """Read one bounded UTF-8 catalog manifest.

    Args:
        root: Backend repository root.

    Returns:
        Parsed JSON object and exact source bytes.

    Raises:
        NetworkedRecipesContractError: If the manifest is unsafe or invalid.
    """

    path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            raise OSError
        content = path.read_bytes()
        document = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise NetworkedRecipesContractError(
            [f"{CONTRACT_RELATIVE_PATH}: expected bounded UTF-8 JSON"]
        ) from error
    if not isinstance(document, dict):
        raise NetworkedRecipesContractError(
            [f"{CONTRACT_RELATIVE_PATH}: expected an object"]
        )
    return document, content


def _string_list(value: Any, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    """Validate one unique ordered list of non-empty strings.

    Args:
        value: Candidate JSON list.
        field: Stable diagnostic field.
        allow_empty: Whether an empty list is valid. Defaults to true.

    Returns:
        Validated string tuple in manifest order.

    Raises:
        NetworkedRecipesContractError: If type, emptiness, or uniqueness fails.
    """

    if not isinstance(value, list) or (not allow_empty and not value):
        raise NetworkedRecipesContractError([f"{field}: expected an ordered list"])
    if any(not isinstance(item, str) or not item for item in value):
        raise NetworkedRecipesContractError([f"{field}: expected non-empty strings"])
    if len(value) != len(set(value)):
        raise NetworkedRecipesContractError([f"{field}: duplicate values"])
    return tuple(value)


def _portable_paths(value: Any, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    """Validate one ordered list of safe app-relative paths.

    Args:
        value: Candidate JSON path list.
        field: Stable diagnostic field.
        allow_empty: Whether an empty list is valid. Defaults to true.

    Returns:
        Validated portable paths.

    Raises:
        NetworkedRecipesContractError: If a path is unsafe.
    """

    values = _string_list(value, field, allow_empty=allow_empty)
    for item in values:
        path = PurePosixPath(item)
        if path.is_absolute() or ".." in path.parts or "\\" in item or path.as_posix() != item:
            raise NetworkedRecipesContractError([f"{field}: unsafe path"])
    return values


def _configuration_keys(value: Any, field: str) -> tuple[str, ...]:
    """Validate one ordered configuration-key list.

    Args:
        value: Candidate JSON list.
        field: Stable diagnostic field.

    Returns:
        Validated uppercase configuration names.

    Raises:
        NetworkedRecipesContractError: If a name is unsafe.
    """

    values = _string_list(value, field)
    if any(not _CONFIG_KEY_PATTERN.fullmatch(item) for item in values):
        raise NetworkedRecipesContractError([f"{field}: invalid configuration key"])
    return values


def _parse_route(value: Any, field: str) -> NetworkedRecipeRoute:
    """Validate one service route declaration.

    Args:
        value: Candidate JSON route object.
        field: Stable diagnostic field.

    Returns:
        Validated route contract.

    Raises:
        NetworkedRecipesContractError: If method or path is unsupported.
    """

    if not isinstance(value, dict) or set(value) != {"method", "path"}:
        raise NetworkedRecipesContractError([f"{field}: expected method and path"])
    method = value.get("method")
    path = value.get("path")
    if method not in _SUPPORTED_METHODS:
        raise NetworkedRecipesContractError([f"{field}.method: unsupported value"])
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path == "/api"
        or path.startswith("/api/")
        or "?" in path
        or "#" in path
    ):
        raise NetworkedRecipesContractError([f"{field}.path: unsafe service route"])
    return NetworkedRecipeRoute(method=method, path=path)


def _parse_recipe(value: Any, index: int) -> NetworkedRecipeContract:
    """Validate one complete B4 recipe catalog entry.

    Args:
        value: Candidate recipe object.
        index: Stable catalog index.

    Returns:
        Validated recipe contract.

    Raises:
        NetworkedRecipesContractError: If any field or removal boundary fails.
    """

    field = f"contract.recipes[{index}]"
    if not isinstance(value, dict) or set(value) != _RECIPE_FIELDS:
        raise NetworkedRecipesContractError([f"{field}: unexpected fields"])
    identity_fields = (
        "backend_recipe_id",
        "backend_revision",
        "flutter_recipe_id",
        "flutter_recipe_version",
        "implementation_status",
    )
    if any(not isinstance(value.get(name), str) for name in identity_fields):
        raise NetworkedRecipesContractError([f"{field}: invalid identity"])
    if not _RECIPE_ID_PATTERN.fullmatch(value["backend_recipe_id"]):
        raise NetworkedRecipesContractError([f"{field}.backend_recipe_id: invalid value"])
    if value["implementation_status"] not in {"contract_only", "renderable"}:
        raise NetworkedRecipesContractError([f"{field}.implementation_status: invalid value"])
    source_contract_value = value["source_contract"]
    if source_contract_value is None:
        source_contract = None
    elif isinstance(source_contract_value, str):
        source_contract = _portable_paths(
            [source_contract_value],
            f"{field}.source_contract",
            allow_empty=False,
        )[0]
    else:
        raise NetworkedRecipesContractError(
            [f"{field}.source_contract: expected a path or null"]
        )
    if (value["implementation_status"] == "renderable") != (source_contract is not None):
        raise NetworkedRecipesContractError(
            [f"{field}.source_contract: must match implementation status"]
        )
    if value["backend_recipe_id"] not in _EXPECTED_SOURCE_CONTRACTS:
        raise NetworkedRecipesContractError(
            [f"{field}.backend_recipe_id: unsupported value"]
        )
    expected_source = _EXPECTED_SOURCE_CONTRACTS[value["backend_recipe_id"]]
    expected_status = "renderable" if expected_source is not None else "contract_only"
    if value["implementation_status"] != expected_status or source_contract != expected_source:
        raise NetworkedRecipesContractError(
            [f"{field}.source_contract: unsupported catalog promotion"]
        )
    dependency_profile_value = value["python_dependency_profile"]
    if dependency_profile_value is None:
        dependency_profile = None
    elif isinstance(dependency_profile_value, str):
        dependency_profile = _portable_paths(
            [dependency_profile_value],
            f"{field}.python_dependency_profile",
            allow_empty=False,
        )[0]
    else:
        raise NetworkedRecipesContractError(
            [f"{field}.python_dependency_profile: expected a path or null"]
        )
    python_dependencies = _string_list(
        value["python_dependencies"],
        f"{field}.python_dependencies",
    )
    lock_sha256_value = value["python_dependency_lock_sha256"]
    if lock_sha256_value is None:
        lock_sha256 = None
    elif isinstance(lock_sha256_value, str) and _SHA256_PATTERN.fullmatch(
        lock_sha256_value
    ):
        lock_sha256 = lock_sha256_value
    else:
        raise NetworkedRecipesContractError(
            [f"{field}.python_dependency_lock_sha256: invalid digest"]
        )
    expected_dependency_profile = _EXPECTED_PYTHON_DEPENDENCY_PROFILES[
        value["backend_recipe_id"]
    ]
    if (
        dependency_profile,
        python_dependencies,
        lock_sha256,
    ) != expected_dependency_profile:
        raise NetworkedRecipesContractError(
            [f"{field}.python_dependency_profile: unsupported dependency contract"]
        )
    depends_on = _string_list(value["depends_on"], f"{field}.depends_on", allow_empty=False)
    if any(item not in _SUPPORTED_DEPENDENCIES for item in depends_on):
        raise NetworkedRecipesContractError([f"{field}.depends_on: unsupported recipe"])
    routes_value = value["routes"]
    if not isinstance(routes_value, list) or not routes_value:
        raise NetworkedRecipesContractError([f"{field}.routes: expected entries"])
    routes = tuple(
        _parse_route(route, f"{field}.routes[{route_index}]")
        for route_index, route in enumerate(routes_value)
    )
    route_keys = tuple((route.method, route.path) for route in routes)
    if len(route_keys) != len(set(route_keys)):
        raise NetworkedRecipesContractError([f"{field}.routes: duplicate route"])
    migrations = _portable_paths(value["migration_paths"], f"{field}.migration_paths")
    services = _portable_paths(
        value["service_paths"], f"{field}.service_paths", allow_empty=False
    )
    removal = _portable_paths(
        value["removal_paths"], f"{field}.removal_paths", allow_empty=False
    )
    if not set((*migrations, *services)).issubset(removal):
        raise NetworkedRecipesContractError(
            [f"{field}.removal_paths: must cover migrations and services"]
        )
    public_keys = _configuration_keys(
        value["public_configuration_keys"], f"{field}.public_configuration_keys"
    )
    secret_keys = _configuration_keys(
        value["secret_configuration_keys"], f"{field}.secret_configuration_keys"
    )
    if set(public_keys).intersection(secret_keys):
        raise NetworkedRecipesContractError(
            [f"{field}: configuration ownership overlaps"]
        )
    return NetworkedRecipeContract(
        backend_recipe_id=value["backend_recipe_id"],
        backend_revision=value["backend_revision"],
        flutter_recipe_id=value["flutter_recipe_id"],
        flutter_recipe_version=value["flutter_recipe_version"],
        implementation_status=value["implementation_status"],
        depends_on=depends_on,
        routes=routes,
        migration_paths=migrations,
        service_paths=services,
        public_configuration_keys=public_keys,
        python_dependencies=python_dependencies,
        python_dependency_lock_sha256=lock_sha256,
        python_dependency_profile=dependency_profile,
        secret_configuration_keys=secret_keys,
        removal_paths=removal,
        source_contract=source_contract,
    )


def validate_networked_recipes_contract(root: Path) -> NetworkedRecipesCatalog:
    """Validate the canonical B4 catalog and return its exact identity.

    Args:
        root: Backend repository root containing ``template_v2``.

    Returns:
        Validated catalog identity and ordered recipes.

    Raises:
        NetworkedRecipesContractError: If identity, profile, recipe, or route drifts.
    """

    document, manifest_bytes = _read_contract(root)
    expected = {
        "contract_id": SUPPORTED_CONTRACT_ID,
        "contract_version": SUPPORTED_CONTRACT_VERSION,
        "catalog_revision": SUPPORTED_CATALOG_REVISION,
        "standard_profile": {"auth_provider": "keycloak", "backend": "postgresql"},
    }
    issues = [
        f"contract.{field}: unsupported value"
        for field, expected_value in expected.items()
        if document.get(field) != expected_value
    ]
    recipes_value = document.get("recipes")
    if not isinstance(recipes_value, list):
        issues.append("contract.recipes: expected an ordered list")
    if issues:
        raise NetworkedRecipesContractError(issues)
    assert isinstance(recipes_value, list)
    recipes = tuple(_parse_recipe(value, index) for index, value in enumerate(recipes_value))
    actual_identity = tuple(
        (
            recipe.backend_recipe_id,
            recipe.backend_revision,
            recipe.flutter_recipe_id,
            recipe.flutter_recipe_version,
        )
        for recipe in recipes
    )
    if actual_identity != _EXPECTED_RECIPES:
        raise NetworkedRecipesContractError(
            ["contract.recipes: expected the complete ordered B4 catalog"]
        )
    route_keys = tuple(
        (route.method, route.path)
        for recipe in recipes
        for route in recipe.routes
    )
    if len(route_keys) != len(set(route_keys)):
        raise NetworkedRecipesContractError(["contract.recipes: duplicate service route"])
    return NetworkedRecipesCatalog(
        contract_version=SUPPORTED_CONTRACT_VERSION,
        catalog_revision=SUPPORTED_CATALOG_REVISION,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        recipes=recipes,
    )
