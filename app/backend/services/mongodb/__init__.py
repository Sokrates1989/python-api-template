"""MongoDB-specific service implementations."""

from .example_service import ExampleService as MongoExampleService
from .user_service import UserService as MongoUserService

__all__ = ["MongoExampleService", "MongoUserService"]
