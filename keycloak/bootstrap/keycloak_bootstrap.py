"""
Module: keycloak_bootstrap.py
Author: Cascade
Date: 2025-01-01
Version: 1.0.0

Description:
    Bootstraps a Keycloak realm with default roles, clients, and test users.
    Designed for local development of the python-api-template project.

Dependencies:
    - requests

Usage:
    python keycloak_bootstrap.py --base-url http://localhost:9090 --realm python-api-template
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable, Sequence

import requests

from bootstrap_errors import KeycloakBootstrapError
from bootstrap_safety import build_local_user_payload, build_sanitized_summary
from keycloak_admin_operations import (
    assign_client_roles,
    assign_realm_roles,
    assign_service_account_client_roles,
    assign_service_account_role,
    request_with_token,
    resolve_client_id,
)


def _split_env_list(value: str) -> list[str]:
    """Split a semicolon-delimited environment variable value.

    Args:
        value: Raw environment variable value.

    Returns:
        list[str]: Trimmed list entries.
    """
    return [item.strip() for item in value.split(";") if item.strip()]


def parse_user_specs(raw_specs: Sequence[str]) -> list[dict[str, object]]:
    """Parse user specifications from CLI or environment.

    Args:
        raw_specs: Iterable of strings in the format "username:password:role1,role2".

    Returns:
        list[dict[str, object]]: Parsed user specifications.

    Raises:
        KeycloakBootstrapError: When a specification is invalid.
    """
    users: list[dict[str, object]] = []
    for index, spec in enumerate(raw_specs, start=1):
        parts = spec.split(":")
        if len(parts) < 3:
            raise KeycloakBootstrapError(
                f"Invalid user specification #{index}. "
                "Use username:password:role1,role2."
            )
        username, password = parts[0], parts[1]
        roles_raw = ":".join(parts[2:])
        roles = [role.strip() for role in roles_raw.split(",") if role.strip()]
        if not username or not password or not roles:
            raise KeycloakBootstrapError(
                f"Invalid user specification #{index}. "
                "Username, password, and roles are required."
            )
        users.append({"username": username, "password": password, "roles": roles})
    return users


def get_admin_token(base_url: str, username: str, password: str) -> str:
    """Request an admin access token from Keycloak.

    Args:
        base_url: Keycloak base URL.
        username: Admin username.
        password: Admin password.

    Returns:
        str: Access token.

    Raises:
        KeycloakBootstrapError: When the token request fails.
    """
    token_endpoint = f"{base_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
    response = requests.post(
        token_endpoint,
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": username,
            "password": password,
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise KeycloakBootstrapError(
            f"Failed to obtain admin token: {response.status_code} {response.text}"
        )
    token = response.json().get("access_token")
    if not token:
        raise KeycloakBootstrapError("Keycloak admin token response missing access_token")
    return token


def ensure_realm(base_url: str, token: str, realm: str) -> None:
    """Ensure a realm exists, creating it if needed.

    Args:
        base_url: Keycloak base URL.
        token: Admin access token.
        realm: Realm name.

    Raises:
        KeycloakBootstrapError: When realm creation fails unexpectedly.
    """
    response = request_with_token("GET", base_url, token, f"/admin/realms/{realm}")
    if response.status_code == 200:
        return
    if response.status_code not in (404, 400):
        raise KeycloakBootstrapError(
            f"Failed to check realm '{realm}': {response.status_code} {response.text}"
        )

    payload = {
        "realm": realm,
        "displayName": realm.replace("-", " ").title(),
        "enabled": True,
        "loginWithEmailAllowed": True,
        "resetPasswordAllowed": True,
        "registrationAllowed": False,
    }
    create_response = request_with_token("POST", base_url, token, "/admin/realms", payload)
    if create_response.status_code not in (201, 204):
        raise KeycloakBootstrapError(
            f"Failed to create realm '{realm}': {create_response.status_code} {create_response.text}"
        )


def ensure_roles(base_url: str, token: str, realm: str, roles: Iterable[str]) -> None:
    """Ensure realm roles exist.

    Args:
        base_url: Keycloak base URL.
        token: Admin access token.
        realm: Realm name.
        roles: Role names to ensure.

    Raises:
        KeycloakBootstrapError: When role creation fails unexpectedly.
    """
    for role in roles:
        response = request_with_token(
            "GET",
            base_url,
            token,
            f"/admin/realms/{realm}/roles/{role}",
        )
        if response.status_code == 200:
            continue
        payload = {"name": role, "description": f"Role {role}"}
        create_response = request_with_token(
            "POST",
            base_url,
            token,
            f"/admin/realms/{realm}/roles",
            payload,
        )
        if create_response.status_code not in (201, 204):
            raise KeycloakBootstrapError(
                f"Failed to create role '{role}': {create_response.status_code} {create_response.text}"
            )


def ensure_client_roles(
    base_url: str,
    token: str,
    realm: str,
    client_uuid: str,
    roles: Iterable[str],
) -> None:
    """Ensure roles exist under one Keycloak client.

    Args:
        base_url: Keycloak base URL.
        token: Admin access token.
        realm: Realm name.
        client_uuid: Internal UUID of the role-owning client.
        roles: Client-role names to create when absent.

    Raises:
        KeycloakBootstrapError: When lookup or creation fails unexpectedly.
    """
    for role in roles:
        role_path = f"/admin/realms/{realm}/clients/{client_uuid}/roles/{role}"
        response = request_with_token("GET", base_url, token, role_path)
        if response.status_code == 200:
            continue
        create_response = request_with_token(
            "POST",
            base_url,
            token,
            f"/admin/realms/{realm}/clients/{client_uuid}/roles",
            {"name": role, "description": f"Booking client role {role}"},
        )
        if create_response.status_code not in (201, 204):
            raise KeycloakBootstrapError(
                f"Failed to create client role '{role}': "
                f"{create_response.status_code} {create_response.text}"
            )


def ensure_client(base_url: str, token: str, realm: str, client_payload: dict) -> str:
    """Ensure a client exists and return its UUID.

    Args:
        base_url: Keycloak base URL.
        token: Admin access token.
        realm: Realm name.
        client_payload: Client configuration payload.

    Returns:
        str: Client UUID.

    Raises:
        KeycloakBootstrapError: When client creation fails.
    """
    client_id = client_payload.get("clientId")
    client_uuid = resolve_client_id(base_url, token, realm, client_id)
    if client_uuid:
        return client_uuid

    response = request_with_token(
        "POST",
        base_url,
        token,
        f"/admin/realms/{realm}/clients",
        client_payload,
    )
    if response.status_code not in (201, 204):
        raise KeycloakBootstrapError(
            f"Failed to create client '{client_id}': {response.status_code} {response.text}"
        )

    client_uuid = resolve_client_id(base_url, token, realm, client_id)
    if not client_uuid:
        raise KeycloakBootstrapError(f"Unable to resolve client '{client_id}' after creation")
    return client_uuid


def get_client_secret(base_url: str, token: str, realm: str, client_uuid: str) -> str:
    """Fetch a client secret.

    Args:
        base_url: Keycloak base URL.
        token: Admin access token.
        realm: Realm name.
        client_uuid: Client UUID.

    Returns:
        str: Client secret.

    Raises:
        KeycloakBootstrapError: When the secret cannot be retrieved.
    """
    response = request_with_token(
        "GET",
        base_url,
        token,
        f"/admin/realms/{realm}/clients/{client_uuid}/client-secret",
    )
    if response.status_code != 200:
        raise KeycloakBootstrapError(
            f"Failed to fetch client secret: {response.status_code} {response.text}"
        )
    secret = response.json().get("value")
    if not secret:
        raise KeycloakBootstrapError("Client secret response missing value")
    return secret


def ensure_user(base_url: str, token: str, realm: str, username: str) -> str:
    """Ensure a user exists and return its UUID.

    Args:
        base_url: Keycloak base URL.
        token: Admin access token.
        realm: Realm name.
        username: Username.

    Returns:
        str: User UUID.
    """
    response = request_with_token(
        "GET",
        base_url,
        token,
        f"/admin/realms/{realm}/users",
        params={"username": username},
    )
    if response.status_code == 200 and response.json():
        return response.json()[0].get("id")

    payload = build_local_user_payload(username)
    create_response = request_with_token(
        "POST",
        base_url,
        token,
        f"/admin/realms/{realm}/users",
        payload,
    )
    if create_response.status_code not in (201, 204):
        raise KeycloakBootstrapError(
            f"Failed to create user '{username}': {create_response.status_code} {create_response.text}"
        )

    lookup = request_with_token(
        "GET",
        base_url,
        token,
        f"/admin/realms/{realm}/users",
        params={"username": username},
    )
    if lookup.status_code == 200 and lookup.json():
        return lookup.json()[0].get("id")
    raise KeycloakBootstrapError(f"Unable to resolve user '{username}' after creation")


def set_user_password(base_url: str, token: str, realm: str, user_id: str, password: str) -> None:
    """Set a user's password.

    Args:
        base_url: Keycloak base URL.
        token: Admin access token.
        realm: Realm name.
        user_id: User UUID.
        password: Plaintext password.

    Raises:
        KeycloakBootstrapError: When password update fails.
    """
    payload = {"type": "password", "value": password, "temporary": False}
    response = request_with_token(
        "PUT",
        base_url,
        token,
        f"/admin/realms/{realm}/users/{user_id}/reset-password",
        payload,
    )
    if response.status_code not in (204,):
        raise KeycloakBootstrapError(
            f"Failed to set password for user: {response.status_code} {response.text}"
        )


def write_disposable_client_secret(secret: str, destination: str) -> None:
    """Write a generated secret to an explicitly selected local proof volume.

    This helper exists for disposable Compose qualification only. Production
    deployments must inject the confidential client secret from their secret
    manager instead of using the bootstrap container as a secret distributor.

    Args:
        secret: Generated backend client secret, never printed by this helper.
        destination: Explicit container-local file in an ephemeral shared volume.

    Returns:
        None: The complete secret is written once with read-only permissions.

    Raises:
        KeycloakBootstrapError: When the destination is empty.

    Side Effects:
        Creates the parent directory and secret file inside the selected volume.
    """
    normalized = destination.strip()
    if not normalized:
        raise KeycloakBootstrapError("Backend client secret destination is empty")
    path = Path(normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o444)


def build_client_payloads(
    frontend_client_id: str,
    backend_client_id: str,
    frontend_root_url: str,
    api_root_url: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Build frontend and backend client payloads.

    Args:
        frontend_client_id: Public client ID.
        backend_client_id: Confidential client ID.
        frontend_root_url: Base URL for frontend.
        api_root_url: Base URL for API.

    Returns:
        tuple[dict[str, object], dict[str, object]]: Frontend and backend payloads.
    """
    frontend_payload = {
        "clientId": frontend_client_id,
        "name": frontend_client_id,
        "protocol": "openid-connect",
        "publicClient": True,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": True,
        "implicitFlowEnabled": False,
        "serviceAccountsEnabled": False,
        "rootUrl": frontend_root_url,
        "baseUrl": "/",
        "redirectUris": [f"{frontend_root_url.rstrip('/')}/*"],
        "webOrigins": [frontend_root_url, api_root_url, "+"],
        "attributes": {"pkce.code.challenge.method": "S256"},
        "protocolMappers": [
            {
                "name": f"{frontend_client_id}-access-token-audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": False,
                "config": {
                    "included.client.audience": frontend_client_id,
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "introspection.token.claim": "true",
                },
            }
        ],
    }

    backend_payload = {
        "clientId": backend_client_id,
        "name": backend_client_id,
        "protocol": "openid-connect",
        "publicClient": False,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "implicitFlowEnabled": False,
        "serviceAccountsEnabled": True,
        "bearerOnly": False,
        "rootUrl": api_root_url,
        "baseUrl": "/",
    }

    return frontend_payload, backend_payload


