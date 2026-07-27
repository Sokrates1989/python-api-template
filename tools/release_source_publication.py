"""Git versioning and immutable-registry guards for API image publication."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Protocol, Sequence

try:
    from tools.release_command import ReleaseError
except ModuleNotFoundError:
    from release_command import ReleaseError  # type: ignore[no-redef]


SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)


class PublicationCommandRunner(Protocol):
    """Command behavior required by source and registry publication guards."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run one argument-vector command.

        Args:
            command: Executable and arguments.
            cwd: Child-process working directory.
            check: Whether failure should raise.

        Returns:
            subprocess.CompletedProcess[str]: Captured result.

        Side Effects:
            Executes the requested external process.
        """


def git_output(
    runner: PublicationCommandRunner,
    repository_root: Path,
    *arguments: str,
) -> str:
    """Run a read-only Git query.

    Args:
        runner: Injectable command runner.
        repository_root: Git working tree.
        arguments: Git arguments after the executable.

    Returns:
        str: Stripped standard output.

    Raises:
        ReleaseError: Through the runner when Git fails.
    """

    completed = runner.run(("git", *arguments), cwd=repository_root)
    return completed.stdout.strip()


def ensure_clean_worktree(
    repository_root: Path,
    runner: PublicationCommandRunner,
) -> None:
    """Require a completely clean Git tree.

    Args:
        repository_root: Git working tree.
        runner: Injectable command runner.

    Side Effects:
        Executes a read-only Git status query.

    Raises:
        ReleaseError: If tracked, staged, or untracked changes exist.
    """

    status = git_output(
        runner,
        repository_root,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )
    if status:
        raise ReleaseError(
            "Build & Push requires a clean Git worktree before the version bump."
        )


def ensure_release_branch(
    repository_root: Path,
    runner: PublicationCommandRunner,
) -> None:
    """Require the protected release branch.

    Args:
        repository_root: Git working tree.
        runner: Injectable command runner.

    Side Effects:
        Executes a read-only Git branch query.

    Raises:
        ReleaseError: If the current branch is not ``main``.
    """

    branch = git_output(runner, repository_root, "branch", "--show-current")
    if branch != "main":
        raise ReleaseError(
            f"Build & Push is allowed only from main; current branch is {branch!r}."
        )


def ensure_immutable_tag_absent(
    repository_root: Path,
    image_ref: str,
    runner: PublicationCommandRunner,
) -> None:
    """Refuse to overwrite an immutable registry version.

    Args:
        repository_root: Docker command working directory.
        image_ref: Proposed immutable registry reference.
        runner: Injectable command runner.

    Side Effects:
        Reads registry manifest state.

    Raises:
        ReleaseError: If the tag exists or absence cannot be proven.
    """

    completed = runner.run(
        ("docker", "manifest", "inspect", image_ref),
        cwd=repository_root,
        check=False,
    )
    if completed.returncode == 0:
        raise ReleaseError(
            f"Immutable registry tag already exists and cannot be replaced: {image_ref}"
        )
    detail = f"{completed.stdout}\n{completed.stderr}".lower()
    if any(
        marker in detail
        for marker in ("manifest unknown", "no such manifest", "not found")
    ):
        return
    if any(marker in detail for marker in ("unauthorized", "denied")):
        raise ReleaseError(
            f"Registry authentication is required to verify tag absence: {image_ref}"
        )
    raise ReleaseError(
        f"Unable to prove that immutable registry tag is absent: {image_ref}"
    )


def version_tuple(version: str) -> tuple[int, int, int]:
    """Convert strict semantic version text.

    Args:
        version: Version in ``x.y.z`` form.

    Returns:
        tuple[int, int, int]: Comparable major, minor, and patch values.

    Raises:
        ReleaseError: If the value is not strict semantic version text.
    """

    match = SEMVER_PATTERN.fullmatch(version)
    if not match:
        raise ReleaseError(f"Invalid strict SemVer value: {version!r}")
    return tuple(int(item) for item in match.groups())  # type: ignore[return-value]


def update_project_version(path: Path, current: str, target: str) -> None:
    """Replace only the selected app project version.

    Args:
        path: App-owned ``pyproject.toml``.
        current: Exact current semantic version.
        target: Exact greater semantic version.

    Side Effects:
        Rewrites the manifest while preserving unrelated content.

    Raises:
        ReleaseError: If the project table or exact version is missing.
        OSError: If the manifest cannot be read or written.
    """

    source = path.read_text(encoding="utf-8")
    section_match = re.search(r"(?ms)^\[project\]\s*$.*?(?=^\[|\Z)", source)
    if not section_match:
        raise ReleaseError(f"Missing [project] table in {path}")
    section = section_match.group(0)
    version_pattern = re.compile(
        rf'(?m)^version\s*=\s*"{re.escape(current)}"\s*$'
    )
    updated_section, count = version_pattern.subn(
        f'version = "{target}"',
        section,
        count=1,
    )
    if count != 1:
        raise ReleaseError(
            f"Unable to replace the exact project version {current!r} in {path}"
        )
    path.write_text(
        source[: section_match.start()]
        + updated_section
        + source[section_match.end() :],
        encoding="utf-8",
    )


def extract_push_digest(output: str) -> str | None:
    """Extract a registry-reported manifest digest.

    Args:
        output: Combined Docker push output.

    Returns:
        str | None: Last SHA-256 digest, or ``None`` when absent.
    """

    matches = re.findall(r"digest:\s*(sha256:[0-9a-f]{64})", output)
    return matches[-1] if matches else None
