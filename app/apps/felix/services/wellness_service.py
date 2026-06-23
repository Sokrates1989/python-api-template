"""Wellness service facade owned by the Felix backend app."""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class FelixWellnessService(SharedWellnessService):
    """Felix wellness service facade."""
