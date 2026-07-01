"""
Legacy compatibility shim for shared database lock routes.

New app definitions should opt in to the ``database_lock`` shared route group
instead of importing this module directly.
"""
from api.shared_routes.database_lock import router

__all__ = ["router"]
