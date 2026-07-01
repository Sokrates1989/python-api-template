"""
Legacy compatibility shim for shared example routes.

New app definitions should opt in to the ``examples`` shared route group
instead of importing this module directly.
"""
from api.shared_routes.examples import router

__all__ = ["router"]
