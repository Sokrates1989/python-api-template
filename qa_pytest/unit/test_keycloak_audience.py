"""Focused Keycloak resource-audience validation tests."""

from __future__ import annotations

from typing import Any

import pytest

from backend import auth_provider_utils


class _VerifyingKey:
    """Minimal JWK stand-in whose signature check succeeds."""

    def verify(self, _message: bytes, _signature: bytes) -> bool:
        """Accept the synthetic token signature."""
        return True


def _configure_verification_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace network and cryptography seams for claim-policy assertions."""
    monkeypatch.setattr(
        auth_provider_utils,
        "_get_keycloak_jwks",
        lambda: {"keys": [{"kid": "test-key"}]},
    )
    monkeypatch.setattr(
        auth_provider_utils.jwt,
        "get_unverified_header",
        lambda _token: {"kid": "test-key"},
    )
    monkeypatch.setattr(
        auth_provider_utils.jwk,
        "construct",
        lambda _key: _VerifyingKey(),
    )
    monkeypatch.setattr(
        auth_provider_utils,
        "base64url_decode",
        lambda _value: b"signature",
    )
    monkeypatch.setattr(
        auth_provider_utils.settings,
        "KEYCLOAK_ISSUER_URL",
        "https://keycloak.fe-wi.com/realms/felix-new",
    )
    monkeypatch.setattr(
        auth_provider_utils.settings,
        "KEYCLOAK_ENFORCE_AUDIENCE",
        True,
    )


def test_keycloak_verification_uses_dedicated_backend_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass KEYCLOAK_AUDIENCE rather than the frontend client to JWT decode."""
    _configure_verification_stubs(monkeypatch)
    monkeypatch.setattr(
        auth_provider_utils.settings,
        "KEYCLOAK_CLIENT_ID",
        "felix-new-frontend",
    )
    monkeypatch.setattr(
        auth_provider_utils.settings,
        "KEYCLOAK_AUDIENCE",
        "felix-new-backend",
    )
    captured: dict[str, Any] = {}

    def _decode(_token: str, _key: object, **kwargs: Any) -> dict[str, str]:
        captured.update(kwargs)
        return {"sub": "user-1"}

    monkeypatch.setattr(auth_provider_utils.jwt, "decode", _decode)

    claims = auth_provider_utils._verify_keycloak_token("header.payload.signature")

    assert claims == {"sub": "user-1"}
    assert captured["audience"] == "felix-new-backend"
    assert captured["options"] == {"verify_aud": True}


def test_keycloak_audience_enforcement_fails_without_resource_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed when audience enforcement lacks its dedicated value."""
    _configure_verification_stubs(monkeypatch)
    monkeypatch.setattr(auth_provider_utils.settings, "KEYCLOAK_AUDIENCE", None)

    with pytest.raises(RuntimeError, match="KEYCLOAK_AUDIENCE is missing"):
        auth_provider_utils._verify_keycloak_token("header.payload.signature")
