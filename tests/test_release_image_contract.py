"""Static release-image contract tests that require no Docker daemon."""

from __future__ import annotations

import unittest
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ReleaseImageContractTests(unittest.TestCase):
    """Keep the Docker, menu, and quality-only CI boundaries explicit."""

    def test_dockerfile_binds_selected_build_and_runtime_identity(self) -> None:
        source = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ARG BACKEND_APP_ID=demo_app", source)
        self.assertIn("ARG APP_PROFILE=demo_app", source)
        self.assertIn("ENV BACKEND_APP_ID=$BACKEND_APP_ID", source)
        self.assertIn("ENV APP_PROFILE=$APP_PROFILE", source)
        self.assertIn('test "${BACKEND_APP_ID}" = "${APP_PROFILE}"', source)
        self.assertIn('com.fe-wi.backend-app-id="${BACKEND_APP_ID}"', source)
        self.assertIn('com.fe-wi.app-profile="${APP_PROFILE}"', source)

    def test_dockerfile_pins_pdm_and_declares_non_root_health_contract(self) -> None:
        source = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ARG PDM_VERSION=2.27.0", source)
        self.assertIn('"pdm==${PDM_VERSION}"', source)
        self.assertIn("USER 10001:10001", source)
        self.assertIn("HEALTHCHECK", source)
        self.assertIn("/app/.venv/bin/uvicorn", source)
        self.assertNotIn("exec pdm run uvicorn", source)
        self.assertIn("org.opencontainers.image.revision", source)
        self.assertIn("com.fe-wi.dependency-lock-sha256", source)
        self.assertNotIn("chown -R api:api /app", source)

    def test_felix_lock_meets_vulnerability_security_floors(self) -> None:
        """Keep scanner-remediated dependency versions from regressing.

        Returns:
            None.
        """
        lock_path = REPOSITORY_ROOT / "app" / "apps" / "felix" / "pdm.lock"
        lock_document = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        locked_versions = {
            str(package["name"]): tuple(
                int(part) for part in str(package["version"]).split(".")
            )
            for package in lock_document["package"]
        }
        security_floors = {
            "cryptography": (48, 0, 1),
            "pyasn1": (0, 6, 4),
            "python-multipart": (0, 0, 30),
            "starlette": (1, 3, 1),
        }

        for package_name, floor in security_floors.items():
            self.assertGreaterEqual(locked_versions[package_name], floor)

    def test_selected_app_menu_separates_plan_build_and_publish(self) -> None:
        source = (
            REPOSITORY_ROOT / "setup" / "modules" / "menu_handlers.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("Validate API Docker image release plan", source)
        self.assertIn("Build API Docker image locally (no push)", source)
        self.assertIn(
            "Build & Push API Docker Image (current or bump + immutable + latest)",
            source,
        )
        self.assertIn(
            "Keep current (${current_version}; registry tag must be absent)",
            source,
        )
        self.assertIn("run_api_release_tool plan --app", source)
        self.assertIn("run_api_release_tool build --app", source)
        self.assertIn('publish_arguments=(publish --app "$app_id"', source)
        self.assertIn("publish_arguments+=(--allow-current-version)", source)
        self.assertIn("Push proven source and publish both image tags?", source)
        self.assertIn("This action never deploys", source)

    def test_build_only_handler_contains_no_push_or_latest_command(self) -> None:
        source = (
            REPOSITORY_ROOT / "setup" / "modules" / "menu_handlers.sh"
        ).read_text(encoding="utf-8")
        start = source.index("handle_build_production_image_local()")
        end = source.index(
            "# Prove/push current source",
            start,
        )
        handler = source[start:end]

        self.assertIn("run_api_release_tool build", handler)
        self.assertNotIn("docker push", handler)
        self.assertNotIn("docker tag", handler)
        self.assertNotIn(":latest", handler)

    def test_push_to_main_ci_remains_quality_only(self) -> None:
        source = (
            REPOSITORY_ROOT / ".github" / "workflows" / "main.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("build-and-push:", source)
        self.assertIn("if: false", source)
        self.assertIn(
            "Image build and push are intentionally disabled in GitHub Actions.",
            source,
        )

    def test_release_tool_modules_stay_below_repository_file_limit(self) -> None:
        """Keep cohesive release modules below the hard physical-line limit."""

        for relative_path in (
            "tools/release_api_image.py",
            "tools/release_command.py",
            "tools/release_image_evidence.py",
            "tools/release_source_publication.py",
        ):
            with self.subTest(relative_path=relative_path):
                line_count = len(
                    (REPOSITORY_ROOT / relative_path).read_text(
                        encoding="utf-8"
                    ).splitlines()
                )
                self.assertLessEqual(line_count, 950)


if __name__ == "__main__":
    unittest.main()
