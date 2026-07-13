"""Runtime configuration for shared infrastructure and selected backend apps.

Settings are loaded from environment variables or the repository ``.env``
file. File-backed helpers support Docker secret injection without exposing
private values through app routes or committed configuration.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from apps.contracts import BackendAppDefinition


class Settings(BaseSettings):
    # API Settings
    PORT: int = 8000
    # Comma-separated list of allowed CORS origins.
    # Defaults to common local dev ports (Flutter web, Vite, React, etc.).
    # Override via CORS_ORIGINS env var for staging and production.
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:4200"
    IMAGE_TAG: str = "local non docker"
    REDIS_URL: str = "redis://localhost:6379"
    DEBUG: bool = False
    DEBUG_ENABLED: bool = False
    LOG_DIR: str = "/app/logs"
    LOG_LEVEL: str = ""
    LOG_TIMEZONE: str = "Europe/Berlin"
    ENABLE_HTTP_DEBUG_LOGGING: bool = False
    LOG_REQUEST_HEADERS: bool = False
    LOG_REQUEST_BODY: bool = False
    LOG_RESPONSE_HEADERS: bool = False
    LOG_RESPONSE_BODY: bool = False
    
    # Security Settings - Tiered API Keys
    ADMIN_API_KEY: str = ""  # Level 1: Read-only admin operations
    ADMIN_API_KEY_FILE: str = ""  # Path to file containing admin API key
    BACKUP_RESTORE_API_KEY: str = ""  # Level 2: Restore operations (destructive)
    BACKUP_RESTORE_API_KEY_FILE: str = ""  # Path to file containing restore API key
    BACKUP_DELETE_API_KEY: str = ""  # Level 3: Delete operations (destructive)
    BACKUP_DELETE_API_KEY_FILE: str = ""  # Path to file containing delete API key
    
    # Database Type Configuration
    # Official stability matrix: neo4j, postgresql/postgres, mongodb
    # Legacy compatibility types: mysql, sqlite
    # No-database app profiles: none
    DB_TYPE: Literal[
        "neo4j",
        "postgresql",
        "postgres",
        "mysql",
        "sqlite",
        "mongodb",
        "mongo",
        "none",
    ] = "neo4j"
    DB_MODE: Literal["local", "external", "none"] = "local"

    # Authentication Provider Configuration
    AUTH_PROVIDER: str = "cognito"

    # App profile configuration
    APP_PROFILE: str = "demo_app"
    APP_NAME: str = "Python API Template"
    APP_DESCRIPTION: str = "A flexible API template with SQL, Neo4j, and MongoDB support"

    # Backend-owned AI chat provider configuration.
    # Frontends must never receive these credentials or call provider endpoints
    # directly. Apps opt into AI by setting an OpenAI-compatible completions
    # endpoint and, when required by the provider, an API key or API key file.
    AI_CHAT_COMPLETIONS_ENDPOINT: str = ""
    AI_CHAT_API_KEY: str = ""
    AI_CHAT_API_KEY_FILE: str = ""
    AI_CHAT_MODEL: str = ""
    AI_CHAT_TEMPERATURE: float = 0.35
    AI_CHAT_MAX_TOKENS: int = 900
    AI_CHAT_TIMEOUT_SECONDS: float = 30.0
    AI_CHAT_DEBUG_ENABLED: bool = False
    AI_CHAT_DEBUG_INCLUDE_PROMPTS: bool = False
    AI_CHAT_LOG_DIR: str = ""

    # Browser Web Push public and private delivery configuration.
    WEB_PUSH_VAPID_PUBLIC_KEY: str = ""
    WEB_PUSH_VAPID_PUBLIC_KEY_FILE: str = ""
    WEB_PUSH_VAPID_PRIVATE_KEY: str = ""
    WEB_PUSH_VAPID_PRIVATE_KEY_FILE: str = ""
    WEB_PUSH_VAPID_SUBJECT: str = ""
    WEB_PUSH_DEFAULT_TTL_SECONDS: int = 86400
    WEB_PUSH_REQUEST_TIMEOUT_SECONDS: float = 10.0

    # Keycloak Configuration
    KEYCLOAK_SERVER_URL: Optional[str] = None
    KEYCLOAK_INTERNAL_URL: Optional[str] = None
    KEYCLOAK_REALM: Optional[str] = None
    KEYCLOAK_CLIENT_ID: Optional[str] = None
    KEYCLOAK_CLIENT_SECRET: Optional[str] = None
    KEYCLOAK_ISSUER_URL: Optional[str] = None
    KEYCLOAK_JWKS_URL: Optional[str] = None
    KEYCLOAK_ENFORCE_AUDIENCE: bool = False

    # AWS Cognito Configuration
    AWS_REGION: Optional[str] = None
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_USER_POOL_ID_FILE: str = ""  # Path to file containing Cognito User Pool ID
    COGNITO_APP_CLIENT_ID: Optional[str] = None
    COGNITO_APP_CLIENT_ID_FILE: str = ""  # Path to file containing Cognito App Client ID
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_ACCESS_KEY_ID_FILE: str = ""  # Path to file containing AWS Access Key ID
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_SECRET_ACCESS_KEY_FILE: str = ""  # Path to file containing AWS Secret Access Key

    # Neo4j Configuration
    NEO4J_URL: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_PASSWORD_FILE: str = ""  # Path to file containing DB password
    
    # SQL Database Configuration
    DATABASE_URL: str = ""  # Full connection string (for external databases)
    DB_HOST: str = "localhost"
    DB_NAME: str = ""
    DB_PORT: int = 5433
    MONGODB_URL: str = ""
    MONGODB_DB_NAME: str = "apidb"
    MONGODB_ROOT_USER: str = ""
    MONGODB_ROOT_PASSWORD: str = ""
    MONGODB_PORT: int = 27017
    # Database lock configuration (for /database/lock endpoints)
    DB_LOCK_TIMEOUT_SECONDS: int = 3600
    DB_LOCK_FAIL_CLOSED: bool = True

    model_config = SettingsConfigDict(env_file=".env")
    
    def get_admin_api_key(self) -> str:
        """Get admin API key from file or environment variable"""
        if self.ADMIN_API_KEY_FILE and Path(self.ADMIN_API_KEY_FILE).exists():
            return Path(self.ADMIN_API_KEY_FILE).read_text().strip()
        return self.ADMIN_API_KEY
    
    def get_restore_api_key(self) -> str:
        """Get restore API key from file or environment variable"""
        if self.BACKUP_RESTORE_API_KEY_FILE and Path(self.BACKUP_RESTORE_API_KEY_FILE).exists():
            return Path(self.BACKUP_RESTORE_API_KEY_FILE).read_text().strip()
        return self.BACKUP_RESTORE_API_KEY
    
    def get_delete_api_key(self) -> str:
        """Get delete API key from file or environment variable"""
        if self.BACKUP_DELETE_API_KEY_FILE and Path(self.BACKUP_DELETE_API_KEY_FILE).exists():
            return Path(self.BACKUP_DELETE_API_KEY_FILE).read_text().strip()
        return self.BACKUP_DELETE_API_KEY
    
    def get_db_password(self) -> str:
        """Get database password from file or environment variable"""
        if self.DB_PASSWORD_FILE and Path(self.DB_PASSWORD_FILE).exists():
            return Path(self.DB_PASSWORD_FILE).read_text().strip()
        return self.DB_PASSWORD
    
    def get_cognito_user_pool_id(self) -> Optional[str]:
        """Get Cognito User Pool ID from file or environment variable"""
        if self.COGNITO_USER_POOL_ID_FILE and Path(self.COGNITO_USER_POOL_ID_FILE).exists():
            return Path(self.COGNITO_USER_POOL_ID_FILE).read_text().strip()
        return self.COGNITO_USER_POOL_ID
    
    def get_cognito_app_client_id(self) -> Optional[str]:
        """Get Cognito App Client ID from file or environment variable"""
        if self.COGNITO_APP_CLIENT_ID_FILE and Path(self.COGNITO_APP_CLIENT_ID_FILE).exists():
            return Path(self.COGNITO_APP_CLIENT_ID_FILE).read_text().strip()
        return self.COGNITO_APP_CLIENT_ID
    
    def get_aws_access_key_id(self) -> Optional[str]:
        """Get AWS Access Key ID from file or environment variable"""
        if self.AWS_ACCESS_KEY_ID_FILE and Path(self.AWS_ACCESS_KEY_ID_FILE).exists():
            return Path(self.AWS_ACCESS_KEY_ID_FILE).read_text().strip()
        return self.AWS_ACCESS_KEY_ID
    
    def get_aws_secret_access_key(self) -> Optional[str]:
        """Get AWS Secret Access Key from file or environment variable"""
        if self.AWS_SECRET_ACCESS_KEY_FILE and Path(self.AWS_SECRET_ACCESS_KEY_FILE).exists():
            return Path(self.AWS_SECRET_ACCESS_KEY_FILE).read_text().strip()
        return self.AWS_SECRET_ACCESS_KEY

    def get_ai_chat_api_key(self) -> str:
        """Return the backend-only AI chat provider API key.

        Args:
            None.

        Returns:
            str: API key read from ``AI_CHAT_API_KEY_FILE`` when configured,
            otherwise ``AI_CHAT_API_KEY``.

        Raises:
            ValueError: When ``AI_CHAT_API_KEY_FILE`` is configured but missing.
        """
        return self.read_env_or_file(self.AI_CHAT_API_KEY, self.AI_CHAT_API_KEY_FILE)

    def get_web_push_vapid_public_key(self) -> str:
        """Return the browser-safe public VAPID application-server key.

        Args:
            None.

        Returns:
            str: Public key read from ``WEB_PUSH_VAPID_PUBLIC_KEY_FILE`` when
            configured, otherwise ``WEB_PUSH_VAPID_PUBLIC_KEY``.

        Raises:
            ValueError: When the configured public-key file does not exist.

        Side Effects:
            Reads the configured file when file-based injection is enabled.
        """
        return self.read_env_or_file(
            self.WEB_PUSH_VAPID_PUBLIC_KEY,
            self.WEB_PUSH_VAPID_PUBLIC_KEY_FILE,
        )

    def get_web_push_vapid_private_key_reference(self) -> str:
        """Return the backend-only VAPID private key or mounted-file path.

        File-backed configuration remains a path because ``pywebpush`` accepts
        PEM file paths directly and should read the secret only while signing.

        Args:
            None.

        Returns:
            str: Existing ``WEB_PUSH_VAPID_PRIVATE_KEY_FILE`` path when
            configured, otherwise the direct DER-encoded private-key value.

        Raises:
            ValueError: When the configured private-key file does not exist.

        Side Effects:
            Checks mounted-file existence without reading or logging it.
        """
        private_key_file = self.WEB_PUSH_VAPID_PRIVATE_KEY_FILE.strip()
        if private_key_file:
            path = Path(private_key_file)
            if not path.exists():
                raise ValueError(f"Configured secret file not found: {path}")
            return str(path)
        return self.WEB_PUSH_VAPID_PRIVATE_KEY.strip()

    def get_auth_provider(self) -> str:
        """Return the configured authentication provider.

        Falls back to provider auto-detection when AUTH_PROVIDER is unset.

        Returns:
            str: Normalized provider name (cognito, keycloak, dual, none).
        """
        provider = (self.AUTH_PROVIDER or "").strip().lower()
        if provider:
            return provider

        if self.is_keycloak_configured():
            return "keycloak"

        if self.is_cognito_configured():
            return "cognito"

        return "none"

    def is_cognito_configured(self) -> bool:
        """Return True when Cognito configuration values are present."""
        region = (self.AWS_REGION or "").strip()
        user_pool = (self.get_cognito_user_pool_id() or "").strip()
        return bool(region and user_pool)

    def is_keycloak_configured(self) -> bool:
        """Return True when Keycloak configuration values are present."""
        server_url = (self.KEYCLOAK_SERVER_URL or "").strip()
        realm = (self.KEYCLOAK_REALM or "").strip()
        client_id = (self.KEYCLOAK_CLIENT_ID or "").strip()
        return bool(server_url and realm and client_id)

    def get_keycloak_issuer_url(self) -> Optional[str]:
        """Return the Keycloak issuer URL for JWT validation.

        Returns:
            Optional[str]: Issuer URL or None when configuration is incomplete.
        """
        if self.KEYCLOAK_ISSUER_URL:
            return self.KEYCLOAK_ISSUER_URL.strip()

        server_url = (self.KEYCLOAK_SERVER_URL or "").strip()
        realm = (self.KEYCLOAK_REALM or "").strip()
        if not server_url or not realm:
            return None

        return f"{server_url.rstrip('/')}/realms/{realm}"

    def get_keycloak_jwks_url(self) -> Optional[str]:
        """Return the Keycloak JWKS URL used for token verification.

        Returns:
            Optional[str]: JWKS URL or None when configuration is incomplete.
        """
        if self.KEYCLOAK_JWKS_URL:
            return self.KEYCLOAK_JWKS_URL.strip()

        server_url = (self.KEYCLOAK_INTERNAL_URL or self.KEYCLOAK_SERVER_URL or "").strip()
        realm = (self.KEYCLOAK_REALM or "").strip()
        if not server_url or not realm:
            return None

        return f"{server_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/certs"
    
    def get_neo4j_uri(self) -> str:
        """Resolve Neo4j Bolt URI, preferring explicit NEO4J_URL when set."""
        if self.NEO4J_URL:
            return self.NEO4J_URL
        return f"bolt://{self.DB_HOST}:{self.DB_PORT}"

    def normalized_app_profile(self) -> str:
        """Return the normalized application profile identifier."""
        from apps.registry import normalize_backend_app_id

        return normalize_backend_app_id(self.APP_PROFILE)

    def get_backend_app_definition(self) -> "BackendAppDefinition":
        """Return the selected backend app definition from the app registry."""
        from apps.registry import get_backend_app_definition

        return get_backend_app_definition(self.APP_PROFILE)

    def normalized_db_type(self) -> str:
        """Return normalized database type."""
        db_type = (self.DB_TYPE or "").strip().lower()
        if db_type == "mongo":
            return "mongodb"
        return db_type

    def is_sql_database(self) -> bool:
        """Return True for SQL database backends."""
        return self.normalized_db_type() in {"postgresql", "postgres", "mysql", "sqlite"}

    def is_legacy_sql_database(self) -> bool:
        """Return True when running a legacy SQL compatibility backend."""
        return self.normalized_db_type() in {"mysql", "sqlite"}

    def is_mongodb(self) -> bool:
        """Return True when MongoDB is configured."""
        return self.normalized_db_type() == "mongodb"

    def get_mongodb_url(self) -> str:
        """Resolve MongoDB URI from explicit URL or host/port settings."""
        if self.MONGODB_URL:
            return self.MONGODB_URL

        credentials = ""
        user = (self.MONGODB_ROOT_USER or "").strip()
        password = (self.MONGODB_ROOT_PASSWORD or "").strip()
        if user:
            credentials = f"{user}:{password}@"

        auth_source = "/?authSource=admin" if credentials else ""
        return f"mongodb://{credentials}{self.DB_HOST}:{self.MONGODB_PORT}{auth_source}"
    
    def get_database_url(self) -> str:
        """Build database URL for SQL databases"""
        from sqlalchemy.engine import URL

        if self.DATABASE_URL:
            # Use provided URL (for external databases)
            return self.DATABASE_URL
        
        # Build URL from components (for local databases)
        password = self.get_db_password()
        db_type = self.normalized_db_type()
        if db_type in {"postgresql", "postgres"}:
            return URL.create(
                "postgresql",
                username=self.DB_USER,
                password=password,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=self.DB_NAME,
            ).render_as_string(hide_password=False)
        elif db_type == "mysql":
            return URL.create(
                "mysql+pymysql",
                username=self.DB_USER,
                password=password,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=self.DB_NAME,
            ).render_as_string(hide_password=False)
        elif db_type == "sqlite":
            return f"sqlite:///{self.DB_NAME}"
        return ""

    def get_cors_origins(self) -> list[str]:
        """
        Parse CORS_ORIGINS into a list of allowed origin strings.

        Splits the comma-separated CORS_ORIGINS setting and strips whitespace
        from each entry. Returns an empty list when CORS_ORIGINS is unset.

        Returns:
            list[str]: Allowed CORS origins for CORSMiddleware.

        Side Effects:
            None.
        """
        if not self.CORS_ORIGINS:
            return []
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def is_http_debug_logging_enabled(self) -> bool:
        """Return True when HTTP debug logging should be enabled."""
        return bool(self.DEBUG and self.ENABLE_HTTP_DEBUG_LOGGING)

    def read_env_or_file(self, value: str, file_path: str) -> str:
        """
        Read a configuration value from file or environment variable.

        File values take precedence over direct environment values. This
        supports Docker secrets and other file-based secret injection patterns.

        Args:
            value (str): Direct environment variable value.
            file_path (str): Path to file containing the value.

        Returns:
            str: The value from file if available, otherwise the direct value.

        Raises:
            ValueError: When file_path is set but the file does not exist.
        """
        if file_path:
            path_obj = Path(file_path)
            if path_obj.exists():
                return path_obj.read_text().strip()
            # File path is specified but file does not exist - this is a config error
            raise ValueError(f"Configuration file not found: {file_path}")
        return value


settings = Settings()
