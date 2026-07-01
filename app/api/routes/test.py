"""
Legacy compatibility shim for shared test routes.

New app definitions should opt in to the ``test`` shared route group instead
of importing this module directly.
"""
from api.shared_routes.test import router

__all__ = ["router"]
