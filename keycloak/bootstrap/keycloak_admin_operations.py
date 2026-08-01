"""Bounded Keycloak administration primitives for local realm bootstrap.

The module groups reusable client/user role operations, including the narrow
service-account permissions required by Booking membership qualification.
"""

from __future__ import annotations

from typing import Iterable

import requests

from bootstrap_errors import KeycloakBootstrapError


def request_with_token(
    method: str,
    base_url: str,
    token: str,
    path: str,
    json_body: dict | list | None = None,
    params: dict | None = None,
) -> requests.Response:
    """Send an authenticated request to the Keycloak admin API.

    Args:
        method: HTTP method.
        base_url: Keycloak base URL.
        token: Bearer token retained only in request memory.
        path: Keycloak administrative API path.
        json_body: Optional JSON body.
        params: Optional query parameters.

    Returns:
        requests.Response: Keycloak response for bounded status handling.
    """
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return requests.request(
        method,
        url,
        headers=headers,
        json=json_body,
        params=params,
        timeout=20,
    )


def resolve_client_id(
    base_url: str,
    token: str,
    realm: str,
    client_id: str,
) -> str | None:
    """Resolve a client UUID by public client ID.

    Args:
        base_url: Keycloak base URL.
        token: Bootstrap administrator token.
        realm: Realm name.
        client_id: Public client ID to search for.

    Returns:
        str | None: Internal client UUID when found.
    """
    response = request_with_token(
        "GET",
        base_url,
        token,
        f"/admin/realms/{realm}/clients",
        params={"clientId": client_id},
    )
    if response.status_code != 200:
        return None
    results = response.json()
    if not results:
        return None
    return results[0].get("id")


def get_role_representations(
    base_url: str,
    token: str,
    realm: str,
    roles: Iterable[str],
    *,
    skip_missing: bool = False,
) -> tuple[list[dict[str, object]], list[str]]:
    """Resolve realm-role representations for assignment.

    Args:
        base_url: Keycloak base URL.
        token: Bootstrap administrator token.
        realm: Realm name.
        roles: Role names to resolve.
        skip_missing: Whether absent roles are reported rather than rejected.

    Returns:
        tuple[list[dict[str, object]], list[str]]: Representations and missing roles.

    Raises:
        KeycloakBootstrapError: When a required role lookup fails.
    """
    representations: list[dict[str, object]] = []
    missing_roles: list[str] = []
    for role in roles:
        response = request_with_token(
            "GET", base_url, token, f"/admin/realms/{realm}/roles/{role}"
        )
        if response.status_code == 404 and skip_missing:
            missing_roles.append(role)
            continue
        if response.status_code != 200:
            raise KeycloakBootstrapError(f"Failed to resolve role '{role}'")
        representations.append(response.json())
    return representations, missing_roles


def assign_realm_roles(
    base_url: str,
    token: str,
    realm: str,
    user_id: str,
    roles: Iterable[str],
    username: str,
) -> None:
    """Assign existing realm roles to one user.

    Args:
        base_url: Keycloak base URL.
        token: Bootstrap administrator token.
        realm: Realm name.
        user_id: Internal user UUID.
        roles: Role names to assign.
        username: Public fixture label used only in a missing-role warning.

    Returns:
        None: Successful return means mappings were accepted or absent.

    Raises:
        KeycloakBootstrapError: When Keycloak rejects the assignment.
    """
    roles_list = list(roles)
    role_reps, missing_roles = get_role_representations(
        base_url, token, realm, roles_list, skip_missing=True
    )
    if missing_roles:
        print(f"  ⚠ Skipping missing roles for '{username}': {', '.join(missing_roles)}")
    if not role_reps:
        print(f"  ⚠ No roles to assign for '{username}'")
        return
    response = request_with_token(
        "POST",
        base_url,
        token,
        f"/admin/realms/{realm}/users/{user_id}/role-mappings/realm",
        role_reps,
    )
    if response.status_code != 204:
        raise KeycloakBootstrapError("Failed to assign realm roles to user")


