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

    def test_local_compose_binds_both_build_selectors_to_active_app(self) -> None:
        source = (
            REPOSITORY_ROOT / "local-deployment" / "base" / "api.compose.yml"
        ).read_text(encoding="utf-8")

        selected_app_argument = "${ACTIVE_BACKEND_APP_ID:-demo_app}"
        self.assertIn(f"BACKEND_APP_ID: {selected_app_argument}", source)
        self.assertIn(f"APP_PROFILE: {selected_app_argument}", source)

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
            "aiohttp": (3, 14, 3),
            "cryptography": (50, 0, 0),
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
            "Production Release API Image (guided; version + latest)",
            source,
        )
        self.assertIn(
            "Production-Connected Test API Image (guided; version-test + latest-test)",
            source,
        )
        self.assertIn('local MENU_BUILD_PROD_IMAGE="p"', source)
        self.assertIn('local MENU_BUILD_TEST_IMAGE="t"', source)
        self.assertIn(
            "${MENU_BUILD_PROD_IMAGE}|P|${MENU_BUILD_PROD_IMAGE_LEGACY})",
            source,
        )
        self.assertIn(
            'run_api_release_stack_minimum "$app_id" "$current_version"',
            source,
        )
        self.assertIn('"$minimum_version" true', source)
        self.assertIn("run_api_release_tool plan --app", source)
        self.assertIn("run_api_release_tool build --app", source)
        self.assertIn('--channel "$channel"', source)
        self.assertIn("publish_arguments+=(--allow-current-version)", source)
        self.assertIn(
            'publish_prompt="Build and publish ${tag_version} and latest? (Y/n): "',
            source,
        )
        self.assertIn('read -r -p "$publish_prompt" confirmation', source)
        self.assertIn('if [[ "$confirmation" =~ ^[Nn]$ ]]', source)
        self.assertIn("never pushes Git", source)
        self.assertNotIn("API publication channel choice", source)

        powershell_source = (
            REPOSITORY_ROOT / "setup" / "modules" / "menu_handlers.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn('$MENU_BUILD_PROD_IMAGE = "p"', powershell_source)
        self.assertIn(
            "$choice -eq \"$MENU_BUILD_PROD_IMAGE_LEGACY\"",
            powershell_source,
        )

    def test_action_summary_uses_status_matched_icons(self) -> None:
        """Prevent failed quick-start actions from displaying a success icon.

        Returns:
            None.
        """
        source = (
            REPOSITORY_ROOT / "setup" / "modules" / "menu_handlers.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('prefix="✅"', source)
        self.assertIn('prefix="❌"', source)
        self.assertIn(
            'print_action_summary "$summary_msg" "$exit_code"',
            source,
        )

    def test_felix_declares_a_non_default_production_startup_smoke(self) -> None:
        """Require Felix image proof to exercise relational Keycloak identity.

        Returns:
            None.
        """

        smoke_path = (
            REPOSITORY_ROOT
            / "app"
            / "apps"
            / "felix"
            / "deployment"
            / "release-startup-smoke.env"
        )
        source = smoke_path.read_text(encoding="utf-8")

        self.assertIn("APP_ENVIRONMENT=production", source)
        self.assertIn("KEYCLOAK_REALM=release-smoke-realm", source)
        self.assertIn("KEYCLOAK_CLIENT_ID=release-smoke-frontend", source)
        self.assertIn("KEYCLOAK_AUDIENCE=release-smoke-api", source)
        self.assertNotIn("felix-new-frontend", source)
        self.assertNotIn("keycloak.fe-wi.com", source)
        self.assertNotIn("KEYCLOAK_CLIENT_SECRET=", source)

    def test_build_only_handler_contains_no_push_or_latest_command(self) -> None:
        source = (
            REPOSITORY_ROOT / "setup" / "modules" / "menu_handlers.sh"
        ).read_text(encoding="utf-8")
        start = source.index("handle_build_production_image_local()")
        end = source.index(
            "# Prove current source",
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
            "tools/release_api_publication.py",
            "tools/release_command.py",
            "tools/release_image_evidence.py",
            "tools/release_image_startup_smoke.py",
            "tools/release_registry_publication.py",
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
