"""Provider adapters that implement domain ports."""

from .backup_capability_factory import create_backup_capability
from .example_repository_factory import create_example_repository
from .provider_capability_factory import (
    get_current_provider_capabilities,
    get_provider_capabilities_for_db_type,
)
from .user_repository_factory import create_user_repository

__all__ = [
    "create_backup_capability",
    "create_example_repository",
    "get_current_provider_capabilities",
    "get_provider_capabilities_for_db_type",
    "create_user_repository",
]
