"""Wellness service entry point owned by the MongoDB Template backend app."""
from backend.shared_services.wellness_service import WellnessService as SharedWellnessService


class MongoDBTemplateWellnessService(SharedWellnessService):
    """MongoDB Template wellness service facade."""
