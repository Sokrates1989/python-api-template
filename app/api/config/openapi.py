"""OpenAPI configuration for Swagger UI."""
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def setup_openapi(app: FastAPI) -> None:
    """
    Configure OpenAPI schema for the FastAPI application with security schemes.
    
    Args:
        app: The FastAPI application instance
    """
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        
        # Define security schemes that will appear in Swagger UI "Authorize" button
        security_schemes = openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
        security_schemes.update({
            "X-Admin-Key": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Admin-Key",
                "description": "Admin API Key for protected operations"
            },
            "X-Restore-Key": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Restore-Key",
                "description": "Restore API Key for destructive restore operations"
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Bearer token alternative for external backup-restore lock orchestration."
            },
        })

        # Add security requirements to packages, lock, and stats endpoints
        for path, path_item in openapi_schema.get("paths", {}).items():
            if path.startswith("/packages/"):
                for method, operation in path_item.items():
                    if method in ["get", "post", "delete", "put", "patch"]:
                        operation["security"] = [{"X-Admin-Key": []}]
            if path.startswith("/database/"):
                for method, operation in path_item.items():
                    if method in ["get", "post", "delete", "put", "patch"]:
                        operation["security"] = [{"X-Admin-Key": []}, {"BearerAuth": []}]
            if path == "/stats":
                for method, operation in path_item.items():
                    if method in ["get"]:
                        operation["security"] = [{"X-Admin-Key": []}]
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi
