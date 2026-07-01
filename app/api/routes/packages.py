"""
Legacy compatibility shim for shared package routes.

New app definitions should opt in to the ``packages`` shared route group
instead of importing this module directly.
"""
from api.shared_routes.packages import router

__all__ = ["router"]
