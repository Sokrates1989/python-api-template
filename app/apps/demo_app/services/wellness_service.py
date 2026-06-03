"""Wellness service entry point owned by the demo backend app."""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class DemoAppWellnessService(SharedWellnessService):
    """Demo app wellness service facade."""
