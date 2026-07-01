"""
Legacy compatibility shim for shared file routes.

New app definitions should opt in to the ``files`` shared route group instead
of importing this module directly.
"""
from api.shared_routes.files import router

__all__ = ["router"]
