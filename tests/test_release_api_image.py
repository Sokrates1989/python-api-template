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
        """Initialize deterministic command outputs and invocation records."""

        self.commands: list[tuple[str, ...]] = []
        self.command_cwds: list[Path] = []
        self.inspect_document: list[dict[str, object]] = []
        self.revision = REVISION
        self.worktree_status = ""
        self.manifest_exists = False
        self.vulnerability_failure = False
        self.vulnerability_operational_failure = False
        self.trivy_available = True

    def run(
        self,
        command: tuple[str, ...] | list[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Record a command and return its configured deterministic result.

        Args:
            command: Shell-free executable and argument vector.
            cwd: Requested process working directory.
            check: Accepted for parity with the production command runner.

        Returns:
            subprocess.CompletedProcess[str]: Simulated process outcome.

        Side Effects:
            Records the command and working directory, mutates the simulated
            revision after a commit, and may write scanner output fixtures.
        """

        del check
        normalized = tuple(command)
        self.commands.append(normalized)
        self.command_cwds.append(cwd)
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
            return self._manifest_result(normalized)
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
        elif normalized[:3] == ("docker", "scout", "cves"):
            return self._scout_cves_result(normalized)
        elif normalized[:2] == ("trivy", "image") and "--output" in normalized:
            return self._trivy_result(normalized)
        return subprocess.CompletedProcess(normalized, 0, stdout=stdout, stderr="")

    def _manifest_result(
        self,
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        """Return configured registry manifest existence.

        Args:
            command: Recorded Docker manifest command.

        Returns:
            subprocess.CompletedProcess[str]: Existing or missing result.
        """

        if self.manifest_exists:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"schemaVersion": 2}',
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="manifest unknown",
        )

    def _scout_cves_result(
        self,
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        """Write a Docker Scout SARIF fixture and return its policy result.

        Args:
            command: Recorded Docker Scout CVE command.

        Returns:
            subprocess.CompletedProcess[str]: Clean, finding, or operational result.

        Side Effects:
            Writes the requested SARIF output except during an operational failure.
        """

        output_path = Path(command[command.index("--output") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.vulnerability_operational_failure:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="registry authentication failed",
            )
        results: list[dict[str, object]] = []
        if self.vulnerability_failure:
            results.append(
                {
                    "ruleId": "CVE-2099-0002",
                    "level": "error",
                    "message": {"text": "openssl 1.0 is affected; upgrade to 1.1"},
                    "properties": {
                        "package": "openssl",
                        "installedVersion": "1.0",
                        "fixedVersion": "1.1",
                    },
                }
            )
        output_path.write_text(
            json.dumps({"version": "2.1.0", "runs": [{"results": results}]}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            2 if self.vulnerability_failure else 0,
            stdout="",
            stderr="vulnerabilities found" if self.vulnerability_failure else "",
        )

    def _trivy_result(
        self,
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        """Write a Trivy SPDX or vulnerability fixture.

        Args:
            command: Recorded Trivy command.

        Returns:
            subprocess.CompletedProcess[str]: Clean, finding, or operational result.

        Side Effects:
            Writes the requested scanner output except during an operational failure.
        """

        output_path = Path(command[command.index("--output") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if "spdx-json" in command:
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
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if self.vulnerability_operational_failure:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="vulnerability database unavailable",
            )
        vulnerabilities = []
        if self.vulnerability_failure:
            vulnerabilities.append(
                {
                    "VulnerabilityID": "CVE-2099-0001",
                    "Severity": "CRITICAL",
                    "PkgName": "libexample",
                    "InstalledVersion": "1.0",
                    "FixedVersion": "1.1",
                    "Title": "Example memory corruption",
                }
            )
        output_path.write_text(
            json.dumps(
                {
                    "Results": [
                        {
                            "Target": "python:3.13-slim",
                            "Vulnerabilities": vulnerabilities,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            1 if self.vulnerability_failure else 0,
            stdout="",
            stderr="policy findings" if self.vulnerability_failure else "",
        )

    def which(self, executable: str) -> str | None:
        """Resolve the simulated vulnerability scanner executable.

        Args:
            executable: Tool name requested by release evidence code.

        Returns:
            str | None: Fake Trivy path when enabled; otherwise ``None``.
        """

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
        self._write_startup_smoke_fixture()
        self.runner = FakeRunner()

    def _write_startup_smoke_fixture(self) -> None:
        """Create one public non-default app-owned startup-smoke fixture.

        Returns:
            None.

        Side Effects:
            Writes the selected app's dedicated release-smoke environment.
        """

        deployment_root = self.app_root / "deployment"
        deployment_root.mkdir()
        (deployment_root / "release-startup-smoke.env").write_text(
            "\n".join(
                (
                    "APP_ENVIRONMENT=production",
                    "BACKEND_APP_ID=felix",
                    "APP_PROFILE=felix",
                    "DB_PASSWORD_FILE=/tmp/release-smoke/database-password",
                    "CORS_ORIGINS=https://web.release-smoke.example.com",
                    "AUTH_PROVIDER=keycloak",
                    "KEYCLOAK_SERVER_URL=https://identity.release-smoke.example.com",
                    "KEYCLOAK_REALM=release-smoke-realm",
                    "KEYCLOAK_CLIENT_ID=release-smoke-frontend",
                    "KEYCLOAK_AUDIENCE=release-smoke-api",
                    "KEYCLOAK_ADMIN_CLIENT_ID=release-smoke-backend",
                    "KEYCLOAK_ADMIN_CLIENT_SECRET_FILE="
                    "/tmp/release-smoke/keycloak-client-secret",
                    "",
                )
            ),
            encoding="utf-8",
        )

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
        self.runner.worktree_status = " M app/apps/felix/pyproject.toml\0"

        with self.assertRaisesRegex(ReleaseError, "selected-app and shared"):
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse(
            any(command[:3] == ("docker", "buildx", "build") for command in self.runner.commands)
        )

    def test_local_build_isolates_dirty_sibling_app_at_committed_head(self) -> None:
        """Allow sibling work without copying it into the selected-app image."""

        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.worktree_status = (
            " M app/apps/booking_service/models/company.py\0"
            "?? app/apps/booking_service/schemas/company.py\0"
            " M tools/booking_quality/runtime_checks.py\0"
            "?? tests/test_booking_service_company_settings.py\0"
        )

        receipt = build_release_image(self.repository, plan, runner=self.runner)

        add_index = next(
            index
            for index, command in enumerate(self.runner.commands)
            if command[:3] == ("git", "worktree", "add")
        )
        build_index = next(
            index
            for index, command in enumerate(self.runner.commands)
            if command[:3] == ("docker", "buildx", "build")
        )
        remove_index = next(
            index
            for index, command in enumerate(self.runner.commands)
            if command[:3] == ("git", "worktree", "remove")
        )
        self.assertLess(add_index, build_index)
        self.assertLess(build_index, remove_index)
        self.assertNotEqual(self.runner.command_cwds[build_index], self.repository)
        self.assertEqual(self.runner.commands[add_index][-1], REVISION)
        self.assertEqual(receipt["plan"]["app_id"], "felix")

    def test_local_build_blocks_dirty_shared_image_input(self) -> None:
        """Reject a dirty shared runtime path that affects every app image."""

        plan = self._plan()
        self.runner.worktree_status = " M app/backend/config.py\0"

        with self.assertRaisesRegex(ReleaseError, "app/backend/config.py"):
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse(
            any(
                command[:3] == ("docker", "buildx", "build")
                for command in self.runner.commands
            )
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
        self.assertFalse(receipt["publication"]["versionTagPushed"])
        self.assertTrue(receipt["publication"]["versionTagRepublishAllowed"])
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
        vulnerability_report = self.repository / plan.vulnerability_report_path
        self.assertTrue(vulnerability_report.is_file())
        self.assertEqual(
            receipt["vulnerabilityPolicy"]["reportPath"],
            plan.vulnerability_report_path,
        )
        self.assertEqual(len(receipt["vulnerabilityPolicy"]["reportSha256"]), 64)
        self.assertIs(receipt["startupSmoke"]["executed"], True)
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

    def test_build_runs_non_default_startup_smoke_before_image_evidence(self) -> None:
        """Import the built production app with non-default coherent identity.

        Returns:
            None.
        """

        plan = self._plan()
        self._set_valid_inspection(plan)

        receipt = build_release_image(self.repository, plan, runner=self.runner)

        commands = self.runner.commands
        inspect_index = next(
            index
            for index, command in enumerate(commands)
            if command[:3] == ("docker", "image", "inspect")
        )
        smoke_index = next(
            index
            for index, command in enumerate(commands)
            if command[:2] == ("docker", "run")
        )
        evidence_index = next(
            index
            for index, command in enumerate(commands)
            if command[:2] == ("trivy", "image")
        )
        smoke_command = commands[smoke_index]
        rendered = " ".join(smoke_command)
        self.assertLess(inspect_index, smoke_index)
        self.assertLess(smoke_index, evidence_index)
        self.assertIn("KEYCLOAK_REALM=release-smoke-realm", smoke_command)
        self.assertIn("KEYCLOAK_CLIENT_ID=release-smoke-frontend", smoke_command)
        self.assertIn("KEYCLOAK_AUDIENCE=release-smoke-api", smoke_command)
        self.assertIn("import main", rendered)
        self.assertIs(receipt["startupSmoke"]["executed"], True)
        self.assertNotIn("felix-new-frontend", rendered)

    def test_startup_smoke_rejects_direct_secret_fields(self) -> None:
        """Block a release fixture that attempts to embed a secret value.

        Returns:
            None.
        """

        fixture = (
            self.app_root / "deployment" / "release-startup-smoke.env"
        )
        fixture.write_text(
            fixture.read_text(encoding="utf-8")
            + "KEYCLOAK_CLIENT_SECRET=unsafe-placeholder\n",
            encoding="utf-8",
        )
        plan = self._plan()
        self._set_valid_inspection(plan)

        with self.assertRaisesRegex(ReleaseError, "direct secret field"):
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse(
            any(command[:2] == ("docker", "push") for command in self.runner.commands)
        )

    def test_build_rejects_root_image_before_receipt(self) -> None:
        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.inspect_document[0]["Config"]["User"] = "root"  # type: ignore[index]

        with self.assertRaisesRegex(ReleaseError, "non-root"):
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse((self.repository / plan.receipt_path).exists())

    def test_vulnerability_policy_failure_blocks_successful_receipt(self) -> None:
        """Show the exact fixable finding while withholding a success receipt.

        Returns:
            None.
        """

        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.vulnerability_failure = True

        with self.assertRaises(ReleaseError) as raised:
            build_release_image(self.repository, plan, runner=self.runner)

        self.assertFalse((self.repository / plan.receipt_path).exists())
        message = str(raised.exception)
        self.assertIn("CVE-2099-0001", message)
        self.assertIn("package=libexample", message)
        self.assertIn("fixed=1.1", message)
        self.assertIn(plan.vulnerability_report_path, message)
        self.assertIn("trivy image", message)
        self.assertIn("release_api_image.py build", message)

    def test_scanner_operational_failure_is_not_reported_as_a_cve(self) -> None:
        """Separate scanner/database failures from vulnerability findings.

        Returns:
            None.
        """

        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.vulnerability_operational_failure = True

        with self.assertRaises(ReleaseError) as raised:
            build_release_image(self.repository, plan, runner=self.runner)

        message = str(raised.exception)
        self.assertIn("scanner operational error", message)
        self.assertIn("vulnerability database unavailable", message)
        self.assertNotIn("Blocking findings:", message)

    def test_scout_failure_prints_exact_sarif_finding_and_rerun(self) -> None:
        """Expose Docker Scout findings instead of one ambiguous rejection.

        Returns:
            None.
        """

        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.trivy_available = False
        self.runner.vulnerability_failure = True

        with self.assertRaises(ReleaseError) as raised:
            build_release_image(self.repository, plan, runner=self.runner)

        message = str(raised.exception)
        self.assertIn("Scanner: docker-scout", message)
        self.assertIn("CVE-2099-0002", message)
        self.assertIn("package=openssl", message)
        self.assertIn("docker scout cves", message)

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

    def test_publish_commits_bump_then_pushes_version_and_latest(self) -> None:
        """Commit only the app bump before proving and publishing its image."""

        original_plan = self._plan()
        del original_plan
        # publish_release_image creates its plan after the local release commit.
        # Build inspection must therefore describe that exact source revision.
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
        self.runner.worktree_status = (
            "M  app/apps/booking_service/models/company.py\0"
        )

        receipt = publish_release_image(
            self.repository,
            "felix",
            "1.2.4",
            runner=self.runner,
        )

        commands = self.runner.commands
        commit_index = next(i for i, command in enumerate(commands) if command[:2] == ("git", "commit"))
        commit_command = commands[commit_index]
        build_index = next(i for i, command in enumerate(commands) if command[:3] == ("docker", "buildx", "build"))
        version_push_index = next(
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
        self.assertIn("--only", commit_command)
        self.assertEqual(commit_command[-1], "app/apps/felix/pyproject.toml")
        smoke_index = next(
            i
            for i, command in enumerate(commands)
            if command[:2] == ("docker", "run")
        )
        self.assertLess(build_index, version_push_index)
        self.assertLess(smoke_index, version_push_index)
        self.assertLess(version_push_index, latest_push_index)
        self.assertFalse(any(command == ("git", "push") for command in commands))
        self.assertEqual(receipt["publication"]["registryDigest"], REGISTRY_DIGEST)
        self.assertTrue(receipt["publication"]["versionTagPushed"])
        self.assertTrue(receipt["publication"]["versionTagRepublishAllowed"])
        self.assertTrue(receipt["publication"]["latestConvenienceTagPushed"])
        self.assertFalse(receipt["publication"]["latestAllowedForDeployment"])
        self.assertFalse(receipt["sourcePublication"]["gitPushPerformed"])
        self.assertEqual(
            (self.app_root / "pyproject.toml").read_text(encoding="utf-8").count(
                'version = "1.2.4"'
            ),
            1,
        )

    def test_publish_reuses_current_version_without_source_mutation(self) -> None:
        """Publish or replace the current tag while retaining manifest and HEAD."""

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
        version_push_index = next(
            index
            for index, command in enumerate(commands)
            if command
            == ("docker", "push", "sokrates1989/python-api-felix:1.2.3")
        )

        self.assertFalse(
            any(command[:2] == ("git", "commit") for command in commands)
        )
        self.assertFalse(any(command[:2] == ("git", "add") for command in commands))
        self.assertFalse(any(command == ("git", "push") for command in commands))
        self.assertLess(build_index, version_push_index)
        self.assertEqual(receipt["plan"]["git_revision"], REVISION)
        self.assertEqual(
            receipt["sourcePublication"],
            {
                "currentVersionReused": True,
                "versionBumpCommitCreated": False,
                "gitPushPerformed": False,
                "sourcePushOwnedByOperator": True,
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

    def test_publish_does_not_block_or_probe_existing_version_tag(self) -> None:
        """Permit version-tag replacement without a registry manifest precheck."""

        plan = self._plan()
        self._set_valid_inspection(plan)
        self.runner.manifest_exists = True

        receipt = publish_release_image(
            self.repository,
            "felix",
            "1.2.3",
            allow_current_version=True,
            runner=self.runner,
        )

        self.assertFalse(
            any(
                command[:3] == ("docker", "manifest", "inspect")
                for command in self.runner.commands
            )
        )
        self.assertTrue(receipt["publication"]["versionTagRepublishAllowed"])


if __name__ == "__main__":
    unittest.main()
