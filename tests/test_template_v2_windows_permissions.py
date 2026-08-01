"""Tests for inherited Windows ACLs on backend lifecycle staging paths."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from template_v2.windows_permissions import reset_windows_inherited_permissions


class TemplateV2WindowsPermissionsTest(unittest.TestCase):
    """Verify safe no-op, command, failure, and live Windows behavior."""

    def test_non_windows_host_performs_no_subprocess(self) -> None:
        """Leave POSIX staging permissions to the process umask."""

        runner = Mock()
        with patch("template_v2.windows_permissions.os.name", "posix"):
            reset_windows_inherited_permissions(Path("unused"), command_runner=runner)

        runner.assert_not_called()

    def test_windows_host_uses_shell_free_bounded_icacls_reset(self) -> None:
        """Reset only the exact existing path without exposing command output."""

        runner = Mock(return_value=subprocess.CompletedProcess([], 0))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage"
            path.mkdir()
            with patch("template_v2.windows_permissions.os.name", "nt"):
                reset_windows_inherited_permissions(path, command_runner=runner)

        runner.assert_called_once_with(
            ["icacls", str(path), "/reset", "/Q"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def test_rejected_reset_raises_content_free_error(self) -> None:
        """Fail publication without reflecting localized ACL diagnostics."""

        private_output = "localized path and principal details"
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [],
                5,
                stdout=private_output,
                stderr=private_output,
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage"
            path.mkdir()
            with (
                patch("template_v2.windows_permissions.os.name", "nt"),
                self.assertRaises(OSError) as context,
            ):
                reset_windows_inherited_permissions(path, command_runner=runner)

        self.assertNotIn(private_output, str(context.exception))

    @unittest.skipUnless(os.name == "nt", "live ACL reset requires Windows")
    def test_live_windows_reset_accepts_fresh_staging_directory(self) -> None:
        """Prove the platform command works on a disposable fresh directory."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage"
            path.mkdir()

            reset_windows_inherited_permissions(path)

            self.assertTrue(path.is_dir())


if __name__ == "__main__":
    unittest.main()