def run_bootstrap(args: argparse.Namespace) -> None:
    """Execute the bootstrap flow.

    Args:
        args: Parsed CLI arguments.

    Raises:
        KeycloakBootstrapError: On failure.
    """
    roles = args.role if args.role else []
    client_roles = getattr(args, "client_role", None) or []
    users = parse_user_specs(args.user)

    token = get_admin_token(args.base_url, args.admin_user, args.admin_password)
    ensure_realm(args.base_url, token, args.realm)

    if roles:
        print("\nEnsuring roles exist...")
        ensure_roles(args.base_url, token, args.realm, roles)

    frontend_uuid, backend_uuid, backend_secret = _ensure_bootstrap_clients(
        args, token
    )

    if client_roles:
        print("\nEnsuring frontend client roles exist...")
        ensure_client_roles(
            args.base_url,
            token,
            args.realm,
            frontend_uuid,
            client_roles,
        )

    _provision_users(args, token, users, frontend_uuid, client_roles)
    _configure_service_account(args, token, backend_uuid)

    summary = build_sanitized_summary(args, roles, users, backend_secret)
    print("\nBootstrap completed. Summary:")
    print(json.dumps(summary, indent=2))


def _ensure_bootstrap_clients(
    args: argparse.Namespace,
    token: str,
) -> tuple[str, str, str]:
    """Ensure frontend/backend clients and optionally share the proof secret.

    Args:
        args: Parsed client identity and endpoint arguments.
        token: Bootstrap administrator access token.

    Returns:
        tuple[str, str, str]: Frontend UUID, backend UUID, and backend secret.
    """
    frontend_payload, backend_payload = build_client_payloads(
        args.frontend_client_id,
        args.backend_client_id,
        args.frontend_root_url,
        args.api_root_url,
    )
    frontend_uuid = ensure_client(args.base_url, token, args.realm, frontend_payload)
    backend_uuid = ensure_client(args.base_url, token, args.realm, backend_payload)
    backend_secret = get_client_secret(args.base_url, token, args.realm, backend_uuid)
    destination = getattr(args, "backend_client_secret_file", "")
    if destination:
        write_disposable_client_secret(backend_secret, destination)
    return frontend_uuid, backend_uuid, backend_secret


