"""Wellness service entry point owned by the Postgres Template backend app."""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class PostgresTemplateWellnessService(SharedWellnessService):
    """Postgres Template wellness service facade."""
