"""Tests for visible Docker registry publication and login retry behavior."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from tools.release_command import ReleaseError
from tools.release_registry_publication import push_image_with_auth_retry


class RegistryRunner:
    """Provide deterministic Docker push and login command outcomes."""

    def __init__(self, *, fail_first_push: bool = False) -> None:
        """Initialize one registry command fake.

        Args:
            fail_first_push: Whether the first image push should fail.

        Returns:
            None.
        """

        self.fail_first_push = fail_first_push
        self.push_attempts = 0
        self.commands: list[tuple[str, ...]] = []
        self.streamed_commands: list[tuple[str, ...]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Return configured Docker results.

        Args:
            command: Docker argument vector.
            cwd: Ignored working directory.
            check: Whether a configured failure should raise.

        Returns:
            subprocess.CompletedProcess[str]: Deterministic command result.

        Raises:
            ReleaseError: If a checked command fails.
        """

        del cwd
        normalized = tuple(command)
        self.commands.append(normalized)
        return_code = 0
        stdout = ""
        if normalized[:2] == ("docker", "push"):
            self.push_attempts += 1
            if self.fail_first_push and self.push_attempts == 1:
                return_code = 1
                stdout = "unauthorized"
            else:
                stdout = "digest: sha256:" + ("a" * 64)
        completed = subprocess.CompletedProcess(
            normalized,
            return_code,
            stdout=stdout,
            stderr="",
        )
        if check and return_code != 0:
            raise ReleaseError("configured registry command failed")
        return completed

    def run_streaming(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Record visible execution before returning the configured result.

        Args:
            command: Docker argument vector.
            cwd: Ignored working directory.
            check: Whether a configured failure should raise.

        Returns:
            subprocess.CompletedProcess[str]: Deterministic command result.

        Raises:
            ReleaseError: Through :meth:`run` for a checked failure.
        """

        self.streamed_commands.append(tuple(command))
        return self.run(command, cwd=cwd, check=check)


class RegistryPublicationTests(unittest.TestCase):
    """Verify Docker-only authentication and default-yes retry behavior."""

    def setUp(self) -> None:
        """Create one isolated command working directory.

        Returns:
            None.
        """

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def test_successful_push_never_requests_login(self) -> None:
        """Return the first successful Docker push without authentication."""

        runner = RegistryRunner()
        prompts: list[str] = []

        completed = push_image_with_auth_retry(
            self.root,
            "sokrates1989/python-api-felix:0.1.1",
            runner,
            input_fn=lambda prompt: prompts.append(prompt) or "",
            output_fn=lambda message: None,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(prompts, [])
        self.assertNotIn(("docker", "login"), runner.commands)
        self.assertIn(
            ("docker", "push", "sokrates1989/python-api-felix:0.1.1"),
            runner.streamed_commands,
        )

    def test_failed_push_uses_default_yes_docker_login_and_retry(self) -> None:
        """Run Docker login and retry when Enter accepts the default."""

        runner = RegistryRunner(fail_first_push=True)

        completed = push_image_with_auth_retry(
            self.root,
            "sokrates1989/python-api-felix:0.1.1",
            runner,
            input_fn=lambda prompt: "",
            output_fn=lambda message: None,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(runner.push_attempts, 2)
        self.assertIn(("docker", "login"), runner.commands)
        self.assertIn(("docker", "login"), runner.streamed_commands)
        self.assertFalse(any(command[0] == "git" for command in runner.commands))

    def test_declined_login_returns_a_sanitized_failure(self) -> None:
        """Fail without login when the operator explicitly enters no."""

        runner = RegistryRunner(fail_first_push=True)

        with self.assertRaisesRegex(ReleaseError, "Docker push failed"):
            push_image_with_auth_retry(
                self.root,
                "sokrates1989/python-api-felix:0.1.1",
                runner,
                input_fn=lambda prompt: "n",
                output_fn=lambda message: None,
            )

        self.assertEqual(runner.push_attempts, 1)
        self.assertNotIn(("docker", "login"), runner.commands)


if __name__ == "__main__":
    unittest.main()
