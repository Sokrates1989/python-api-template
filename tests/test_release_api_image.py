"""Focused tests for the selected-app API image release tool."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.release_api_image import (
    CommandRunner,
    ReleaseError,
    build_release_image,
    create_release_plan,
    publish_release_image,
)


REVISION = "a" * 40
PUSHED_REVISION = "b" * 40
IMAGE_ID = "sha256:" + ("c" * 64)
REGISTRY_DIGEST = "sha256:" + ("d" * 64)


class FakeRunner:
    """Record argument-vector effects and provide deterministic Docker/Git data."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.inspect_document: list[dict[str, object]] = []
        self.revision = REVISION
        self.worktree_status = ""
        self.manifest_exists = False
        self.vulnerability_failure = False
        self.trivy_available = True

    def run(
        self,
        command: tuple[str, ...] | list[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del check
        normalized = tuple(command)
        self.commands.append(normalized)
        stdout = ""
        if normalized[:3] == ("git", "rev-parse", "HEAD"):
            stdout = self.revision + "\n"
        elif normalized[:3] == ("git", "branch", "--show-current"):
            stdout = "main\n"
        elif normalized[:2] == ("git", "status"):
            stdout = self.worktree_status
        elif normalized[:2] == ("git", "commit"):
            self.revision = PUSHED_REVISION
        elif normalized[:3] == ("docker", "image", "inspect"):
            stdout = json.dumps(self.inspect_document)
        elif normalized[:3] == ("docker", "manifest", "inspect"):
            if self.manifest_exists:
                return subprocess.CompletedProcess(
                    normalized,
                    0,
                    stdout='{"schemaVersion": 2}',
                    stderr="",
                )
            return subprocess.CompletedProcess(
                normalized,
                1,
                stdout="",
                stderr="manifest unknown",
            )
        elif normalized[:2] == ("docker", "push") and not normalized[-1].endswith(
            ":latest"
        ):
            stdout = f"digest: {REGISTRY_DIGEST} size: 1234\n"
        elif normalized[:3] == ("docker", "scout", "sbom"):
            stdout = json.dumps(
                {
                    "spdxVersion": "SPDX-2.3",
                    "SPDXID": "SPDXRef-DOCUMENT",
                    "name": "image-sbom",
                    "packages": [],
                }
            )
        elif normalized[:2] == ("trivy", "image") and "--output" in normalized:
            output_path = Path(normalized[normalized.index("--output") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if "spdx-json" in normalized:
                output_path.write_text(
                    json.dumps(
                        {
                            "spdxVersion": "SPDX-2.3",
                            "SPDXID": "SPDXRef-DOCUMENT",
                            "name": "image-sbom",
                            "packages": [],
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                output_path.write_text('{"Results": []}\n', encoding="utf-8")
                if self.vulnerability_failure:
                    return subprocess.CompletedProcess(
                        normalized,
                        1,
                        stdout="",
                        stderr="policy findings",
                    )
        return subprocess.CompletedProcess(normalized, 0, stdout=stdout, stderr="")

    def which(self, executable: str) -> str | None:
        if executable == "trivy" and self.trivy_available:
            return "/usr/bin/trivy"
        return None


class ReleaseApiImageTests(unittest.TestCase):
    """Exercise plan, local build, evidence, and explicit publication behavior."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        self.app_root = self.repository / "app" / "apps" / "felix"
        self.app_root.mkdir(parents=True)
        (self.repository / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        (self.app_root / "pyproject.toml").write_text(
            "\n".join(
                (
                    "[tool.pdm]",
                    "distribution = false",
                    "",
                    "[project]",
                    'name = "felix"',
                    'version = "1.2.3"',
                    'requires-python = ">=3.13,<3.14"',
                    "dependencies = []",
                    "",
                )
            ),
            encoding="utf-8",
        )
        (self.app_root / "pdm.lock").write_text(
            "\n".join(
                (
                    "[metadata]",
                    'groups = ["default"]',
                    'lock_version = "4.5.0"',
                    'content_hash = "sha256:test"',
                    "",
                    "[[package]]",
                    'name = "fastapi"',
                    'version = "1.0.0"',
                    "files = [",
                    '  {file = "fastapi.whl", hash = "sha256:'
                    + ("e" * 64)
                    + '"},',
                    "]",
                    "",
                )
            ),
            encoding="utf-8",
        )
        self.runner = FakeRunner()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _plan(self, version: str | None = None):
        return create_release_plan(
            self.repository,
            "felix",
            version=version,
            runner=self.runner,
        )

    def _set_valid_inspection(self, plan) -> None:
        self.runner.inspect_document = [
            {
                "Id": IMAGE_ID,
                "Config": {
                    "User": "10001:10001",
                    "Env": [
                        "BACKEND_APP_ID=felix",
                        "APP_PROFILE=felix",
                    ],
                    "Labels": {
                        "org.opencontainers.image.revision": plan.git_revision,
                        "org.opencontainers.image.version": plan.image_tag,
                        "com.fe-wi.backend-app-id": "felix",
                        "com.fe-wi.app-profile": "felix",
                        "com.fe-wi.dependency-lock-sha256": (
                            plan.dependency_lock_sha256
                        ),
                    },
                    "Healthcheck": {"Test": ["CMD", "python", "-c", "health"]},
                },
            }
        ]

    def test_plan_uses_selected_app_manifest_lock_and_immutable_tag(self) -> None:
        plan = self._plan()

        self.assertEqual(plan.app_id, "felix")
        self.assertEqual(plan.app_profile, "felix")
        self.assertEqual(plan.image_ref, "sokrates1989/python-api-felix:1.2.3")
        self.assertEqual(plan.package_version, "1.2.3")
        self.assertEqual(len(plan.dependency_lock_sha256), 64)
        self.assertEqual(plan.pdm_version, "2.27.0")
        self.assertEqual(plan.git_revision, REVISION)

    def test_command_runner_replaces_non_utf8_scanner_bytes(self) -> None:
        """Keep Windows locale decoding from crashing scanner capture.

        Returns:
            None.

        Side Effects:
            Starts a short-lived Python child process that emits one invalid
            UTF-8 byte.
        """
        completed = CommandRunner().run(
            (
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(bytes([0x81]))",
            ),
            cwd=self.repository,
        )

        self.assertEqual(completed.stdout, "\ufffd")

    def test_plan_rejects_missing_lock_before_docker(self) -> None:
        (self.app_root / "pdm.lock").unlink()

        with self.assertRaisesRegex(ReleaseError, "Missing required release input"):
            self._plan()

        self.assertFalse(any(command[0] == "docker" for command in self.runner.commands))

    def test_plan_rejects_tag_that_differs_from_package_version(self) -> None:
        with self.assertRaisesRegex(ReleaseError, "must equal"):
            self._plan("1.2.4")

    def test_local_build_fails_closed_on_dirty_worktree(self) -> None:
        plan = self._plan()
        self.runner.worktree_status = " M app/apps/felix/pyproject.toml\n"

        with self.assertRaisesRegex(ReleaseError, "clean Git worktree"):
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse(
            any(command[:3] == ("docker", "buildx", "build") for command in self.runner.commands)
        )

    def test_local_build_never_pushes_and_writes_lock_sbom_receipt(self) -> None:
        plan = self._plan()
        self._set_valid_inspection(plan)

        receipt = build_release_image(self.repository, plan, runner=self.runner)

        commands = self.runner.commands
        self.assertTrue(
            any(command[:3] == ("docker", "buildx", "build") for command in commands)
        )
        self.assertFalse(any(command[:2] == ("docker", "push") for command in commands))
        self.assertNotIn("latest", " ".join(" ".join(command) for command in commands))
        self.assertEqual(receipt["state"], "built")
        self.assertFalse(receipt["deploymentAuthorized"])
        self.assertFalse(receipt["publication"]["immutableTagPushed"])
        self.assertFalse(receipt["publication"]["latestAllowedForDeployment"])
        image_sbom = json.loads(
            (self.repository / plan.sbom_path).read_text(encoding="utf-8")
        )
        dependency_sbom = json.loads(
            (self.repository / plan.dependency_sbom_path).read_text(encoding="utf-8")
        )
        self.assertEqual(image_sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(dependency_sbom["packages"][0]["name"], "fastapi")
        self.assertEqual(receipt["imageEvidence"]["sbomScanner"], "trivy")
        self.assertTrue((self.repository / plan.receipt_path).is_file())

    def test_build_command_binds_identity_revision_lock_and_pinned_pdm(self) -> None:
        plan = self._plan()
        self._set_valid_inspection(plan)

        build_release_image(self.repository, plan, runner=self.runner)

        build_command = next(
            command
            for command in self.runner.commands
            if command[:3] == ("docker", "buildx", "build")
        )
        rendered = " ".join(build_command)
        self.assertIn("BACKEND_APP_ID=felix", rendered)
        self.assertIn("APP_PROFILE=felix", rendered)
        self.assertIn(f"SOURCE_REVISION={REVISION}", rendered)
        self.assertIn(
            f"DEPENDENCY_LOCK_SHA256={plan.dependency_lock_sha256}",
            rendered,
        )
        self.assertIn("PDM_VERSION=2.27.0", rendered)
        self.assertIn("--platform linux/amd64", rendered)

    def test_build_rejects_root_image_before_receipt(self) -> None:
        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.inspect_document[0]["Config"]["User"] = "root"  # type: ignore[index]

        with self.assertRaisesRegex(ReleaseError, "non-root"):
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse((self.repository / plan.receipt_path).exists())

    def test_vulnerability_policy_failure_blocks_successful_receipt(self) -> None:
        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.vulnerability_failure = True

        with self.assertRaisesRegex(ReleaseError, "Vulnerability policy failed"):
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse((self.repository / plan.receipt_path).exists())

    def test_scout_fallback_rejects_only_fixable_high_critical_findings(self) -> None:
        """Keep Docker Scout aligned with Trivy's ignore-unfixed policy."""

        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.trivy_available = False

        receipt = build_release_image(self.repository, plan, runner=self.runner)

        scout_command = next(
            command
            for command in self.runner.commands
            if command[:3] == ("docker", "scout", "cves")
        )
        self.assertIn("--only-fixed", scout_command)
        self.assertEqual(
            receipt["vulnerabilityPolicy"]["policy"]["rejectedSeverities"],
            ["HIGH", "CRITICAL"],
        )
        self.assertTrue(
            receipt["vulnerabilityPolicy"]["policy"]["ignoreUnfixed"]
        )

    def test_publish_commits_and_pushes_bump_before_images_then_latest(self) -> None:
        """Commit a greater version before proving and publishing its image."""

        original_plan = self._plan()
        del original_plan
        # publish_release_image creates its plan after the release commit. Build
        # inspection must therefore describe the pushed source revision.
        lock_sha = __import__("hashlib").sha256(
            (self.app_root / "pdm.lock").read_bytes()
        ).hexdigest()
        self.runner.inspect_document = [
            {
                "Id": IMAGE_ID,
                "Config": {
                    "User": "10001:10001",
                    "Env": ["BACKEND_APP_ID=felix", "APP_PROFILE=felix"],
                    "Labels": {
                        "org.opencontainers.image.revision": PUSHED_REVISION,
                        "org.opencontainers.image.version": "1.2.4",
                        "com.fe-wi.backend-app-id": "felix",
                        "com.fe-wi.app-profile": "felix",
                        "com.fe-wi.dependency-lock-sha256": lock_sha,
                    },
                    "Healthcheck": {"Test": ["CMD", "python", "-c", "health"]},
                },
            }
        ]

        receipt = publish_release_image(
            self.repository,
            "felix",
            "1.2.4",
            runner=self.runner,
        )

        commands = self.runner.commands
        commit_index = next(i for i, command in enumerate(commands) if command[:2] == ("git", "commit"))
        git_push_index = next(i for i, command in enumerate(commands) if command == ("git", "push"))
        build_index = next(i for i, command in enumerate(commands) if command[:3] == ("docker", "buildx", "build"))
        immutable_push_index = next(
            i
            for i, command in enumerate(commands)
            if command == ("docker", "push", "sokrates1989/python-api-felix:1.2.4")
        )
        latest_push_index = next(
            i
            for i, command in enumerate(commands)
            if command == ("docker", "push", "sokrates1989/python-api-felix:latest")
        )
        self.assertLess(commit_index, build_index)
        self.assertLess(build_index, git_push_index)
        self.assertLess(build_index, immutable_push_index)
        self.assertLess(git_push_index, immutable_push_index)
        self.assertLess(immutable_push_index, latest_push_index)
        self.assertEqual(receipt["publication"]["immutableDigest"], REGISTRY_DIGEST)
        self.assertTrue(receipt["publication"]["latestConvenienceTagPushed"])
        self.assertFalse(receipt["publication"]["latestAllowedForDeployment"])
        self.assertEqual(
            (self.app_root / "pyproject.toml").read_text(encoding="utf-8").count(
                'version = "1.2.4"'
            ),
            1,
        )

    def test_publish_reuses_current_version_without_source_mutation(self) -> None:
        """Publish an absent current tag while retaining the manifest and HEAD."""

        plan = self._plan()
        self._set_valid_inspection(plan)

        receipt = publish_release_image(
            self.repository,
            "felix",
            "1.2.3",
            allow_current_version=True,
            runner=self.runner,
        )

        commands = self.runner.commands
        build_index = next(
            index
            for index, command in enumerate(commands)
            if command[:3] == ("docker", "buildx", "build")
        )
        source_push_index = next(
            index
            for index, command in enumerate(commands)
            if command == ("git", "push")
        )
        immutable_push_index = next(
            index
            for index, command in enumerate(commands)
            if command
            == ("docker", "push", "sokrates1989/python-api-felix:1.2.3")
        )

        self.assertFalse(
            any(command[:2] == ("git", "commit") for command in commands)
        )
        self.assertFalse(any(command[:2] == ("git", "add") for command in commands))
        self.assertLess(build_index, source_push_index)
        self.assertLess(source_push_index, immutable_push_index)
        self.assertEqual(receipt["plan"]["git_revision"], REVISION)
        self.assertEqual(
            receipt["sourcePublication"],
            {
                "currentVersionReused": True,
                "versionBumpCommitCreated": False,
            },
        )
        self.assertEqual(
            (self.app_root / "pyproject.toml").read_text(encoding="utf-8").count(
                'version = "1.2.3"'
            ),
            1,
        )

    def test_publish_rejects_non_increment_before_git_or_docker_mutation(self) -> None:
        """Reject current-version publication without explicit authorization."""

        with self.assertRaisesRegex(ReleaseError, "greater than"):
            publish_release_image(
                self.repository,
                "felix",
                "1.2.3",
                runner=self.runner,
            )

        self.assertFalse(any(command[:2] == ("git", "commit") for command in self.runner.commands))
        self.assertFalse(any(command[0] == "docker" for command in self.runner.commands))

    def test_publish_refuses_to_overwrite_existing_immutable_tag(self) -> None:
        self.runner.manifest_exists = True

        with self.assertRaisesRegex(ReleaseError, "already exists"):
            publish_release_image(
                self.repository,
                "felix",
                "1.2.4",
                runner=self.runner,
            )

        self.assertFalse(
            any(command[:2] == ("git", "commit") for command in self.runner.commands)
        )


if __name__ == "__main__":
    unittest.main()
