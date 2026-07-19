"""Standard-library CI smoke tests for the records starter contract."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from template_v2.records_starter_contract import (
    CONTRACT_RELATIVE_PATH,
    TEMPLATE_ROOT_RELATIVE_PATH,
    RecordsStarterContractError,
    validate_records_starter_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RecordsStarterContractSmokeTest(unittest.TestCase):
    """Verify canonical rendering and checksum failure without app dependencies."""

    def _copy_contract(self, destination: Path) -> Path:
        """Copy only the records manifest and templates.

        Args:
            destination: Empty temporary repository root.

        Returns:
            Prepared isolated contract root.
        """

        source_manifest = REPOSITORY_ROOT.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
        target_manifest = destination.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
        target_manifest.parent.mkdir(parents=True)
        shutil.copyfile(source_manifest, target_manifest)
        source_templates = REPOSITORY_ROOT.joinpath(*TEMPLATE_ROOT_RELATIVE_PATH.split("/"))
        target_templates = destination.joinpath(*TEMPLATE_ROOT_RELATIVE_PATH.split("/"))
        shutil.copytree(source_templates, target_templates)
        return destination

    def test_canonical_contract_renders_and_compiles(self) -> None:
        """Render the complete standard starter and parse every Python file."""

        contract = validate_records_starter_contract(REPOSITORY_ROOT)
        outputs = contract.render("ci_records_app")

        self.assertEqual(contract.starter_revision, "1.0.0")
        self.assertEqual(len(outputs), 13)
        self.assertIn("routes/records.py", outputs)
        self.assertIn("migrations/versions/ci_records_app_001_records.py", outputs)
        for path, content in outputs.items():
            if path.endswith(".py"):
                compile(content, path, "exec")

    def test_checksum_drift_fails_closed(self) -> None:
        """Reject an edited route template before generated staging."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_contract(Path(directory))
            route = root.joinpath(
                *TEMPLATE_ROOT_RELATIVE_PATH.split("/"), "routes", "records.py.tmpl"
            )
            route.write_bytes(route.read_bytes() + b"\n# drift\n")

            with self.assertRaises(RecordsStarterContractError) as captured:
                validate_records_starter_contract(root)

        self.assertIn("checksum drifted", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
