"""
Compatibility wrapper for shared example routes.

New app definitions should opt in to the ``examples`` shared route group.
"""

from api.shared_routes.examples import router

__all__ = ["router"]
