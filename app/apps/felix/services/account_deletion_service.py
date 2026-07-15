"""Delete one authenticated Felix account from active backend systems.

The service owns the destructive ordering required by the self-service account
erasure endpoint. It validates identity-provider support before mutation,
purges provider-specific application records, and removes the external
identity last so a partially completed request can be retried with the still
valid bearer session.

Dependencies:
    - Active database handler and SQL user/sync models.
    - Runtime authentication settings.
    - ``requests`` for Keycloak service-account administration.

Usage:
    Instantiate ``FelixAccountDeletionService`` from the authenticated Felix
    account route and call ``delete_account`` with the token subject only.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
from sqlalchemy import delete

from api.settings import Settings, settings
from backend.database import get_database_handler
from models.sql.sync_conflict_log import SyncConflictLog
from models.sql.sync_operation_log import SyncOperationLog
from models.sql.user import User


@dataclass(frozen=True)
class FelixAccountDeletionResult:
    """Describe a completed account erasure without exposing row counts.

    Attributes:
        backend_data_deleted (bool): Whether active backend records were
            purged successfully.
        identity_deleted (bool): Whether the configured external identity was
            deleted or no external identity provider was configured.
    """

    backend_data_deleted: bool
    identity_deleted: bool


class FelixAccountDeletionError(RuntimeError):
    """Represent a safe, classified account-erasure failure.

    Args:
        code (str): Stable non-sensitive error code for route mapping.
        message (str): Safe operator-facing explanation.
        backend_data_deleted (bool): Whether backend purge already completed.

    Attributes:
        code (str): Stable failure code.
        backend_data_deleted (bool): Partial-completion marker used to guide a
            retry without falsely reporting success.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        backend_data_deleted: bool = False,
    ) -> None:
        """Initialize one classified deletion failure.

        Args:
            code (str): Stable non-sensitive error code.
            message (str): Safe error description.
            backend_data_deleted (bool): Whether active backend data is gone.

        Returns:
            None.
        """
        super().__init__(message)
        self.code = code
        self.backend_data_deleted = backend_data_deleted


