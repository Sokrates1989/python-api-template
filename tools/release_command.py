"""Shell-free, secret-conscious command execution for API release tools."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Sequence


SECRET_KEY_PATTERN = re.compile(
    r"(?:password|passwd|secret|token|private[_-]?key|credential)",
    re.IGNORECASE,
)


class ReleaseError(RuntimeError):
    """Raised when a release action cannot satisfy its safety contract."""


class CommandRunner:
    """Execute release commands without shell interpolation."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run one argument-vector command with deterministic UTF-8 capture.

        Undecodable scanner bytes are replaced so Windows locale differences
        cannot crash the reader threads or bypass fail-closed policy handling.

        Args:
            command: Executable and arguments.
            cwd: Child-process working directory.
            check: Whether nonzero exit status raises.

        Returns:
            subprocess.CompletedProcess[str]: Captured process result.

        Side Effects:
            Executes the requested external process.

        Raises:
            ReleaseError: If ``check`` is true and the process fails.
        """

        completed = subprocess.run(
            list(command),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if check and completed.returncode != 0:
            detail = safe_command_error(completed)
            raise ReleaseError(f"Command failed: {' '.join(command)}\n{detail}")
        return completed

    def which(self, executable: str) -> str | None:
        """Locate an executable through the host path.

        Args:
            executable: Program name to resolve.

        Returns:
            str | None: Executable path, or ``None`` when missing.
        """

        return shutil.which(executable)


def safe_command_error(completed: subprocess.CompletedProcess[str]) -> str:
    """Sanitize and bound child-process failure output.

    Args:
        completed: Failed subprocess result.

    Returns:
        str: At most twenty bounded, secret-conscious lines.
    """

    lines = (completed.stderr or completed.stdout or "").splitlines()
    safe_lines = []
    for line in lines[-20:]:
        if SECRET_KEY_PATTERN.search(line):
            safe_lines.append("[redacted potentially secret-bearing output]")
        else:
            safe_lines.append(line[:500])
    return "\n".join(safe_lines) or f"exit code {completed.returncode}"
