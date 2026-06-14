"""OpenAPI configuration for Swagger UI."""
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from api.settings import settings
from apps.contracts import BackendAppDefinition, RouteSecurityRequirement


HTTP_METHODS_WITH_SECURITY = {"get", "post", "delete", "put", "patch"}
SHARED_SECURITY_SCHEMES = {
    "X-Admin-Key": {
        "type": "apiKey",
        "in": "header",
        "name": "X-Admin-Key",
        "description": "Admin API key for protected operations.",
    },
    "X-Restore-Key": {
        "type": "apiKey",
        "in": "header",
        "name": "X-Restore-Key",
        "description": "Restore API key for destructive restore operations.",
    },
    "BearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "API key",
        "description": "Bearer token alternative for backup and restore orchestration.",
    },
}


def _iter_shared_security_requirements() -> tuple[RouteSecurityRequirement, ...]:
    """
    Return security requirements for shared admin routes.

    Returns:
        tuple[RouteSecurityRequirement, ...]: Route security declarations for
            shared package, database, and stats endpoints.

    Side Effects:
        None.
    """
    return (
        RouteSecurityRequirement(
            path_prefix="/packages/",
            requirement={"X-Admin-Key": []},
        ),
        RouteSecurityRequirement(
            path_prefix="/database/",
            requirement={"X-Admin-Key": []},
        ),
        RouteSecurityRequirement(
            path_prefix="/database/",
            requirement={"BearerAuth": []},
        ),
        RouteSecurityRequirement(
            path_prefix="/stats",
            requirement={"X-Admin-Key": []},
            methods=("get",),
            exact_path=True,
        ),
    )


def _get_selected_security_schemes(
    selected_app: BackendAppDefinition,
) -> dict[str, dict]:
    """
    Build the security schemes allowed for the selected backend app.

    Args:
        selected_app (BackendAppDefinition): Active backend app definition.

    Returns:
        dict[str, dict]: OpenAPI security scheme objects keyed by scheme name.

    Side Effects:
        None.
    """
    security_schemes = {
        scheme.name: scheme.scheme
        for scheme in selected_app.openapi_security_schemes
    }
    if selected_app.include_shared_routes or selected_app.requires_database:
        security_schemes.update(SHARED_SECURITY_SCHEMES)
    return security_schemes


def _iter_selected_route_security(
    selected_app: BackendAppDefinition,
) -> tuple[RouteSecurityRequirement, ...]:
    """
    Return route security requirements for the selected backend app.

    Args:
        selected_app (BackendAppDefinition): Active backend app definition.

    Returns:
        tuple[RouteSecurityRequirement, ...]: App-owned requirements plus shared
            admin requirements when shared or database routes are active.

    Side Effects:
        None.
    """
    requirements = list(selected_app.openapi_route_security)
    if selected_app.include_shared_routes or selected_app.requires_database:
        requirements.extend(_iter_shared_security_requirements())
    return tuple(requirements)


def _set_security_schemes(openapi_schema: dict, selected_app: BackendAppDefinition) -> None:
    """
    Replace generated security schemes with selected-app schemes.

    Args:
        openapi_schema (dict): Mutable OpenAPI schema object.
        selected_app (BackendAppDefinition): Active backend app definition.

    Returns:
        None: The schema is modified in place.

    Side Effects:
        Mutates the OpenAPI schema components.
    """
    components = openapi_schema.setdefault("components", {})
    selected_schemes = _get_selected_security_schemes(selected_app)
    if selected_schemes:
        components["securitySchemes"] = selected_schemes
        return

    components.pop("securitySchemes", None)


def _apply_route_security(openapi_schema: dict, selected_app: BackendAppDefinition) -> None:
    """
    Apply selected-app security requirements to OpenAPI operations.

    Args:
        openapi_schema (dict): Mutable OpenAPI schema object.
        selected_app (BackendAppDefinition): Active backend app definition.

    Returns:
        None: The schema is modified in place.

    Side Effects:
        Mutates operation security metadata.
    """
    requirements = _iter_selected_route_security(selected_app)
    for path, path_item in openapi_schema.get("paths", {}).items():
        matching_requirements = [
            requirement
            for requirement in requirements
            if requirement.matches_path(path)
        ]
        for method, operation in path_item.items():
            if method not in HTTP_METHODS_WITH_SECURITY:
                continue
            operation.pop("security", None)
            operation_security = [
                requirement.requirement
                for requirement in matching_requirements
                if method in requirement.methods
            ]
            if operation_security:
                operation["security"] = operation_security


def setup_openapi(app: FastAPI) -> None:
    """
    Configure OpenAPI schema for the selected backend app.
    
    Args:
        app (FastAPI): The FastAPI application instance.

    Returns:
        None: Installs a custom OpenAPI factory on the application.

    Side Effects:
        Assigns `app.openapi`.
    """
    def custom_openapi():
        """
        Return the generated OpenAPI schema with selected-app security.

        Returns:
            dict: OpenAPI schema for the active backend app.

        Side Effects:
            Caches the schema on `app.openapi_schema`.
        """
        if app.openapi_schema:
            return app.openapi_schema
        
        selected_app = settings.get_backend_app_definition()
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        _set_security_schemes(openapi_schema, selected_app)
        _apply_route_security(openapi_schema, selected_app)
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi
