"""Public exports for the Booking Service pair compatibility contract."""

from .contract import (
    CONTRACT_RELATIVE_PATH,
    SUPPORTED_CONTRACT_ID,
    SUPPORTED_CONTRACT_REVISION,
    SUPPORTED_CONTRACT_SEMANTIC_SHA256,
    SUPPORTED_CONTRACT_VERSION,
    BookingServiceContractError,
    BookingServiceContractIdentity,
    render_openapi_contract_extension,
    validate_booking_service_pair_contract,
)

__all__ = [
    "CONTRACT_RELATIVE_PATH",
    "SUPPORTED_CONTRACT_ID",
    "SUPPORTED_CONTRACT_REVISION",
    "SUPPORTED_CONTRACT_SEMANTIC_SHA256",
    "SUPPORTED_CONTRACT_VERSION",
    "BookingServiceContractError",
    "BookingServiceContractIdentity",
    "render_openapi_contract_extension",
    "validate_booking_service_pair_contract",
]
