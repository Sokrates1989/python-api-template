"""SQL parent-user guards for Felix-owned persistence services.

Felix readiness and rewards rows reference the shared ``users`` table. During
new-account bootstrap, authenticated requests can arrive before the matching
application user row has been provisioned. This module converts that expected
race into a stable not-found service result before child-row inserts reach a
foreign-key constraint.
"""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text


class SQLUserNotProvisionedError(LookupError):
    """Signal that an authenticated identity lacks its SQL application user."""


async def ensure_sql_user_provisioned(session: Any, user_id: str) -> None:
    """Require the shared SQL user row before writing Felix-owned state.

    Args:
        session (Any): Active SQLAlchemy asynchronous session.
        user_id (str): Authenticated identity expected in ``users.id``.

    Returns:
        None: The function returns only when the parent user row exists.

    Raises:
        SQLUserNotProvisionedError: When the application user has not yet been
        provisioned or has already been deleted.

    Side Effects:
        Acquires a parent-user row lock for the current transaction. This also
        serializes concurrent first inserts into Felix child-state tables and
        prevents account deletion between the guard and its child write.
    """
    result = await session.execute(
        text("SELECT id FROM users WHERE id = :user_id FOR UPDATE"),
        {"user_id": user_id},
    )
    if result.scalar_one_or_none() is None:
        raise SQLUserNotProvisionedError("User not found")


def sql_user_not_found_result() -> Dict[str, Any]:
    """Return the stable service envelope for an unprovisioned SQL user.

    Args:
        None.

    Returns:
        Dict[str, Any]: Fresh error payload recognized as HTTP 404 by Felix
        route error mapping.

    Side Effects:
        None.
    """
    return {"status": "error", "message": "User not found", "data": None}