def assign_client_roles(
    base_url: str,
    token: str,
    realm: str,
    client_uuid: str,
    user_id: str,
    roles: Iterable[str],
) -> None:
    """Assign exact existing client roles to one user.

    Args:
        base_url: Keycloak base URL.
        token: Bootstrap administrator token.
        realm: Realm name.
        client_uuid: Internal role-owning client UUID.
        user_id: Internal Keycloak user UUID.
        roles: Exact client-role names; absent roles are ignored.

    Returns:
        None: Successful return means available mappings were accepted.

    Raises:
        KeycloakBootstrapError: When Keycloak rejects the assignment.
    """
    representations: list[dict[str, object]] = []
    for role in roles:
        response = request_with_token(
            "GET",
            base_url,
            token,
            f"/admin/realms/{realm}/clients/{client_uuid}/roles/{role}",
        )
        if response.status_code == 404:
            continue
        if response.status_code != 200:
            raise KeycloakBootstrapError("Failed to resolve client role")
        representations.append(response.json())
    if not representations:
        return
    response = request_with_token(
        "POST",
        base_url,
        token,
        f"/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{client_uuid}",
        representations,
    )
    if response.status_code != 204:
        raise KeycloakBootstrapError("Failed to assign client roles to user")


def resolve_service_account_user_id(
    base_url: str,
    token: str,
    realm: str,
    client_uuid: str,
) -> str:
    """Resolve the backend client's service-account user identifier.

    Args:
        base_url: Keycloak base URL.
        token: Bootstrap administrator token.
        realm: Realm name.
        client_uuid: Confidential backend client UUID.

    Returns:
        str: Internal Keycloak service-account user UUID.

    Raises:
        KeycloakBootstrapError: When lookup fails or omits the user ID.
    """
    response = request_with_token(
        "GET",
        base_url,
        token,
        f"/admin/realms/{realm}/clients/{client_uuid}/service-account-user",
    )
    if response.status_code != 200:
        raise KeycloakBootstrapError("Failed to fetch service account user")
    user_id = response.json().get("id")
    if not user_id:
        raise KeycloakBootstrapError("Service account user id missing")
    return str(user_id)


def assign_service_account_role(
    base_url: str,
    token: str,
    realm: str,
    client_uuid: str,
    role: str,
) -> None:
    """Assign one realm role to the backend service account.

    Args:
        base_url: Keycloak base URL.
        token: Bootstrap administrator token.
        realm: Realm name.
        client_uuid: Confidential backend client UUID.
        role: Exact realm role name.

    Returns:
        None: Successful return means the mapping was accepted.
    """
    user_id = resolve_service_account_user_id(base_url, token, realm, client_uuid)
    assign_realm_roles(base_url, token, realm, user_id, [role], "service-account")


def assign_service_account_client_roles(
    base_url: str,
    token: str,
    realm: str,
    service_client_uuid: str,
    role_client_id: str,
    roles: Iterable[str],
) -> None:
    """Assign exact client roles to the backend service account.

    Args:
        base_url: Keycloak base URL.
        token: Bootstrap administrator token.
        realm: Realm name.
        service_client_uuid: Confidential backend client UUID.
        role_client_id: Client that owns the administrative roles.
        roles: Exact client roles to assign.

    Returns:
        None: Successful return means Keycloak accepted the mappings.

    Raises:
        KeycloakBootstrapError: When the role-owning client is absent.
    """
    role_client_uuid = resolve_client_id(base_url, token, realm, role_client_id)
    if not role_client_uuid:
        raise KeycloakBootstrapError("Unable to resolve service-account role client")
    user_id = resolve_service_account_user_id(
        base_url, token, realm, service_client_uuid
    )
    assign_client_roles(
        base_url, token, realm, role_client_uuid, user_id, roles
    )
