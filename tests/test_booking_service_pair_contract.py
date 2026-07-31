"""Tests for the Python-owned Booking Service pair compatibility contract."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

from booking_service_contract import (
    CONTRACT_RELATIVE_PATH,
    BookingServiceContractError,
    render_openapi_contract_extension,
    validate_booking_service_pair_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class BookingServicePairContractTest(unittest.TestCase):
    """Verify identity, safety, failure, and OpenAPI compatibility behavior."""

    def _copy_contract(self, destination: Path) -> Path:
        """Copy the canonical manifest into an isolated repository root.

        Args:
            destination: Empty temporary root receiving the contract.

        Returns:
            Prepared isolated repository root.
        """

        source = REPOSITORY_ROOT.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
        target = destination.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return destination

    def _mutate_contract(
        self,
        root: Path,
        mutation: Callable[[dict[str, Any]], None],
    ) -> None:
        """Apply one test mutation to an isolated contract document.

        Args:
            root: Isolated repository root containing the manifest.
            mutation: Callable that mutates the parsed JSON mapping.

        Returns:
            None.

        Side Effects:
            Rewrites the isolated test manifest.
        """

        path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
        document = json.loads(path.read_text(encoding="utf-8"))
        mutation(document)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def test_real_contract_freezes_the_accepted_identity(self) -> None:
        """Validate the exact booking identity accepted for BKG-002."""

        identity = validate_booking_service_pair_contract(REPOSITORY_ROOT)

        self.assertEqual(identity.contract_id, "booking-service-pair")
        self.assertEqual(identity.contract_version, 1)
        self.assertEqual(identity.contract_revision, "1.0.0")
        self.assertEqual(identity.app_id, "booking_service")
        self.assertEqual(
            identity.android_application_id,
            "com.felicitaswisdom.booking_service",
        )
        self.assertRegex(identity.manifest_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(
            identity.semantic_sha256,
            "b4ce3052502af7d2d7e9a82ecafc7c68ee76d66b0df1028d1f2028e207dc3250",
        )
        self.assertNotIn(str(REPOSITORY_ROOT), repr(identity))

    def test_packaged_contract_and_checkout_contract_match(self) -> None:
        """Keep runtime-adjacent and repository-root validation equivalent."""

        packaged = validate_booking_service_pair_contract()
        checkout = validate_booking_service_pair_contract(REPOSITORY_ROOT)

        self.assertEqual(packaged, checkout)

    def test_unsupported_version_fails_before_target_creation(self) -> None:
        """Reject an incompatible contract version during read-only preflight."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))
            self._mutate_contract(root, lambda document: document.update(contract_version=2))

            with self.assertRaisesRegex(BookingServiceContractError, "contract_version"):
                validate_booking_service_pair_contract(root)
            self.assertFalse((root / "app" / "apps" / "booking_service").exists())

    def test_forbidden_api_prefix_is_rejected(self) -> None:
        """Reject the absolute `/api` service-route anti-pattern."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))

            def mutate(document: dict[str, Any]) -> None:
                """Replace capability discovery with a forbidden route.

                Args:
                    document: Parsed isolated contract.

                Returns:
                    None.
                """

                document["http"]["capability_discovery"]["route"] = "/api/v1/capabilities"

            self._mutate_contract(root, mutate)

            with self.assertRaisesRegex(BookingServiceContractError, "forbidden /api"):
                validate_booking_service_pair_contract(root)

    def test_semantic_change_requires_revision_pin_update(self) -> None:
        """Reject harmless-looking drift until the supported pin is reviewed."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))

            def mutate(document: dict[str, Any]) -> None:
                """Change one public example without changing its schema.

                Args:
                    document: Parsed isolated contract.

                Returns:
                    None.
                """

                document["examples"]["error"]["message"] = "A revised safe message."

            self._mutate_contract(root, mutate)

            with self.assertRaisesRegex(BookingServiceContractError, "semantic document"):
                validate_booking_service_pair_contract(root)

    def test_credential_shaped_field_is_rejected(self) -> None:
        """Keep examples and public runtime configuration secret-free."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))

            def mutate(document: dict[str, Any]) -> None:
                """Inject a forbidden credential-shaped public field.

                Args:
                    document: Parsed isolated contract.

                Returns:
                    None.
                """

                document["runtime"]["authentication"]["client_secret"] = "forbidden"

            self._mutate_contract(root, mutate)

            with self.assertRaisesRegex(BookingServiceContractError, "credential-shaped"):
                validate_booking_service_pair_contract(root)

    def test_openapi_extension_contains_only_stable_public_identity(self) -> None:
        """Render the service implementation identity without endpoint data."""

        identity = validate_booking_service_pair_contract(REPOSITORY_ROOT)

        self.assertEqual(
            render_openapi_contract_extension(identity, "0.1.0"),
            {
                "contract_id": "booking-service-pair",
                "contract_version": 1,
                "contract_revision": "1.0.0",
                "implementation_version": "0.1.0",
            },
        )

    def test_openapi_extension_rejects_empty_implementation_version(self) -> None:
        """Require every backend build to declare an implementation version."""

        identity = validate_booking_service_pair_contract(REPOSITORY_ROOT)

        with self.assertRaisesRegex(ValueError, "implementation_version"):
            render_openapi_contract_extension(identity, "  ")


if __name__ == "__main__":
    unittest.main()
