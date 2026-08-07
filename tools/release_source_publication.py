"""Git versioning helpers for API image publication."""

from __future__ import annotations

import re
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol, Sequence

try:
    from tools.release_command import ReleaseError
except ModuleNotFoundError:
    from release_command import ReleaseError  # type: ignore[no-redef]


SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)


@dataclass(frozen=True)
class ReleaseWorktreeState:
    """Describe dirty unrelated paths allowed during one app release.

    Attributes:
        unrelated_paths: Repository-relative dirty paths outside the selected
            app, shared image inputs, and release machinery. These paths are
            deliberately excluded by building from the recorded Git revision.
    """

    unrelated_paths: tuple[str, ...]


class PublicationCommandRunner(Protocol):
    """Command behavior required by local source versioning safeguards."""

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


def _parse_porcelain_paths(status: str) -> tuple[str, ...]:
    """Extract repository-relative paths from NUL-safe Git status output.

    Args:
        status: Output from ``git status --porcelain=v1 -z --no-renames``.

    Returns:
        tuple[str, ...]: Dirty paths in Git's repository-relative form.

    Raises:
        ReleaseError: If Git returns a malformed porcelain record.
    """

    if not status:
        return ()
    records = status.split("\0") if "\0" in status else status.splitlines()
    paths: list[str] = []
    for record in records:
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            raise ReleaseError(
                "Git returned malformed worktree status while validating the "
                "selected-app release source."
            )
        paths.append(record[3:])
    return tuple(paths)


def _is_release_input_path(path: str, selected_app_id: str) -> bool:
    """Identify selected-app, shared-image, or release-tool source.

    Args:
        path: Git repository-relative dirty path.
        selected_app_id: Backend app currently being released.

    Returns:
        bool: ``True`` when the path can affect the selected image or the
        mechanism that validates and publishes it.
    """

    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if len(parts) >= 4 and parts[0:2] == ["app", "apps"]:
        return parts[2] == selected_app_id
    if normalized.startswith("app/"):
        return True
    if normalized == "alembic.ini" or normalized.startswith("alembic/"):
        return True
    if normalized in {"Dockerfile", ".dockerignore"}:
        return True
    if normalized.startswith("tools/release_"):
        return True
    if normalized == "tools/api_release_stack.py":
        return True
    return normalized in {
        "quick-start.sh",
        "quick-start.ps1",
        "setup/modules/menu_handlers.sh",
    }


def validate_release_worktree(
    repository_root: Path,
    selected_app_id: str,
    runner: PublicationCommandRunner,
) -> ReleaseWorktreeState:
    """Require committed selected-app and shared source for publication.

    Args:
        repository_root: Git working tree.
        selected_app_id: Backend app selected for the image release.
        runner: Injectable command runner.

    Returns:
        ReleaseWorktreeState: Allowed unrelated dirt that requires an
        isolated committed build context.

    Side Effects:
        Executes a read-only Git status query.

    Raises:
        ReleaseError: If selected-app or shared paths have tracked, staged, or
            untracked changes.
    """

    completed = runner.run(
        (
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--no-renames",
        ),
        cwd=repository_root,
    )
    dirty_paths = _parse_porcelain_paths(completed.stdout)
    blocking_paths = tuple(
        path
        for path in dirty_paths
        if _is_release_input_path(path, selected_app_id)
    )
    unrelated_paths = tuple(
        path for path in dirty_paths if path not in blocking_paths
    )
    if blocking_paths:
        rendered_paths = ", ".join(blocking_paths[:8])
        if len(blocking_paths) > 8:
            rendered_paths += f", ... (+{len(blocking_paths) - 8} more)"
        raise ReleaseError(
            "Build & Push requires committed selected-app and shared release "
            f"source. Commit or stash these blocking paths: {rendered_paths}. "
            "Dirty unrelated paths are allowed and excluded by building from "
            "committed HEAD instead."
        )
    return ReleaseWorktreeState(unrelated_paths=unrelated_paths)


@contextmanager
def committed_release_context(
    repository_root: Path,
    revision: str,
    worktree_state: ReleaseWorktreeState,
    runner: PublicationCommandRunner,
) -> Iterator[Path]:
    """Yield a Docker context that cannot contain dirty unrelated source.

    A clean release scope can be used directly. When unrelated work is present, this
    helper creates a temporary detached Git worktree at the release plan's
    exact revision so Docker cannot copy those uncommitted changes.

    Args:
        repository_root: Canonical API Git working tree.
        revision: Exact full Git revision recorded by the release plan.
        worktree_state: Result of selected-app worktree validation.
        runner: Injectable command runner.

    Yields:
        Path: Canonical or temporary committed Docker build context.

    Side Effects:
        May add and remove a temporary detached Git worktree.

    Raises:
        ReleaseError: Through the runner if temporary worktree creation or
            cleanup fails.
    """

    if not worktree_state.unrelated_paths:
        yield repository_root
        return

    with tempfile.TemporaryDirectory(prefix="api-release-context-") as parent:
        build_context = Path(parent) / "source"
        runner.run(
            (
                "git",
                "worktree",
                "add",
                "--detach",
                str(build_context),
                revision,
            ),
            cwd=repository_root,
        )
        try:
            yield build_context
        finally:
            runner.run(
                (
                    "git",
                    "worktree",
                    "remove",
                    "--force",
                    str(build_context),
                ),
                cwd=repository_root,
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
            "--only",
            "-m",
            f"[Release] {app_id} API {target_version}",
            "--",
            manifest_argument,
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
