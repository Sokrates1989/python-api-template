"""Domain ports (provider-agnostic contracts)."""

from .backup_capability import BackupCapability
from .example_repository import ExampleOperationResult, ExampleRepository
from .provider_capabilities import ProviderCapabilities
from .user_repository import UserOperationResult, UserRepository

__all__ = [
    "BackupCapability",
    "ExampleRepository",
    "ExampleOperationResult",
    "ProviderCapabilities",
    "UserRepository",
    "UserOperationResult",
]
