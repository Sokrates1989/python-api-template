"""Build non-personal user profiles and credential-free bootstrap summaries."""

from __future__ import annotations

import argparse
import hashlib
from typing import Sequence, cast


def build_local_user_payload(username: str) -> dict[str, object]:
    """Build a complete non-personal Keycloak user profile.

    Args:
        username: Neutral local-development username.

    Returns:
        dict[str, object]: Enabled user representation with deterministic local
        placeholder name/email fields and no password or required actions.

    Side Effects:
        None.
    """
    readable = "".join(
        character.lower() if character.isalnum() else "-" for character in username
    ).strip("-")
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:10]
    email_local = f"{(readable or 'quality-user')[:32]}-{digest}"
    return {
        "username": username,
        "enabled": True,
        "email": f"{email_local}@local.invalid",
        "emailVerified": True,
        "firstName": "Local",
        "lastName": "Quality",
        "requiredActions": [],
    }


def build_sanitized_summary(
    args: argparse.Namespace,
    roles: Sequence[str],
    users: Sequence[dict[str, object]],
    backend_secret: str,
) -> dict[str, object]:
    """Build the credential-free bootstrap completion summary.

    Args:
        args: Parsed bootstrap identity and client arguments.
        roles: Realm roles requested by the operator.
        users: Parsed user specifications containing private passwords.
        backend_secret: Generated confidential-client secret.

    Returns:
        dict[str, object]: Public identifiers, roles, usernames, and a boolean
        indicating whether Keycloak returned a client secret. Passwords,
        tokens, and secret values are always absent.

    Side Effects:
        None.
    """
    sanitized_users = [
        {
            "username": str(user["username"]),
            "roles": [
                str(role) for role in cast(Sequence[object], user["roles"])
            ],
        }
        for user in users
    ]
    return {
        "realm": args.realm,
        "frontend_client_id": args.frontend_client_id,
        "backend_client_id": args.backend_client_id,
        "backend_client_secret_configured": bool(backend_secret),
        "roles": list(roles),
        "users": sanitized_users,
    }