def _provision_users(
    args: argparse.Namespace,
    token: str,
    users: list[dict[str, object]],
    frontend_uuid: str,
    client_roles: list[str],
) -> None:
    """Create fixture users and assign configured realm/client roles.

    Args:
        args: Parsed realm and provider endpoint arguments.
        token: Bootstrap administrator access token.
        users: Parsed local fixture user specifications.
        frontend_uuid: Public client UUID that owns Booking roles.
        client_roles: Roles configured on the public client.

    Returns:
        None: Successful return means all fixtures were provisioned.
    """
    print("\nCreating/updating users...")
    for user in users:
        username = str(user["username"])
        print(f"  Processing user '{username}'...")
        user_id = ensure_user(args.base_url, token, args.realm, username)
        set_user_password(args.base_url, token, args.realm, user_id, str(user["password"]))
        assign_realm_roles(args.base_url, token, args.realm, user_id, user["roles"], username)
        if client_roles:
            assign_client_roles(
                args.base_url, token, args.realm, frontend_uuid, user_id, user["roles"]
            )


def _configure_service_account(
    args: argparse.Namespace,
    token: str,
    backend_uuid: str,
) -> None:
    """Assign the requested realm and narrow client roles to the service account.

    Args:
        args: Parsed service-account role configuration.
        token: Bootstrap administrator access token.
        backend_uuid: Confidential backend client UUID.

    Returns:
        None: Successful return means configured mappings were accepted.
    """
    if args.assign_service_account_role:
        assign_service_account_role(
            args.base_url,
            token,
            args.realm,
            backend_uuid,
            args.assign_service_account_role,
        )
    client_roles = getattr(args, "service_account_client_role", None) or []
    if client_roles:
        assign_service_account_client_roles(
            args.base_url,
            token,
            args.realm,
            backend_uuid,
            getattr(args, "service_account_role_client_id", ""),
            client_roles,
        )


