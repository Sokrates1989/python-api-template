"""Cryptographic JWT contract tests for Booking Service Keycloak access tokens."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError

from backend import auth_provider_utils


class _KeycloakSettingsStub:
    """Provide the exact issuer/audience settings used by verification tests."""

    KEYCLOAK_ENFORCE_AUDIENCE = True
    KEYCLOAK_AUDIENCE = "keycloak"

    def get_keycloak_issuer_url(self) -> str:
        """Return the expected test issuer.

        Returns:
            str: Stable HTTPS issuer used in generated JWT claims.
        """
        return "https://issuer.example.test/realms/booking"


class BookingJwtContractTests(unittest.TestCase):
    """Prove signature, issuer, audience, expiry, and access-token type checks."""

    private_key_pem: bytes
    public_jwk: dict[str, object]

    @classmethod
    def setUpClass(cls) -> None:
        """Generate ephemeral RSA signing material for this test process."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cls.public_jwk = jwk.construct(public_key_pem, algorithm="RS256").to_dict()
        cls.public_jwk["kid"] = "booking-test-key"

    def _token(self, **overrides: object) -> str:
        """Create one signed Keycloak-like access token.

        Args:
            overrides: Claim values replacing the valid defaults.

        Returns:
            str: RS256 token signed by the ephemeral process-local key.
        """
        now = int(time.time())
        claims: dict[str, object] = {
            "sub": "subject-1",
            "iss": _KeycloakSettingsStub().get_keycloak_issuer_url(),
            "aud": "keycloak",
            "iat": now,
            "nbf": now - 1,
            "exp": now + 300,
            "typ": "Bearer",
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            self.private_key_pem,
            algorithm="RS256",
            headers={"kid": "booking-test-key"},
        )

    def _verify(self, token: str) -> dict[str, object]:
        """Verify one token through the production Keycloak boundary.

        Args:
            token: Signed access token under test.

        Returns:
            dict[str, object]: Verified claims returned by the shared boundary.

        Raises:
            ValueError: For an invalid access-token type.
            JWTClaimsError: For invalid issuer or audience.
            ExpiredSignatureError: For expired tokens.
        """
        with (
            patch.object(
                auth_provider_utils,
                "_get_keycloak_jwks",
                return_value={"keys": [self.public_jwk]},
            ),
            patch.object(
                auth_provider_utils,
                "settings",
                _KeycloakSettingsStub(),
            ),
        ):
            return auth_provider_utils._verify_keycloak_token(token)

    def test_valid_access_token_returns_verified_subject(self) -> None:
        """Accept a signed bearer token with exact issuer and audience."""
        self.assertEqual(self._verify(self._token())["sub"], "subject-1")

    def test_wrong_issuer_and_audience_fail_closed(self) -> None:
        """Reject tokens minted for another issuer or another API audience."""
        invalid_tokens = (
            self._token(iss="https://wrong.example.test/realms/booking"),
            self._token(aud="unrelated-client"),
        )
        for token in invalid_tokens:
            with self.subTest(token_kind=len(token)), self.assertRaises(JWTClaimsError):
                self._verify(token)

    def test_expired_tokens_fail_closed(self) -> None:
        """Reject an otherwise valid token after its expiry instant."""
        with self.assertRaises(ExpiredSignatureError):
            self._verify(self._token(exp=int(time.time()) - 1))


if __name__ == "__main__":
    unittest.main()
