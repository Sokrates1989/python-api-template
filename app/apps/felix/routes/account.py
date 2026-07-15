"""Authenticated self-service account deletion route for Felix.

The route accepts no caller-selected account identifier. Ownership comes only
from the verified bearer token, and partial backend/identity completion is
reported explicitly so clients never claim full erasure after a failed step.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.shared_dependencies.auth import get_user_id_from_token
from apps.felix.schemas.account import (
    FelixAccountDeletionData,
    FelixAccountDeletionResponse,
)
from apps.felix.services.account_deletion_service import (
    FelixAccountDeletionError,
    FelixAccountDeletionService,
)

router = APIRouter(tags=["account"], prefix="/v1/account")


def get_account_deletion_service() -> FelixAccountDeletionService:
    """Return the provider-aware Felix account deletion service.

    Returns:
        FelixAccountDeletionService: Service bound to active providers.

    Side Effects:
        Resolves the active database handler and runtime identity settings.
    """
    return FelixAccountDeletionService()


@router.delete("")
async def delete_current_account(
    current_user_id: str = Depends(get_user_id_from_token),
    service: FelixAccountDeletionService = Depends(get_account_deletion_service),
) -> FelixAccountDeletionResponse:
    """Permanently delete the authenticated Felix account.

    Args:
        current_user_id (str): Verified bearer-token subject supplied by the
            authentication dependency.
        service (FelixAccountDeletionService): Provider-aware deletion service.

    Returns:
        FelixAccountDeletionResponse: Completed backend and identity markers.

    Raises:
        HTTPException: ``409`` for unsupported/missing provider configuration,
            ``502`` when identity deletion remains pending after backend purge,
            or ``500`` when backend deletion fails.

    Side Effects:
        Permanently deletes active Felix data and the external identity.
    """
    try:
        result = await service.delete_account(current_user_id)
    except FelixAccountDeletionError as exc:
        if exc.backend_data_deleted:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": exc.code,
                    "message": "Backend data was deleted, but identity deletion must be retried.",
                    "backend_data_deleted": True,
                },
            ) from exc
        if exc.code in {
            "identity_provider_unsupported",
            "identity_provider_not_configured",
            "database_provider_unsupported",
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    return FelixAccountDeletionResponse(
        status="success",
        message="Felix account deletion completed.",
        data=FelixAccountDeletionData(
            backend_data_deleted=result.backend_data_deleted,
            identity_deleted=result.identity_deleted,
        ),
    )