def _env_default(name: str, fallback: str) -> str:
    """Return an environment variable value or fallback.

    Args:
        name: Environment variable name.
        fallback: Fallback value.

    Returns:
        str: Resolved value.
    """
    return os.getenv(name) or fallback


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(
        description="Bootstrap a Keycloak realm with clients, roles, and users.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_connection_arguments(parser)
    _add_role_and_user_arguments(parser)
    _add_service_account_arguments(parser)
    return parser


def _add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Add Keycloak, realm, and client endpoint arguments.

    Args:
        parser: Parser receiving connection and client options.

    Returns:
        None: Arguments are registered on the supplied parser.
    """
    parser.add_argument("--base-url", default=_env_default("KEYCLOAK_URL", "http://localhost:9090"))
    parser.add_argument("--admin-user", default=_env_default("KEYCLOAK_ADMIN", "admin"))
    parser.add_argument("--admin-password", default=_env_default("KEYCLOAK_ADMIN_PASSWORD", "admin"))
    parser.add_argument("--realm", default=_env_default("KEYCLOAK_REALM", "python-api-template"))
    parser.add_argument(
        "--frontend-client-id",
        default=_env_default("KEYCLOAK_FRONTEND_CLIENT_ID", "python-api-template-frontend"),
    )
    parser.add_argument(
        "--backend-client-id",
        default=_env_default("KEYCLOAK_BACKEND_CLIENT_ID", "python-api-template-backend"),
    )
    parser.add_argument(
        "--frontend-root-url",
        default=_env_default("KEYCLOAK_FRONTEND_ROOT_URL", "http://localhost:3000"),
    )
    parser.add_argument(
        "--api-root-url",
        default=_env_default("KEYCLOAK_API_ROOT_URL", "http://localhost:8000"),
    )


def _add_role_and_user_arguments(parser: argparse.ArgumentParser) -> None:
    """Add realm/client role and local fixture-user arguments.

    Args:
        parser: Parser receiving role and user options.

    Returns:
        None: Arguments are registered on the supplied parser.
    """
    roles_env = os.getenv("KEYCLOAK_ROLES")
    default_roles = ["python-api-template-user", "python-api-template-admin"]
    roles_default = _split_env_list(roles_env) if roles_env else default_roles
    parser.add_argument("--role", action="append", default=roles_default, help="Realm role to create")

    client_roles_env = os.getenv("KEYCLOAK_FRONTEND_CLIENT_ROLES")
    client_roles_default = _split_env_list(client_roles_env) if client_roles_env else []
    parser.add_argument(
        "--client-role",
        action="append",
        default=client_roles_default,
        help="Frontend client role to create and assign from matching user role specs",
    )

    users_env = os.getenv("KEYCLOAK_USERS")
    default_users = ["demo:Demo123!:python-api-template-user"]
    users_default = _split_env_list(users_env) if users_env else default_users
    parser.add_argument(
        "--user",
        action="append",
        default=users_default,
        help="User spec username:password:role1,role2 (repeatable)",
    )


def _add_service_account_arguments(parser: argparse.ArgumentParser) -> None:
    """Add confidential client secret and service-account role arguments.

    Args:
        parser: Parser receiving service-account options.

    Returns:
        None: Arguments are registered on the supplied parser.
    """
    parser.add_argument(
        "--assign-service-account-role",
        default=_env_default("KEYCLOAK_SERVICE_ACCOUNT_ROLE", "python-api-template-admin"),
    )
    parser.add_argument(
        "--backend-client-secret-file",
        default=_env_default("KEYCLOAK_BACKEND_CLIENT_SECRET_FILE", ""),
        help="Disposable proof-volume destination for the generated client secret",
    )
    parser.add_argument(
        "--service-account-role-client-id",
        default=_env_default("KEYCLOAK_SERVICE_ACCOUNT_ROLE_CLIENT_ID", ""),
        help="Client owning exact roles assigned to the backend service account",
    )
    service_client_roles_env = os.getenv("KEYCLOAK_SERVICE_ACCOUNT_CLIENT_ROLES")
    service_client_roles = (
        _split_env_list(service_client_roles_env)
        if service_client_roles_env
        else []
    )
    parser.add_argument(
        "--service-account-client-role",
        action="append",
        default=service_client_roles,
        help="Exact client role assigned to the backend service account",
    )


def main() -> None:
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()
    if not args.user:
        raise KeycloakBootstrapError("At least one --user specification is required.")
    run_bootstrap(args)


if __name__ == "__main__":
    main()
