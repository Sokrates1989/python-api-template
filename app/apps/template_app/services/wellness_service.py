"""Template App-owned facade for the shared wellness runtime.

The template app uses wellness as reusable example functionality. Its route
registration and SQL migrations remain app-owned even though the runtime logic
is shared.
"""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class TemplateAppWellnessService(SharedWellnessService):
    """
    Template App wellness service facade.

    The class inherits the shared runtime unchanged while the app slice owns
    route registration and SQL migrations.
    """
