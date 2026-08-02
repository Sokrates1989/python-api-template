"""Contract tests for Felix API branding and selected-app metadata exports."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path
from runpy import run_path


# Standalone metadata fixture avoids importing optional API runtime packages.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = (
    REPOSITORY_ROOT / "app" / "apps" / "felix" / "config" / "app_metadata.py"
)
MAIN_PATH = REPOSITORY_ROOT / "app" / "main.py"
PYPROJECT_PATH = REPOSITORY_ROOT / "app" / "apps" / "felix" / "pyproject.toml"


def _load_metadata_exports() -> dict[str, object]:
    """Load Felix metadata without importing optional FastAPI dependencies.

    Returns:
        dict[str, object]: Globals exported by the standalone metadata module.

    Side Effects:
        Executes the static metadata module in an isolated namespace.
    """
    return run_path(str(METADATA_PATH))


class FelixAppIdentityTests(unittest.TestCase):
    """Prove Felix adopts the generic configurable OpenAPI identity contract."""

    def test_standard_metadata_export_owns_felix_openapi_branding(self) -> None:
        """Expose Felix branding through the generic selected-app config name."""
        exports = _load_metadata_exports()
        backend_config = exports["BACKEND_APP_CONFIG"]
        felix_config = exports["FELIX_APP_CONFIG"]

        self.assertIs(backend_config, felix_config)
        self.assertEqual(backend_config.display_name, "Felix API")
        self.assertEqual(
            backend_config.description,
            (
                "Production API for the Felix wellness app, including account, "
                "wellness, synchronization, notifications, and optional AI chat "
                "services."
            ),
        )

    def test_felix_identity_remains_app_selected_and_postgresql_backed(self) -> None:
        """Keep docs branding independent from fixed runtime app selection."""
        backend_config = _load_metadata_exports()["BACKEND_APP_CONFIG"]

        self.assertEqual(backend_config.app_id, "felix")
        self.assertEqual(backend_config.backend_data_profile, "postgresql")

    def test_fastapi_composition_uses_app_branding_and_runtime_image_tag(self) -> None:
        """Bind Swagger identity to app metadata and deployed image evidence."""
        main_source = MAIN_PATH.read_text(encoding="utf-8")

        self.assertIn(
            'getattr(config_module, "BACKEND_APP_CONFIG", None)',
            main_source,
        )
        self.assertIn("version=settings.IMAGE_TAG", main_source)

    def test_changed_felix_api_uses_the_coordinated_release_floor(self) -> None:
        """Publish diagnostics correction at the shared 1.0.8 stack floor."""
        with PYPROJECT_PATH.open("rb") as project_file:
            project = tomllib.load(project_file)

        self.assertEqual(project["project"]["version"], "1.0.8")


if __name__ == "__main__":
    unittest.main()
