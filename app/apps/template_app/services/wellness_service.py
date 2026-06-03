"""Wellness service entry point owned by the template backend app."""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class TemplateAppWellnessService(SharedWellnessService):
    """Template app wellness service facade."""
