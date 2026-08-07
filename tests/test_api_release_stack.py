"""Test generic API-to-deployment release-stack coordination."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.api_release_stack import (
    advance_api_release_minimum,
    evaluate_api_release_candidate,
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
                        "components": ["api", "web", "android", "ios"],
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

    def test_equal_candidate_needs_no_authority_update(self) -> None:
        """Accept a candidate equal to the next-release minimum silently."""

        decision = evaluate_api_release_candidate(
            self.repository,
            "sample_backend",
            "2.4.0",
            environment=self.environment,
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertFalse(decision.minimum_update_required)
        self.assertEqual(decision.binding.component_id, "api")

    def test_lower_candidate_is_rejected_with_precise_reason(self) -> None:
        """Explain the actual minimum violation instead of a stale manifest."""

        with self.assertRaisesRegex(
            ReleaseStackAuthorityError,
            "below the minimum version for the next release",
        ):
            evaluate_api_release_candidate(
                self.repository,
                "sample_backend",
                "2.3.9",
                environment=self.environment,
            )

    def test_higher_candidate_advances_only_authoritative_profile(self) -> None:
        """Advance the deployment minimum after a confirmed API release."""

        decision = evaluate_api_release_candidate(
            self.repository,
            "sample_backend",
            "2.5.0",
            environment=self.environment,
        )
        assert decision is not None
        self.assertTrue(decision.minimum_update_required)

        advance_api_release_minimum(decision)

        payload = json.loads(self.authority_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["release"]["versionFloor"], "2.5.0")

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


if __name__ == "__main__":
    unittest.main()

