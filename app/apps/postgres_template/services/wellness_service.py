"""Postgres Template-owned facade for the shared wellness runtime.

The Postgres Template app uses wellness as SQL-backed example functionality.
Its route registration and SQL migrations remain app-owned even though the
runtime logic is shared.
"""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class PostgresTemplateWellnessService(SharedWellnessService):
    """
    Postgres Template wellness service facade.

    The class inherits the shared runtime unchanged while the app slice owns
    route registration and SQL migrations.
    """
