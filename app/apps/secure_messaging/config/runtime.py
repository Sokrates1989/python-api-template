"""
Runtime configuration for secure messaging app.

Loads settings from environment variables and Docker secrets files.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SecureMessagingSettings:
    """
    Runtime settings for secure messaging loaded from environment.

    This class provides lazy loading of settings from environment variables
    and Docker secret files. File values take precedence over direct env vars.

    Attributes:
        None: Settings are loaded dynamically from environment.

    Returns:
        None: Dataclass is instantiated empty, values read on demand.

    Side Effects:
        Reads from environment and filesystem.
    """

    @staticmethod
    def _read_env_or_file(env_name: str, file_env_name: str) -> str:
        """
        Read a value from file (via file_env_name) or env (via env_name).

        File values take precedence. If file_env_name is set but file
        doesn't exist, raises ValueError for configuration errors.

        Args:
            env_name (str): Base environment variable name.
            file_env_name (str): Environment variable containing file path.

        Returns:
            str: The configuration value.

        Raises:
            ValueError: When configured file does not exist.
        """
        file_path = os.getenv(file_env_name, "").strip()
        if file_path:
            path_obj = Path(file_path)
            if path_obj.exists():
                return path_obj.read_text().strip()
            raise ValueError(f"Configuration file not found: {file_path}")
        return os.getenv(env_name, "")

    @classmethod
    def get_auth_token(cls) -> str:
        """
        Load the single authentication token from env or file.

        Returns:
            str: The bearer token for API authentication.

        Raises:
            ValueError: When token is not configured.
        """
        token = cls._read_env_or_file(
            "SECURE_MESSAGING_AUTH_TOKEN",
            "SECURE_MESSAGING_AUTH_TOKEN_FILE",
        )
        if not token:
            raise ValueError(
                "SECURE_MESSAGING_AUTH_TOKEN or SECURE_MESSAGING_AUTH_TOKEN_FILE must be set"
            )
        return token

    @classmethod
    def get_rate_limit_per_minute(cls) -> int:
        """Return rate limit per minute, default 30."""
        value = os.getenv("SECURE_MESSAGING_RATE_LIMIT_PER_MINUTE", "30")
        try:
            return int(value)
        except ValueError:
            return 30

    # Telegram senders configuration (split: metadata + secrets)
    @classmethod
    def get_telegram_senders(cls) -> dict[str, dict[str, str]]:
        """
        Load merged Telegram sender configurations from JSON.

        Merges metadata JSON with tokens from separate secrets JSON.

        Returns:
            dict[str, dict]: Map of sender names to merged {token, chat_id} configs.

        Raises:
            ValueError: When JSON is invalid.
        """
        # Load metadata (non-secrets: chat_id, etc.)
        metadata_content = cls._read_env_or_file(
            "SECURE_MESSAGING_TELEGRAM_SENDERS_JSON",
            "SECURE_MESSAGING_TELEGRAM_SENDERS_FILE",
        )
        # Load secrets (tokens)
        secrets_content = cls._read_env_or_file(
            "SECURE_MESSAGING_TELEGRAM_SENDER_TOKENS_JSON",
            "SECURE_MESSAGING_TELEGRAM_SENDER_TOKENS_FILE",
        )

        senders: dict[str, dict[str, str]] = {}

        # Parse metadata
        if metadata_content:
            try:
                metadata = json.loads(metadata_content)
                if not isinstance(metadata, dict):
                    raise ValueError("Telegram senders metadata must be a JSON object")
                senders = {str(k): dict(v) for k, v in metadata.items()}
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in Telegram senders: {exc}") from exc

        # Merge secrets (tokens)
        if secrets_content:
            try:
                secrets = json.loads(secrets_content)
                if not isinstance(secrets, dict):
                    raise ValueError("Telegram sender tokens must be a JSON object")
                for sender_name, token in secrets.items():
                    sender_name = str(sender_name)
                    if sender_name not in senders:
                        senders[sender_name] = {}
                    senders[sender_name]["token"] = str(token)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in Telegram sender tokens: {exc}") from exc

        return senders

    @classmethod
    def get_telegram_sender_config(cls, sender_name: str) -> dict[str, str] | None:
        """
        Get merged configuration for a specific Telegram sender.

        Args:
            sender_name (str): Name of the sender to retrieve.

        Returns:
            dict[str, str] | None: Sender config with token and chat_id, or None.
        """
        senders = cls.get_telegram_senders()
        return senders.get(sender_name)

    # Email senders configuration (split: metadata + secrets)
    @classmethod
    def get_email_senders(cls) -> dict[str, dict[str, str]]:
        """
        Load merged email sender configurations from JSON.

        Merges metadata JSON with passwords from separate secrets JSON.

        Returns:
            dict[str, dict]: Map of sender names to merged SMTP configs.

        Raises:
            ValueError: When JSON is invalid.
        """
        # Load metadata (non-secrets: host, port, username, etc.)
        metadata_content = cls._read_env_or_file(
            "SECURE_MESSAGING_EMAIL_SENDERS_JSON",
            "SECURE_MESSAGING_EMAIL_SENDERS_FILE",
        )
        # Load secrets (passwords)
        secrets_content = cls._read_env_or_file(
            "SECURE_MESSAGING_EMAIL_SENDER_PASSWORDS_JSON",
            "SECURE_MESSAGING_EMAIL_SENDER_PASSWORDS_FILE",
        )

        senders: dict[str, dict[str, str]] = {}

        # Parse metadata
        if metadata_content:
            try:
                metadata = json.loads(metadata_content)
                if not isinstance(metadata, dict):
                    raise ValueError("Email senders metadata must be a JSON object")
                senders = {str(k): dict(v) for k, v in metadata.items()}
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in email senders: {exc}") from exc

        # Merge secrets (passwords)
        if secrets_content:
            try:
                secrets = json.loads(secrets_content)
                if not isinstance(secrets, dict):
                    raise ValueError("Email sender passwords must be a JSON object")
                for sender_name, password in secrets.items():
                    sender_name = str(sender_name)
                    if sender_name not in senders:
                        senders[sender_name] = {}
                    senders[sender_name]["password"] = str(password)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in email sender passwords: {exc}") from exc

        return senders

    @classmethod
    def get_email_sender_config(cls, sender_name: str) -> dict[str, str] | None:
        """
        Get merged configuration for a specific email sender.

        Args:
            sender_name (str): Name of the sender to retrieve.

        Returns:
            dict[str, str] | None: Sender config with host, port, username,
                password, use_tls, from_addr, default_to, or None.
        """
        senders = cls.get_email_senders()
        return senders.get(sender_name)
