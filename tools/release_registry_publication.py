"""Visible Docker build and registry publication helpers.

The module keeps operator-facing Docker output live, retries image publication
through an explicit Docker login when requested, and never performs Git
operations. Credentials remain owned by the Docker CLI and terminal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Protocol, Sequence

try:
    from tools.release_command import ReleaseError, safe_command_error
except ModuleNotFoundError:
    from release_command import (  # type: ignore[no-redef]
        ReleaseError,
        safe_command_error,
    )


class RegistryCommandRunner(Protocol):
    """Command behavior required by visible Docker publication."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run one captured command.

        Args:
            command: Executable and arguments.
            cwd: Child-process working directory.
            check: Whether nonzero status raises.

        Returns:
            subprocess.CompletedProcess[str]: Captured command result.
        """


def run_visible(
    runner: RegistryCommandRunner,
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command with live output when the runner supports streaming.

    Args:
        runner: Injectable command runner.
        command: Executable and arguments.
        cwd: Child-process working directory.
        check: Whether nonzero status raises.

    Returns:
        subprocess.CompletedProcess[str]: Combined retained command output.

    Side Effects:
        Executes the command and may stream output to the operator terminal.

    Raises:
        ReleaseError: Through the runner when a checked command fails.
    """

    streaming_method = getattr(runner, "run_streaming", None)
    if callable(streaming_method):
        return streaming_method(command, cwd=cwd, check=check)
    return runner.run(command, cwd=cwd, check=check)


def _registry_login_command(image_ref: str) -> tuple[str, ...]:
    """Resolve the Docker login command for an image reference.

    Args:
        image_ref: Versioned image reference.

    Returns:
        tuple[str, ...]: Docker Hub login by default, or an explicit registry
        login command for qualified repository names.
    """

    first_segment = image_ref.split("/", 1)[0]
    if (
        "." in first_segment
        or ":" in first_segment
        or first_segment == "localhost"
    ):
        return ("docker", "login", first_segment)
    return ("docker", "login")


def _raise_push_failure(
    image_ref: str,
    completed: subprocess.CompletedProcess[str],
) -> None:
    """Raise one sanitized Docker push failure.

    Args:
        image_ref: Failed image reference.
        completed: Failed Docker push result.

    Returns:
        None.

    Raises:
        ReleaseError: Always, with bounded sanitized command output.
    """

    detail = safe_command_error(completed)
    raise ReleaseError(f"Docker push failed for {image_ref}.\n{detail}")


def push_image_with_auth_retry(
    repository_root: Path,
    image_ref: str,
    runner: RegistryCommandRunner,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> subprocess.CompletedProcess[str]:
    """Push an image visibly and offer Docker login after a failed attempt.

    Args:
        repository_root: Docker command working directory.
        image_ref: Exact image reference to publish.
        runner: Injectable captured/streaming command runner.
        input_fn: Interactive prompt function; defaults to built-in input.
        output_fn: Operator status writer; defaults to built-in print.

    Returns:
        subprocess.CompletedProcess[str]: Successful push result containing the
        registry-reported digest.

    Side Effects:
        Pushes an image. On failure and default-yes approval, runs interactive
        Docker login and retries once.

    Raises:
        ReleaseError: If login is declined, login fails, or the retry fails.
    """

    output_fn(f"Pushing image: {image_ref}")
    completed = run_visible(
        runner,
        ("docker", "push", image_ref),
        cwd=repository_root,
        check=False,
    )
    if completed.returncode == 0:
        output_fn(f"[OK] Successfully pushed: {image_ref}")
        return completed

    output_fn("")
    output_fn("[WARN] Docker push failed; registry login may be required.")
    retry = input_fn("Log in to Docker and retry? (Y/n): ").strip()
    if retry.lower().startswith("n"):
        _raise_push_failure(image_ref, completed)

    login_command = _registry_login_command(image_ref)
    output_fn("Starting Docker registry login...")
    run_visible(runner, login_command, cwd=repository_root)
    output_fn("Retrying Docker push...")
    retried = run_visible(
        runner,
        ("docker", "push", image_ref),
        cwd=repository_root,
        check=False,
    )
    if retried.returncode != 0:
        _raise_push_failure(image_ref, retried)
    output_fn(f"[OK] Successfully pushed: {image_ref}")
    return retried
