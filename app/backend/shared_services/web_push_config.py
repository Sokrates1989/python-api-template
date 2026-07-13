"""Reusable validation for browser-safe Web Push VAPID public keys."""

from __future__ import annotations

import base64
import binascii


def validate_vapid_public_key(raw_key: str) -> str:
    """Validate and normalize an uncompressed public P-256 VAPID key.

    Args:
        raw_key (str): URL-safe or standard Base64 key text.

    Returns:
        str: Trimmed original key text accepted by browser PushManager.

    Raises:
        ValueError: When the key is empty, malformed, or not a 65-byte
            uncompressed P-256 public point.

    Side Effects:
        None.
    """
    key = str(raw_key or "").strip()
    if not key:
        raise ValueError("Web Push public VAPID key is not configured.")
    normalized = key.replace("-", "+").replace("_", "/")
    normalized += "=" * ((4 - len(normalized) % 4) % 4)
    try:
        decoded = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Web Push public VAPID key is malformed.") from exc
    if len(decoded) != 65 or decoded[0] != 4:
        raise ValueError(
            "Web Push public VAPID key must be an uncompressed P-256 point."
        )
    return key
