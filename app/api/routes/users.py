"""
Legacy compatibility shim for shared user routes.

New app definitions should opt in to the ``users`` shared route group instead
of importing this module directly.
"""
from api.shared_routes.users import router

__all__ = ["router"]
