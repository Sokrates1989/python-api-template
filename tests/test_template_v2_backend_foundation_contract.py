"""Tests for the versioned Template V2 backend-foundation contract validator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from template_v2.backend_foundation_contract import (
    BackendFoundationContractError,
    _portable_source_paths,
    _read_manifest,
    calculate_source_sha256,
    validate_backend_foundation,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class BackendFoundationContractTest(unittest.TestCase):
    """Verify the real contract identity and fail-closed drift behavior."""

    def test_real_repository_contract_is_valid_and_path_independent(self) -> None:
        """Validate the canonical repository without exposing its absolute path."""

        identity = validate_backend_foundation(REPOSITORY_ROOT)

        self.assertEqual(identity.contract_id, "template-v2-backend-foundation")
        self.assertEqual(identity.contract_version, 1)
        self.assertEqual(identity.foundation_revision, "1.0.0")
        self.assertEqual(identity.source_file_count, 14)
        self.assertRegex(identity.manifest_sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(identity.source_sha256, r"^[0-9a-f]{64}$")
        self.assertNotIn(str(REPOSITORY_ROOT), repr(identity))

    def test_declared_digest_rejects_source_drift(self) -> None:
        """Reject one changed declared source before it can be consumed."""

        document, _ = _read_manifest(REPOSITORY_ROOT)
        source_paths = _portable_source_paths(document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative_path in source_paths:
                source = REPOSITORY_ROOT.joinpath(*relative_path.split("/"))
                target = root.joinpath(*relative_path.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            contract_path = root / "template_v2" / "backend_foundation_contract.json"
            contract_path.parent.mkdir(parents=True)
            contract_path.write_text(json.dumps(document), encoding="utf-8")
            drifted = root.joinpath(*source_paths[0].split("/"))
            drifted.write_bytes(drifted.read_bytes() + b"\n# drift\n")

            with self.assertRaisesRegex(BackendFoundationContractError, "source drifted"):
                validate_backend_foundation(root)

    def test_digest_normalizes_checkout_line_endings(self) -> None:
        """Produce one digest for equivalent LF and CRLF text checkouts."""

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_root = Path(first)
            second_root = Path(second)
            for root, content in ((first_root, b"alpha\nbeta\n"), (second_root, b"alpha\r\nbeta\r\n")):
                (root / "source.txt").write_bytes(content)

            self.assertEqual(
                calculate_source_sha256(first_root, ("source.txt",)),
                calculate_source_sha256(second_root, ("source.txt",)),
            )


if __name__ == "__main__":
    unittest.main()
