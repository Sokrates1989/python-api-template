"""Narrow backend-only identity administration for membership role grants.

The adapter receives only an immutable provider subject and allowlisted Booking
client roles. It never accepts passwords, profile payloads, arbitrary realm
roles, or unrestricted Keycloak operations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import requests

from api.settings import Settings, settings
from apps.booking_service.domain.tenancy import MembershipRole


@dataclass(frozen=True)
class IdentityAdministrationError(RuntimeError):
    """Represent a sanitized provider failure.

    Attributes:
        code: Stable machine-readable provider failure code.
        retryable: Whether a later delivery attempt may succeed.
    """

    code: str
    retryable: bool


class IdentityAdministrationAdapter(Protocol):
    """Define the only identity-provider mutation used by BKG-103."""

    async def ensure_client_roles(
        self,
        subject_id: str,
        roles: frozenset[MembershipRole],
    ) -> None:
        """Ensure [roles] exist on one immutable provider subject.

        Args:
            subject_id: Immutable Keycloak subject identifier.
            roles: Allowlisted Booking client roles to grant idempotently.

        Returns:
            None: Successful return means all requested roles are present.

        Raises:
            IdentityAdministrationError: For configuration, subject, token, or
                provider transport failures.
        """
        ...


class KeycloakIdentityAdministrationAdapter:
    """Grant exact Booking client roles through a confidential service account."""

    def __init__(
        self,
        runtime_settings: Settings = settings,
        *,
        request_session: requests.Session | None = None,
    ) -> None:
        """Bind public provider configuration and an injectable HTTP session.

        Args:
            runtime_settings: Runtime Keycloak and secret-file configuration.
            request_session: Optional session override for deterministic tests.

        Returns:
            None: Network activity remains deferred until role delivery.
        """
        self._settings = runtime_settings
        self._session = request_session or requests.Session()

    async def ensure_client_roles(
        self,
        subject_id: str,
        roles: frozenset[MembershipRole],
    ) -> None:
        """Grant only the requested allowlisted client roles.

        Args:
            subject_id: Immutable Keycloak user ID, never username or email.
            roles: Booking membership roles to grant on the public app client.

        Returns:
            None: Successful return means Keycloak accepted the idempotent map.

        Raises:
            IdentityAdministrationError: When configuration is incomplete,
                the subject is absent, or Keycloak rejects a request.

        Side Effects:
            Sends confidential backend requests to Keycloak.
        """
        if not roles:
            return
        self._validate_configuration()
        await asyncio.to_thread(self._ensure_roles_sync, subject_id, roles)

    def _validate_configuration(self) -> None:
        """Fail closed unless a dedicated confidential client is configured.

        Returns:
            None: Successful return means required public and secret values exist.

        Raises:
            IdentityAdministrationError: When provider or credential setup is
                absent. Secret-read details are intentionally suppressed.
        """
        public_values = (
            self._base_url(),
            str(self._settings.KEYCLOAK_REALM or "").strip(),
            str(self._settings.KEYCLOAK_CLIENT_ID or "").strip(),
            str(self._settings.KEYCLOAK_ADMIN_CLIENT_ID or "").strip(),
        )
        if self._settings.get_auth_provider() != "keycloak" or not all(public_values):
            raise IdentityAdministrationError("identity_provider_not_configured", False)
        try:
            self._settings.get_keycloak_admin_client_secret()
        except ValueError as error:
            raise IdentityAdministrationError(
                "identity_provider_not_configured", False
            ) from error

    def _ensure_roles_sync(
        self,
        subject_id: str,
        roles: frozenset[MembershipRole],
    ) -> None:
        """Perform the bounded blocking Keycloak requests.

        Args:
            subject_id: Immutable Keycloak user identifier.
            roles: Exact Booking client roles to assign.

        Returns:
            None: Successful return means the role mapping was accepted.

        Raises:
            IdentityAdministrationError: For safe classified provider errors.
        """
        token = self._admin_token()
        self._require_subject(token, subject_id)
        client_uuid = self._frontend_client_uuid(token)
        representations = [
            self._role_representation(token, client_uuid, role)
            for role in sorted(roles, key=lambda value: value.value)
        ]
        path = (
            f"/admin/realms/{self._realm()}/users/{quote(subject_id, safe='')}"
            f"/role-mappings/clients/{quote(client_uuid, safe='')}"
        )
        response = self._request("POST", token, path, payload=representations)
        if response.status_code != 204:
            raise IdentityAdministrationError("identity_role_grant_failed", True)

    def _admin_token(self) -> str:
        """Acquire a service-account token without exposing it to callers.

        Returns:
            str: Non-empty Keycloak access token used only in this adapter.

        Raises:
            IdentityAdministrationError: When token acquisition fails.
        """
        url = f"{self._base_url()}/realms/{self._realm()}/protocol/openid-connect/token"
        try:
            response = self._session.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": str(self._settings.KEYCLOAK_ADMIN_CLIENT_ID).strip(),
                    "client_secret": self._settings.get_keycloak_admin_client_secret(),
                },
                timeout=10,
            )
        except requests.RequestException as error:
            raise IdentityAdministrationError("identity_provider_unavailable", True) from error
        if response.status_code != 200:
            raise IdentityAdministrationError("identity_provider_auth_failed", True)
        token = str(response.json().get("access_token", "")).strip()
        if not token:
            raise IdentityAdministrationError("identity_provider_auth_failed", True)
        return token

    def _require_subject(self, token: str, subject_id: str) -> None:
        """Require the immutable subject to exist without loading profile data.

        Args:
            token: Confidential service-account access token.
            subject_id: Immutable provider user identifier.

        Returns:
            None: Successful return means the provider recognizes the subject.

        Raises:
            IdentityAdministrationError: For missing or unavailable subjects.
        """
        path = f"/admin/realms/{self._realm()}/users/{quote(subject_id, safe='')}"
        response = self._request("GET", token, path)
        if response.status_code == 404:
            raise IdentityAdministrationError("identity_subject_not_found", False)
        if response.status_code != 200:
            raise IdentityAdministrationError("identity_provider_unavailable", True)

    def _frontend_client_uuid(self, token: str) -> str:
        """Resolve the public Booking client UUID from configured client ID.

        Args:
            token: Confidential service-account access token.

        Returns:
            str: Internal Keycloak UUID for the role-owning public client.

        Raises:
            IdentityAdministrationError: When the client cannot be resolved.
        """
        path = f"/admin/realms/{self._realm()}/clients"
        response = self._request(
            "GET",
            token,
            path,
            params={"clientId": str(self._settings.KEYCLOAK_CLIENT_ID).strip()},
        )
        if response.status_code != 200:
            raise IdentityAdministrationError("identity_provider_unavailable", True)
        results = response.json()
        client_uuid = str(results[0].get("id", "")).strip() if results else ""
        if not client_uuid:
            raise IdentityAdministrationError("identity_client_not_found", False)
        return client_uuid

    def _role_representation(
        self,
        token: str,
        client_uuid: str,
        role: MembershipRole,
    ) -> dict[str, object]:
        """Read one exact allowlisted client-role representation.

        Args:
            token: Confidential service-account access token.
            client_uuid: Internal role-owning client identifier.
            role: Allowlisted Booking membership role.

        Returns:
            dict[str, object]: Keycloak representation required for assignment.

        Raises:
            IdentityAdministrationError: When the configured role is absent or
                the provider is unavailable.
        """
        path = (
            f"/admin/realms/{self._realm()}/clients/{quote(client_uuid, safe='')}"
            f"/roles/{quote(role.value, safe='')}"
        )
        response = self._request("GET", token, path)
        if response.status_code == 404:
            raise IdentityAdministrationError("identity_role_not_configured", False)
        if response.status_code != 200:
            raise IdentityAdministrationError("identity_provider_unavailable", True)
        return response.json()

    def _request(
        self,
        method: str,
        token: str,
        path: str,
        *,
        payload: object | None = None,
        params: dict[str, str] | None = None,
    ) -> requests.Response:
        """Send one authenticated admin request with bounded timeout.

        Args:
            method: HTTP method required by the bounded operation.
            token: Service-account token retained only in memory.
            path: Keycloak admin path built from quoted opaque identifiers.
            payload: Optional JSON role-mapping payload.
            params: Optional non-secret lookup parameters.

        Returns:
            requests.Response: Provider response for status-only classification.

        Raises:
            IdentityAdministrationError: When transport fails before a response.
        """
        try:
            return self._session.request(
                method,
                f"{self._base_url()}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                params=params,
                timeout=10,
            )
        except requests.RequestException as error:
            raise IdentityAdministrationError("identity_provider_unavailable", True) from error

    def _base_url(self) -> str:
        """Return the internal-preferred Keycloak base URL.

        Returns:
            str: Normalized URL without a trailing slash, possibly empty.
        """
        value = self._settings.KEYCLOAK_INTERNAL_URL or self._settings.KEYCLOAK_SERVER_URL or ""
        return str(value).strip().rstrip("/")

    def _realm(self) -> str:
        """Return the URL-quoted configured realm.

        Returns:
            str: Realm safe for one URL path segment.
        """
        return quote(str(self._settings.KEYCLOAK_REALM or "").strip(), safe="")
