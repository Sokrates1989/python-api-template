"""Reusable HTTP schemas for browser Web Push subscription ownership.

The module models only the browser-safe public VAPID key and the standard
PushSubscription JSON contract. Private signing keys, delivery payloads, and
scheduler policy deliberately remain outside request and response models.
"""

from __future__ import annotations

from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _WebPushEndpointRequest(BaseModel):
    """Validate an opaque browser endpoint before it can become delivery data.

    Attributes:
        endpoint (str): HTTPS push-service endpoint without credentials or a
            fragment.
    """

    endpoint: str = Field(min_length=1, max_length=4096)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        """Reject endpoint values that could become unsafe delivery targets.

        Args:
            value (str): Client-supplied browser push-service endpoint.

        Returns:
            str: The original, non-normalized HTTPS endpoint.

        Raises:
            ValueError: When the endpoint is not an absolute HTTPS URL, has
                surrounding whitespace, embeds credentials, or has a fragment.

        Side Effects:
            None.
        """
        if value != value.strip():
            raise ValueError("Web Push endpoint cannot contain outer whitespace.")
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("Web Push endpoint must be an absolute safe HTTPS URL.")
        return value


class WebPushSubscriptionKeys(BaseModel):
    """Describe the browser-generated encryption keys for one subscription.

    Attributes:
        p256dh (str): Browser public key used to encrypt push payloads.
        auth (str): Browser authentication secret used during encryption.
    """

    p256dh: str = Field(min_length=1, max_length=2048)
    auth: str = Field(min_length=1, max_length=2048)


class WebPushSubscriptionRequest(_WebPushEndpointRequest):
    """Represent the standard browser ``PushSubscription.toJSON`` payload.

    Attributes:
        endpoint (str): Opaque push-service endpoint owned by the browser.
        expiration_time (Optional[int]): Optional browser expiry timestamp in
            milliseconds, accepted from the ``expirationTime`` JSON field.
        keys (WebPushSubscriptionKeys): Encryption and authentication keys.
    """

    model_config = ConfigDict(populate_by_name=True)

    expiration_time: Optional[int] = Field(
        default=None,
        alias="expirationTime",
        ge=0,
    )
    keys: WebPushSubscriptionKeys


class WebPushSubscriptionDeleteRequest(_WebPushEndpointRequest):
    """Identify one authenticated account subscription for idempotent removal.

    Attributes:
        endpoint (str): Opaque browser endpoint to remove for the current user.
    """


class WebPushPublicKeyResponse(BaseModel):
    """Expose the browser-safe public VAPID key.

    Attributes:
        application_server_key (str): URL-safe uncompressed public P-256 key.
    """

    application_server_key: str


class WebPushRegistrationData(BaseModel):
    """Describe the result of an idempotent registration request.

    Attributes:
        endpoint (str): Opaque endpoint accepted by the backend.
        created (bool): Whether a new record was created instead of refreshed.
    """

    endpoint: str
    created: bool


class WebPushRegistrationResponse(BaseModel):
    """Wrap one successful authenticated registration mutation.

    Attributes:
        status (Literal["success"]): Stable successful operation status.
        data (WebPushRegistrationData): Idempotent registration result.
    """

    status: Literal["success"] = "success"
    data: WebPushRegistrationData


class WebPushDeletionData(BaseModel):
    """Describe the result of an idempotent subscription deletion.

    Attributes:
        endpoint (str): Opaque endpoint targeted by the deletion.
        deleted (bool): Whether an existing account-owned record was removed.
    """

    endpoint: str
    deleted: bool


class WebPushDeletionResponse(BaseModel):
    """Wrap one successful or already-absent deletion mutation.

    Attributes:
        status (Literal["success"]): Stable successful operation status.
        data (WebPushDeletionData): Idempotent deletion result.
    """

    status: Literal["success"] = "success"
    data: WebPushDeletionData
