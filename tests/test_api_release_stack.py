"""Test generic API-to-deployment release-stack coordination."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.api_release_stack import (
    advance_api_release_minimum,
    evaluate_api_release_candidate,
    main,
    select_api_candidate,
)
from tools.release_stack_authority import (
    PROFILE_PATH_ENV,
    ReleaseStackAuthorityError,
    parse_stable_version,
)


class ApiReleaseStackTests(unittest.TestCase):
    """Verify configuration-driven coordination without app-specific logic."""

    def setUp(self) -> None:
        """Create one backend app and deployment authority fixture."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name) / "source"
        self.app_root = self.repository / "app" / "apps" / "sample_backend"
        self.app_root.mkdir(parents=True)
        (self.app_root / "pyproject.toml").write_text(
            "\n".join(
                (
                    "[tool.fe_wi.release_stack]",
                    'stack_id = "sample_stack"',
                    'authority_profile_id = "sample_deployment"',
                    'component_id = "api"',
                    "",
                    "[project]",
                    'name = "sample_backend"',
                    'version = "2.4.0"',
                    "",
                )
            ),
            encoding="utf-8",
        )
        self.authority_path = (
            Path(self.temporary_directory.name)
            / "deployment"
            / "site-configs"
            / "sample_deployment.json"
        )
        self.authority_path.parent.mkdir(parents=True)
        self.authority_path.write_text(
            json.dumps(
                {
                    "appId": "sample_backend",
                    "release": {
                        "stackId": "sample_stack",
                        "versionPolicy": "monotonic-floor",
                        "versionFloor": "2.4.0",
                        "componentVersionFloors": {
                            "api": "2.4.0",
                            "android": "2.5.0",
                            "ios": "2.5.0",
                            "web": "2.5.1",
                            "legacy-webapp": "3.0.0",
                        },
                        "componentVersionTracks": {
                            "application": ["api", "web", "android", "ios"],
                            "legacy": ["legacy-webapp"],
                        },
                        "components": [
                            "api",
                            "web",
                            "android",
                            "ios",
                            "legacy-webapp",
                        ],
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.environment = {PROFILE_PATH_ENV: str(self.authority_path)}

    def tearDown(self) -> None:
        """Delete the isolated source and deployment fixtures."""

        self.temporary_directory.cleanup()

    def test_shared_baseline_catches_up_lagging_api_component(self) -> None:
        """Use the Web high-water as API's next version without another bump."""

        decision = evaluate_api_release_candidate(
            self.repository,
            "sample_backend",
            "2.5.1",
            environment=self.environment,
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertTrue(decision.minimum_update_required)
        self.assertEqual(decision.binding.component_id, "api")
        self.assertEqual(decision.authority.minimum.text, "2.5.1")
        self.assertEqual(decision.authority.next_version.text, "2.5.1")

    def test_lower_candidate_is_rejected_with_precise_reason(self) -> None:
        """Explain the actual minimum violation instead of a stale manifest."""

        with self.assertRaisesRegex(
            ReleaseStackAuthorityError,
            "below the minimum version for the next release",
        ):
            evaluate_api_release_candidate(
                self.repository,
                "sample_backend",
                "2.5.0",
                environment=self.environment,
            )

    def test_lower_exact_image_override_never_changes_the_minimum(self) -> None:
        """Allow a deliberate lower image tag without creating a version track."""

        decision = evaluate_api_release_candidate(
            self.repository,
            "sample_backend",
            "2.5.0",
            allow_below_minimum=True,
            environment=self.environment,
        )
        assert decision is not None

        self.assertTrue(decision.minimum_override)
        self.assertFalse(decision.minimum_update_required)
        advance_api_release_minimum(decision)
        payload = json.loads(self.authority_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["release"]["versionFloor"], "2.4.0")
        self.assertEqual(
            payload["release"]["componentVersionFloors"]["api"],
            "2.4.0",
        )

    def test_higher_candidate_advances_only_authoritative_profile(self) -> None:
        """Advance the deployment minimum after a confirmed API release."""

        decision = evaluate_api_release_candidate(
            self.repository,
            "sample_backend",
            "2.5.2",
            environment=self.environment,
        )
        assert decision is not None
        self.assertTrue(decision.minimum_update_required)

        advance_api_release_minimum(decision)

        payload = json.loads(self.authority_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["release"]["versionFloor"], "2.4.0")
        self.assertEqual(
            payload["release"]["componentVersionFloors"],
            {
                "api": "2.5.2",
                "android": "2.5.0",
                "ios": "2.5.0",
                "web": "2.5.1",
                "legacy-webapp": "3.0.0",
            },
        )

    def test_selector_defaults_cover_both_mismatch_directions(self) -> None:
        """Default lower candidates upward and higher candidates to advance."""

        output: list[str] = []
        lower = select_api_candidate(
            parse_stable_version("2.3.0", field="candidate"),
            parse_stable_version("2.4.0", field="minimum"),
            reader=lambda _prompt: "",
            writer=output.append,
        )
        higher = select_api_candidate(
            parse_stable_version("2.5.0", field="candidate"),
            parse_stable_version("2.4.0", field="minimum"),
            reader=lambda _prompt: "",
            writer=output.append,
        )

        self.assertEqual(lower.text if lower else None, "2.4.0")
        self.assertEqual(higher.text if higher else None, "2.5.0")

    def test_minimum_only_reports_floor_when_package_candidate_is_older(self) -> None:
        """Let shell menus start at the floor without a reconciliation prompt."""

        output = StringIO()
        with redirect_stdout(output):
            result = main(
                (
                    "--repository-root",
                    str(self.repository),
                    "--app",
                    "sample_backend",
                    "--candidate",
                    "2.3.0",
                    "--minimum-only",
                ),
                environment=self.environment,
            )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), "2.5.1")

    def test_plan_reports_baseline_and_catch_up_version(self) -> None:
        """Expose both values needed by the Bash keep/patch menu."""

        output = StringIO()
        with redirect_stdout(output):
            result = main(
                (
                    "--repository-root",
                    str(self.repository),
                    "--app",
                    "sample_backend",
                    "--candidate",
                    "2.4.0",
                    "--plan-only",
                ),
                environment=self.environment,
            )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), "2.5.1 2.5.1")


if __name__ == "__main__":
    unittest.main()
