"""
App metadata for secure messaging backend.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SecureMessagingAppConfig:
    """
    Configuration metadata for the secure messaging app.

    Attributes:
        app_id (str): Stable backend app identifier.
        display_name (str): Human-readable name for logs and diagnostics.
        backend_data_profile (str): Expected backend/database profile.
        notify_mount_prefix (str): Router mount prefix (empty for direct mount).
        notify_public_prefix (str): Publicly visible route prefix.
        exposes_sync_routes (bool): Whether sync routes are exposed.
        requires_database (bool): Whether database is required.
        requires_redis (bool): Whether Redis is required.
        include_shared_routes (bool): Whether to include shared routes.

    Returns:
        None: Dataclass instances are used as immutable config.

    Side Effects:
        None.
    """

    app_id: str = "secure_messaging"
    display_name: str = "Secure Messaging"
    backend_data_profile: str = "none"
    notify_mount_prefix: str = ""
    notify_public_prefix: str = "/v1/notify"
    exposes_sync_routes: bool = False
    requires_database: bool = False
    requires_redis: bool = False
    include_shared_routes: bool = False
