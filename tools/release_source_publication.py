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


def validate_version_transition(
    current_version: str,
    target_version: str,
    *,
    allow_current_version: bool,
) -> bool:
    """Validate a publication version and identify exact-current reuse.

    Args:
        current_version: Version currently committed in the selected manifest.
        target_version: Operator-selected publication version.
        allow_current_version: Whether exact current-version reuse was
            explicitly selected by the quick-start menu.

    Returns:
        bool: ``True`` when the current version should be published without a
        version-file change; ``False`` for a greater-version release.

    Raises:
        ReleaseError: If the target is older, or equals the current version
            without explicit current-version authorization.
    """

    current = version_tuple(current_version)
    target = version_tuple(target_version)
    if target < current:
        raise ReleaseError(
            "Build & Push cannot publish a version older than the current app "
            f"version ({current_version})."
        )
    if target == current and not allow_current_version:
        raise ReleaseError(
            "Build & Push requires a version greater than the current app "
            f"version ({current_version}) unless current-version publication "
            "is explicitly selected."
        )
    return target == current


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


def prepare_release_source(
    repository_root: Path,
    manifest_path: Path,
    app_id: str,
    current_version: str,
    target_version: str,
    *,
    reuse_current_version: bool,
    runner: PublicationCommandRunner,
) -> None:
    """Keep current source or create the selected version-bump commit.

    Args:
        repository_root: Canonical API repository.
        manifest_path: Selected app's committed package manifest.
        app_id: Selected backend app identifier.
        current_version: Exact manifest version before publication.
        target_version: Validated publication version.
        reuse_current_version: Whether to leave the manifest and HEAD intact.
        runner: Shell-free command runner.

    Returns:
        None.

    Side Effects:
        For a greater version, rewrites, stages, and commits only the selected
        app manifest. Current-version publication has no source mutation.

    Raises:
        ReleaseError: Through manifest validation or command failures.
    """

    if reuse_current_version:
        return

    manifest_argument = manifest_path.relative_to(repository_root).as_posix()
    update_project_version(manifest_path, current_version, target_version)
    runner.run(
        ("git", "diff", "--check", "--", manifest_argument),
        cwd=repository_root,
    )
    runner.run(("git", "add", "--", manifest_argument), cwd=repository_root)
    runner.run(
        (
            "git",
            "commit",
            "-m",
            f"[Release] {app_id} API {target_version}",
        ),
        cwd=repository_root,
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
