"""
Registry for backend apps hosted in the multi-app monorepo.

The registry discovers backend app definitions from child packages at import
time and resolves the selected app definition from configuration. Dynamic app
creation therefore only needs to add a package under `app/apps/<app_id>` with a
`definition.py` module.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Any

import apps
from apps.contracts import BackendAppDefinition


DEFAULT_BACKEND_APP_ID = "demo_app"


def _iter_backend_app_package_names() -> tuple[str, ...]:
    """
    Return discoverable backend app package names.

    Args:
        None.

    Returns:
        tuple[str, ...]: Package names found directly below `apps`.

    Side Effects:
        None.
    """
    return tuple(
        module_info.name
        for module_info in pkgutil.iter_modules(apps.__path__)
        if module_info.ispkg and not module_info.name.startswith("_")
    )


def _get_raw_definition(module: Any) -> Any | None:
    """
    Return the app definition object exported by a definition module.

    Args:
        module (Any): Imported `apps.<app_id>.definition` module.

    Returns:
        Any | None: The exported definition object when one can be found.

    Side Effects:
        None.
    """
    exported_definition = getattr(module, "BACKEND_APP_DEFINITION", None)
    if exported_definition is not None:
        return exported_definition

    for value in vars(module).values():
        if isinstance(value, BackendAppDefinition):
            return value
    return None


def _coerce_backend_app_definition(raw_definition: Any) -> BackendAppDefinition | None:
    """
    Convert a discovered app definition into the runtime contract.

    The compatibility branch supports apps created by older quick-start
    generators that wrote a local mini dataclass with `app_id`, `name`,
    `description`, and `db_type` fields.

    Args:
        raw_definition (Any): Definition object exported by an app module.

    Returns:
        BackendAppDefinition | None: Runtime definition, or `None` when the
        object does not look like an app definition.

    Side Effects:
        None.
    """
    if isinstance(raw_definition, BackendAppDefinition):
        return raw_definition

    app_id = getattr(raw_definition, "app_id", None)
    display_name = getattr(raw_definition, "name", None)
    backend_data_profile = getattr(raw_definition, "db_type", None)
    if not app_id or not display_name or not backend_data_profile:
        return None

    return BackendAppDefinition(
        app_id=str(app_id),
        display_name=str(display_name),
        backend_data_profile=str(backend_data_profile),
        route_registrations=(),
        exposes_sync_routes=False,
    )


def discover_backend_apps() -> dict[str, BackendAppDefinition]:
    """
    Discover backend app definitions from child app packages.

    Args:
        None.

    Returns:
        dict[str, BackendAppDefinition]: Definitions keyed by normalized app id.

    Side Effects:
        Imports each `apps.<app_id>.definition` module.
    """
    registered_apps: dict[str, BackendAppDefinition] = {}
    for package_name in _iter_backend_app_package_names():
        module_name = f"apps.{package_name}.definition"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise

        raw_definition = _get_raw_definition(module)
        definition = _coerce_backend_app_definition(raw_definition)
        if definition is None:
            continue

        normalized_app_id = normalize_backend_app_id(definition.app_id)
        registered_apps[normalized_app_id] = definition
    return registered_apps


def normalize_backend_app_id(app_id: str | None) -> str:
    """
    Normalize the configured backend app identifier.

    Args:
        app_id (str | None): Raw configured app identifier.

    Returns:
        str: Normalized identifier, or the default app identifier when empty.

    Side Effects:
        None.
    """
    normalized_app_id = (app_id or DEFAULT_BACKEND_APP_ID).strip().lower()
    return normalized_app_id or DEFAULT_BACKEND_APP_ID


REGISTERED_BACKEND_APPS: dict[str, BackendAppDefinition] = discover_backend_apps()


def get_backend_app_definition(app_id: str | None) -> BackendAppDefinition:
    """
    Resolve a backend app definition from the central registry.

    Args:
        app_id (str | None): Requested app identifier.

    Returns:
        BackendAppDefinition: Registered app definition.

    Raises:
        ValueError: Raised when the requested app is not registered.

    Side Effects:
        None.
    """
    normalized_app_id = normalize_backend_app_id(app_id)
    definition = REGISTERED_BACKEND_APPS.get(normalized_app_id)
    if definition is None:
        supported_ids = ", ".join(sorted(REGISTERED_BACKEND_APPS))
        raise ValueError(
            f"Unsupported backend app id: {app_id!r}. Supported apps: {supported_ids}"
        )
    return definition
