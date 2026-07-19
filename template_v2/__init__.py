"""Template V2 backend foundation contracts and lifecycle tooling."""

from .backend_foundation_contract import (
    BackendFoundationContractError,
    BackendFoundationIdentity,
    validate_backend_foundation,
)
from .backend_lifecycle import execute_backend_lifecycle

__all__ = [
    "BackendFoundationContractError",
    "BackendFoundationIdentity",
    "validate_backend_foundation",
    "execute_backend_lifecycle",
]
