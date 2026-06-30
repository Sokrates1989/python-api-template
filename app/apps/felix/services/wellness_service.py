"""Felix-owned facade for the shared wellness runtime.

The shared runtime remains product-neutral. Felix owns this facade so app code
can extend or replace wellness behavior without writing Felix-specific logic
inside global backend modules.
"""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class FelixWellnessService(SharedWellnessService):
    """
    Felix wellness service facade.

    The class currently inherits the shared runtime unchanged, while Felix owns
    route registration and SQL migrations in `app/apps/felix`.
    """
