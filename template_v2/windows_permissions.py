"""Restore inherited Windows ACLs on backend lifecycle staging paths.

Windows preserves a moved directory or file's discretionary ACL. The backend
lifecycle resets each freshly created staging resource while it is still next
to its destination so atomic publication remains accessible to the same
principals as the repository. Other operating systems require no action.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def reset_windows_inherited_permissions(
    path: Path,
    *,
    command_runner: CommandRunner = subprocess.run,
) -> None:
    """Reset one fresh Windows path to its parent's inherited ACL.

    Args:
        path: Existing non-link staging file or directory.
        command_runner: Injectable subprocess-compatible test seam.

    Returns:
        None on non-Windows hosts or after a successful reset.

    Raises:
        OSError: If the path is unsafe, ``icacls`` cannot run, times out, or
            rejects the reset. Command output is deliberately not reflected.

    Side Effects:
        On Windows, replaces explicit staging ACL entries with the default ACL
        inherited from the current parent directory.
    """

    if os.name != "nt":
        return
    if path.is_symlink() or not path.exists():
        raise OSError("Windows permission reset requires an existing non-link path")
    try:
        completed = command_runner(
            ["icacls", str(path), "/reset", "/Q"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OSError("Windows inherited permission reset failed") from error
    if completed.returncode != 0:
        raise OSError("Windows inherited permission reset was rejected")