class KeycloakIdentityDeletionGateway:
    """Delete the authenticated subject through a Keycloak service account.

    The gateway supports ``AUTH_PROVIDER=keycloak`` and the explicit ``none``
    development provider. Cognito and dual-provider deployments fail closed
    before backend mutation until an equivalent provider-owned deletion
    implementation exists.
    """

    def __init__(
        self,
        runtime_settings: Settings = settings,
        *,
        request_session: requests.Session | None = None,
    ) -> None:
        """Create a deferred Keycloak administrative gateway.

        Args:
            runtime_settings (Settings): Runtime provider configuration.
            request_session (requests.Session | None): Optional HTTP session
                override for tests. A private session is created when omitted.

        Returns:
            None.

        Side Effects:
            Creates an in-memory HTTP session when no override is supplied.
        """
        self._settings = runtime_settings
        self._session = request_session or requests.Session()

    def validate_support(self) -> None:
        """Validate provider support and required confidential credentials.

        Returns:
            None.

        Raises:
            FelixAccountDeletionError: When the provider is unsupported or a
                Keycloak administrative credential is missing.
        """
        provider = self._settings.get_auth_provider()
        if provider == "none":
            return
        if provider != "keycloak":
            raise FelixAccountDeletionError(
                "identity_provider_unsupported",
                "Account deletion is not configured for this identity provider.",
            )
        if not self._keycloak_configuration_complete():
            raise FelixAccountDeletionError(
                "identity_provider_not_configured",
                "Keycloak account deletion is not fully configured.",
            )

    async def delete_identity(self, user_id: str) -> None:
        """Delete one provider identity or complete immediately for ``none``.

        Args:
            user_id (str): Authenticated token subject to delete.

        Returns:
            None.

        Raises:
            FelixAccountDeletionError: When Keycloak token acquisition or user
                deletion fails. A missing Keycloak user is treated as success
                to keep retries idempotent.

        Side Effects:
            Performs Keycloak token and administrative deletion requests.
        """
        self.validate_support()
        if self._settings.get_auth_provider() == "none":
            return
        await asyncio.to_thread(self._delete_keycloak_identity, user_id)

    def _delete_keycloak_identity(self, user_id: str) -> None:
        """Perform blocking Keycloak token and user deletion requests.

        Args:
            user_id (str): Authenticated Keycloak subject.

        Returns:
            None.

        Raises:
            FelixAccountDeletionError: When Keycloak rejects either request.

        Side Effects:
            Sends confidential client credentials and a user DELETE request.
        """
        base_url = self._keycloak_base_url()
        realm = quote(str(self._settings.KEYCLOAK_REALM).strip(), safe="")
        token_url = (
            f"{base_url}/realms/{realm}/protocol/openid-connect/token"
        )
        token_response = self._session.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": str(self._settings.KEYCLOAK_CLIENT_ID).strip(),
                "client_secret": str(self._settings.KEYCLOAK_CLIENT_SECRET).strip(),
            },
            timeout=10,
        )
        if token_response.status_code != 200:
            raise FelixAccountDeletionError(
                "identity_token_failed",
                "Keycloak did not authorize account deletion.",
            )
        access_token = str(token_response.json().get("access_token", "")).strip()
        if not access_token:
            raise FelixAccountDeletionError(
                "identity_token_failed",
                "Keycloak returned no administrative access token.",
            )

        delete_url = (
            f"{base_url}/admin/realms/{realm}/users/"
            f"{quote(user_id, safe='')}"
        )
        delete_response = self._session.delete(
            delete_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if delete_response.status_code not in {204, 404}:
            raise FelixAccountDeletionError(
                "identity_deletion_failed",
                "Keycloak did not complete account deletion.",
            )

    def _keycloak_configuration_complete(self) -> bool:
        """Return whether every Keycloak deletion setting is present.

        Returns:
            bool: True when URL, realm, client id, and secret are non-empty.
        """
        return all(
            str(value or "").strip()
            for value in (
                self._settings.KEYCLOAK_INTERNAL_URL
                or self._settings.KEYCLOAK_SERVER_URL,
                self._settings.KEYCLOAK_REALM,
                self._settings.KEYCLOAK_CLIENT_ID,
                self._settings.KEYCLOAK_CLIENT_SECRET,
            )
        )

    def _keycloak_base_url(self) -> str:
        """Resolve the internal Keycloak base URL without a trailing slash.

        Returns:
            str: Internal URL when configured, otherwise the public server URL.
        """
        value = (
            self._settings.KEYCLOAK_INTERNAL_URL
            or self._settings.KEYCLOAK_SERVER_URL
            or ""
        )
        return str(value).strip().rstrip("/")


class FelixAccountDeletionService:
    """Coordinate provider-aware Felix data and identity erasure."""

    def __init__(
        self,
        *,
        database_handler: Any | None = None,
        identity_gateway: KeycloakIdentityDeletionGateway | None = None,
    ) -> None:
        """Bind deletion to the active database and identity provider.

        Args:
            database_handler (Any | None): Optional active-provider override.
            identity_gateway (KeycloakIdentityDeletionGateway | None): Optional
                identity deletion override for tests.

        Returns:
            None.

        Side Effects:
            Resolves the configured database handler when omitted.
        """
        self._handler = database_handler or get_database_handler()
        self._identity_gateway = identity_gateway or KeycloakIdentityDeletionGateway()

    async def delete_account(self, user_id: str) -> FelixAccountDeletionResult:
        """Delete one authenticated account from active Felix systems.

        Args:
            user_id (str): Exact subject derived from the verified bearer token.

        Returns:
            FelixAccountDeletionResult: Completed backend and identity markers.

        Raises:
            FelixAccountDeletionError: When input, provider support, backend
                purge, or external identity deletion fails.

        Side Effects:
            Permanently deletes active user records and the external identity.
        """
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            raise FelixAccountDeletionError(
                "invalid_user_identity",
                "Authenticated account identity is missing.",
            )
        self._identity_gateway.validate_support()
        await self._delete_backend_data(normalized_user_id)
        try:
            await self._identity_gateway.delete_identity(normalized_user_id)
        except FelixAccountDeletionError as exc:
            raise FelixAccountDeletionError(
                exc.code,
                str(exc),
                backend_data_deleted=True,
            ) from exc
        return FelixAccountDeletionResult(
            backend_data_deleted=True,
            identity_deleted=True,
        )

    async def _delete_backend_data(self, user_id: str) -> None:
        """Dispatch permanent data deletion to the active database provider.

        Args:
            user_id (str): Authenticated account owner.

        Returns:
            None.

        Raises:
            FelixAccountDeletionError: When the provider is unsupported or its
                purge operation fails.
        """
        try:
            provider = str(getattr(self._handler, "db_type", "")).strip().lower()
            if provider in {"sql", "postgresql", "postgres", "mysql", "sqlite"}:
                await self._delete_sql_data(user_id)
                return
            if provider in {"mongodb", "mongo"}:
                await self._delete_mongodb_data(user_id)
                return
            if provider == "neo4j":
                await asyncio.to_thread(self._delete_neo4j_data, user_id)
                return
            raise FelixAccountDeletionError(
                "database_provider_unsupported",
                "Account deletion is not configured for this database provider.",
            )
        except FelixAccountDeletionError:
            raise
        except Exception as exc:
            raise FelixAccountDeletionError(
                "backend_deletion_failed",
                "Felix could not delete the active backend account data.",
            ) from exc

    async def _delete_sql_data(self, user_id: str) -> None:
        """Delete SQL logs and the cascading user root in one transaction.

        Args:
            user_id (str): Authenticated account owner.

        Returns:
            None.

        Side Effects:
            Deletes sync diagnostics explicitly and all foreign-key-owned Felix
            rows through the ``users.id`` cascade.
        """
        async with self._handler.AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    delete(SyncConflictLog).where(SyncConflictLog.user_id == user_id)
                )
                await session.execute(
                    delete(SyncOperationLog).where(SyncOperationLog.user_id == user_id)
                )
                await session.execute(delete(User).where(User.id == user_id))

    async def _delete_mongodb_data(self, user_id: str) -> None:
        """Delete every owner-scoped Mongo document plus the user profile.

        Args:
            user_id (str): Authenticated account owner.

        Returns:
            None.

        Side Effects:
            Scans active collection names and removes documents whose canonical
            ``user_id`` matches, then removes the shared ``users.id`` record.
        """
        collection_names = await self._handler.database.list_collection_names()
        for collection_name in collection_names:
            if collection_name.startswith("system."):
                continue
            collection = self._handler.database[collection_name]
            if collection_name == "users":
                await collection.delete_many({"id": user_id})
                continue
            await collection.delete_many({"user_id": user_id})

    def _delete_neo4j_data(self, user_id: str) -> None:
        """Delete owner-scoped Neo4j nodes and the shared user root.

        Args:
            user_id (str): Authenticated account owner.

        Returns:
            None.

        Side Effects:
            Detaches and deletes every node with the canonical ``user_id``
            property, then the matching ``User.id`` node.
        """
        with self._handler.driver.session() as session:
            session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n",
                user_id=user_id,
            ).consume()
            session.run(
                "MATCH (u:User {id: $user_id}) DETACH DELETE u",
                user_id=user_id,
            ).consume()
