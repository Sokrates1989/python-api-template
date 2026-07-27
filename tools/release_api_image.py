#!/usr/bin/env python3
"""Build and explicitly publish selected-app API images with safe evidence.

The module intentionally uses only the Python standard library. It never reads
or sources a general ``.env`` file: the selected app manifest, dependency lock,
Git revision, and explicit command-line arguments are the release inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from tools.release_image_evidence import (
        ImageEvidenceError,
        ImageEvidenceRequest,
        collect_image_evidence,
    )
except ModuleNotFoundError:
    from release_image_evidence import (  # type: ignore[no-redef]
        ImageEvidenceError,
        ImageEvidenceRequest,
        collect_image_evidence,
    )
try:
    from tools.release_command import CommandRunner, ReleaseError
    from tools.release_source_publication import (
        ensure_clean_worktree as _ensure_clean_worktree,
        ensure_immutable_tag_absent as _ensure_immutable_tag_absent,
        ensure_release_branch as _ensure_release_branch,
        extract_push_digest as _extract_push_digest,
        git_output as _git_output,
        update_project_version as _update_project_version,
        version_tuple as _version_tuple,
    )
except ModuleNotFoundError:
    from release_command import CommandRunner, ReleaseError  # type: ignore[no-redef]
    from release_source_publication import (  # type: ignore[no-redef]
        ensure_clean_worktree as _ensure_clean_worktree,
        ensure_immutable_tag_absent as _ensure_immutable_tag_absent,
        ensure_release_branch as _ensure_release_branch,
        extract_push_digest as _extract_push_digest,
        git_output as _git_output,
        update_project_version as _update_project_version,
        version_tuple as _version_tuple,
    )


DEFAULT_IMAGE_NAMESPACE = "sokrates1989"
DEFAULT_PDM_VERSION = "2.27.0"
DEFAULT_PLATFORM = "linux/amd64"
DEFAULT_PYTHON_VERSION = "3.13-slim"
SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
APP_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
IMAGE_NAME_PATTERN = re.compile(
    r"^(?:[a-z0-9.-]+(?::[0-9]+)?/)?"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$"
)
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class ReleasePlan:
    """Immutable inputs that identify one selected-app API image.

    Attributes:
        schema_version: Evidence schema version.
        app_id: Selected backend build app.
        app_profile: Bound runtime composition profile.
        image_name: Registry repository without tag.
        image_tag: Strict immutable semantic version.
        image_ref: Repository plus immutable tag.
        package_name: App manifest package name.
        package_version: App manifest package version.
        python_version: Selected Python base tag.
        pdm_version: Exact PDM build-tool version.
        platform: Required production image platform.
        git_revision: Full source commit hash.
        dependency_lock_path: Repository-relative selected lock.
        dependency_lock_sha256: Selected lock digest.
        dockerfile_path: Repository-relative Dockerfile.
        receipt_path: Ignored sanitized receipt path.
        sbom_path: Ignored full-image SPDX path.
        dependency_sbom_path: Ignored lock-derived SPDX path.
    """

    schema_version: int
    app_id: str
    app_profile: str
    image_name: str
    image_tag: str
    image_ref: str
    package_name: str
    package_version: str
    python_version: str
    pdm_version: str
    platform: str
    git_revision: str
    dependency_lock_path: str
    dependency_lock_sha256: str
    dockerfile_path: str
    receipt_path: str
    sbom_path: str
    dependency_sbom_path: str


def _utc_timestamp() -> str:
    """Return a stable UTC timestamp.

    Returns:
        str: Second-precision ISO-8601 value with UTC offset.
    """

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    """Hash one release input.

    Args:
        path: File to read in bounded chunks.

    Returns:
        str: Lowercase hexadecimal SHA-256 digest.

    Raises:
        OSError: If the file cannot be read.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_app_image_segment(app_id: str) -> str:
    """Convert an app id to its Docker repository segment.

    Args:
        app_id: Already validated selected backend app id.

    Returns:
        str: Lowercase segment with underscores replaced by hyphens.
    """

    return app_id.replace("_", "-")


def _read_project_manifest(path: Path) -> tuple[str, str]:
    """Read selected-app package identity.

    Args:
        path: App-owned ``pyproject.toml``.

    Returns:
        tuple[str, str]: Package name and strict semantic version.

    Raises:
        ReleaseError: If the manifest is missing, malformed, or incomplete.
    """

    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(f"Unable to read selected app manifest: {path}") from exc

    project = document.get("project")
    if not isinstance(project, dict):
        raise ReleaseError(f"Selected app manifest has no [project] table: {path}")
    package_name = str(project.get("name", "")).strip()
    package_version = str(project.get("version", "")).strip()
    if not package_name:
        raise ReleaseError(f"Selected app manifest has no project name: {path}")
    if not SEMVER_PATTERN.fullmatch(package_version):
        raise ReleaseError(
            f"Selected app version must be strict SemVer x.y.z: {package_version!r}"
        )
    return package_name, package_version


def create_release_plan(
    repository_root: Path,
    app_id: str,
    *,
    version: str | None = None,
    image_name: str | None = None,
    python_version: str = DEFAULT_PYTHON_VERSION,
    pdm_version: str = DEFAULT_PDM_VERSION,
    platform: str = DEFAULT_PLATFORM,
    runner: CommandRunner | None = None,
) -> ReleasePlan:
    """Validate selected-app release inputs.

    Args:
        repository_root: Canonical API repository.
        app_id: Explicit selected backend app.
        version: Optional tag that must equal the package version.
        image_name: Optional registry repository override.
        python_version: Python base image tag.
        pdm_version: Exact PDM build-tool version.
        platform: Required production platform.
        runner: Optional injectable command runner.

    Returns:
        ReleasePlan: Validated secret-free image plan.

    Side Effects:
        Reads manifest, lock, Dockerfile, and Git revision only.

    Raises:
        ReleaseError: If any selected-app, version, image, lock, or Git input
            is invalid.
    """

    runner = runner or CommandRunner()
    repository_root = repository_root.resolve()
    if not APP_ID_PATTERN.fullmatch(app_id):
        raise ReleaseError(f"Invalid selected backend app id: {app_id!r}")

    app_root = repository_root / "app" / "apps" / app_id
    manifest_path = app_root / "pyproject.toml"
    lock_path = app_root / "pdm.lock"
    dockerfile_path = repository_root / "Dockerfile"
    for required_path in (manifest_path, lock_path, dockerfile_path):
        if not required_path.is_file():
            raise ReleaseError(f"Missing required release input: {required_path}")

    package_name, package_version = _read_project_manifest(manifest_path)
    selected_version = version or package_version
    if not SEMVER_PATTERN.fullmatch(selected_version):
        raise ReleaseError(
            f"Image tag must be strict immutable SemVer x.y.z: {selected_version!r}"
        )
    if selected_version != package_version:
        raise ReleaseError(
            "Selected image version must equal the committed app package version "
            f"({package_version}); update the package version before building."
        )

    canonical_image_name = (
        image_name
        or f"{DEFAULT_IMAGE_NAMESPACE}/python-api-{_normalize_app_image_segment(app_id)}"
    )
    if not IMAGE_NAME_PATTERN.fullmatch(canonical_image_name):
        raise ReleaseError(f"Invalid Docker image repository: {canonical_image_name!r}")
    if ":" in canonical_image_name.rsplit("/", 1)[-1]:
        raise ReleaseError("Image repository must not include a mutable or embedded tag.")
    if not python_version or any(character.isspace() for character in python_version):
        raise ReleaseError("Python image version must be a non-empty token.")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", pdm_version):
        raise ReleaseError("PDM_VERSION must be pinned to an exact x.y.z version.")
    if platform != DEFAULT_PLATFORM:
        raise ReleaseError(f"Production platform must be {DEFAULT_PLATFORM}.")

    revision = _git_output(runner, repository_root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ReleaseError("Unable to resolve the full Git source revision.")

    lock_sha256 = _sha256_file(lock_path)
    evidence_root = (
        repository_root / "build" / "release-evidence" / "api" / app_id
    )
    image_ref = f"{canonical_image_name}:{selected_version}"
    return ReleasePlan(
        schema_version=1,
        app_id=app_id,
        app_profile=app_id,
        image_name=canonical_image_name,
        image_tag=selected_version,
        image_ref=image_ref,
        package_name=package_name,
        package_version=package_version,
        python_version=python_version,
        pdm_version=pdm_version,
        platform=platform,
        git_revision=revision,
        dependency_lock_path=lock_path.relative_to(repository_root).as_posix(),
        dependency_lock_sha256=lock_sha256,
        dockerfile_path=dockerfile_path.relative_to(repository_root).as_posix(),
        receipt_path=(
            evidence_root / f"{selected_version}.receipt.json"
        ).relative_to(repository_root).as_posix(),
        sbom_path=(
            evidence_root / f"{selected_version}.image.spdx.json"
        ).relative_to(repository_root).as_posix(),
        dependency_sbom_path=(
            evidence_root / f"{selected_version}.dependencies.spdx.json"
        ).relative_to(repository_root).as_posix(),
    )


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    """Write formatted JSON through a sibling temporary file.

    Args:
        path: Final ignored evidence path.
        value: JSON-serializable document.

    Side Effects:
        Creates parent directories and atomically replaces ``path``.

    Raises:
        OSError: If temporary or final evidence cannot be written.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def _docker_build_command(plan: ReleasePlan) -> tuple[str, ...]:
    """Construct the exact buildx argument vector.

    Args:
        plan: Validated release inputs.

    Returns:
        tuple[str, ...]: Shell-free production image build command.
    """

    return (
        "docker",
        "buildx",
        "build",
        "--platform",
        plan.platform,
        "--load",
        "--tag",
        plan.image_ref,
        "--file",
        plan.dockerfile_path,
        "--build-arg",
        f"PYTHON_VERSION={plan.python_version}",
        "--build-arg",
        f"PDM_VERSION={plan.pdm_version}",
        "--build-arg",
        f"IMAGE_TAG={plan.image_tag}",
        "--build-arg",
        f"BACKEND_APP_ID={plan.app_id}",
        "--build-arg",
        f"APP_PROFILE={plan.app_profile}",
        "--build-arg",
        f"SOURCE_REVISION={plan.git_revision}",
        "--build-arg",
        f"DEPENDENCY_LOCK_SHA256={plan.dependency_lock_sha256}",
        ".",
    )


def _inspect_image(
    repository_root: Path,
    plan: ReleasePlan,
    runner: CommandRunner,
) -> dict[str, Any]:
    """Inspect selected-app image metadata.

    Args:
        repository_root: Docker command working directory.
        plan: Expected image identity and labels.
        runner: Injectable command runner.

    Returns:
        dict[str, Any]: Sanitized image ID, user, labels, and health state.

    Side Effects:
        Executes a read-only Docker image inspection.

    Raises:
        ReleaseError: If inspection is malformed or identity, user, labels,
            runtime bindings, or healthcheck differ from the plan.
    """

    completed = runner.run(
        ("docker", "image", "inspect", plan.image_ref),
        cwd=repository_root,
    )
    try:
        raw = json.loads(completed.stdout)
        image = raw[0]
        config = image["Config"]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
        raise ReleaseError("Docker image inspection returned malformed JSON.") from exc

    user = str(config.get("User", "")).strip()
    if user in {"", "0", "root", "0:0", "root:root"}:
        raise ReleaseError("Production image must declare a non-root runtime user.")

    labels = config.get("Labels") or {}
    expected_labels = {
        "org.opencontainers.image.revision": plan.git_revision,
        "org.opencontainers.image.version": plan.image_tag,
        "com.fe-wi.backend-app-id": plan.app_id,
        "com.fe-wi.app-profile": plan.app_profile,
        "com.fe-wi.dependency-lock-sha256": plan.dependency_lock_sha256,
    }
    for key, expected_value in expected_labels.items():
        if labels.get(key) != expected_value:
            raise ReleaseError(
                f"Image label {key} does not match the release plan."
            )

    environment = set(config.get("Env") or [])
    for expected_value in (
        f"BACKEND_APP_ID={plan.app_id}",
        f"APP_PROFILE={plan.app_profile}",
    ):
        if expected_value not in environment:
            raise ReleaseError(f"Image is missing runtime binding {expected_value}.")
    if not config.get("Healthcheck"):
        raise ReleaseError("Production image must declare a container healthcheck.")

    image_id = str(image.get("Id", ""))
    if not SHA256_PATTERN.fullmatch(image_id):
        raise ReleaseError("Docker inspection did not return an immutable image ID.")
    return {
        "imageId": image_id,
        "runtimeUser": user,
        "labels": expected_labels,
        "healthcheckDeclared": True,
    }


def build_release_image(
    repository_root: Path,
    plan: ReleasePlan,
    *,
    runner: CommandRunner | None = None,
    scanner: str = "auto",
) -> dict[str, Any]:
    """Build and prove one local selected-app image.

    Args:
        repository_root: Canonical API repository.
        plan: Validated release inputs.
        runner: Optional injectable command runner.
        scanner: ``auto``, ``trivy``, or ``docker-scout``.

    Returns:
        dict[str, Any]: Sanitized local build receipt.

    Side Effects:
        Builds a local Docker image and writes ignored SPDX/receipt artifacts.

    Raises:
        ReleaseError: If the tree is dirty or any build, inspect, SBOM, or
            vulnerability gate fails.
    """

    runner = runner or CommandRunner()
    _ensure_clean_worktree(repository_root, runner)
    runner.run(("docker", "buildx", "version"), cwd=repository_root)
    runner.run(_docker_build_command(plan), cwd=repository_root)
    inspection = _inspect_image(repository_root, plan, runner)
    evidence_request = ImageEvidenceRequest(
        app_id=plan.app_id,
        package_name=plan.package_name,
        package_version=plan.package_version,
        git_revision=plan.git_revision,
        image_ref=plan.image_ref,
        dependency_lock_path=repository_root / plan.dependency_lock_path,
        dependency_lock_sha256=plan.dependency_lock_sha256,
        image_sbom_path=repository_root / plan.sbom_path,
        dependency_sbom_path=repository_root / plan.dependency_sbom_path,
    )
    try:
        evidence = collect_image_evidence(
            repository_root,
            evidence_request,
            runner,
            scanner,
        )
    except ImageEvidenceError as exc:
        raise ReleaseError(str(exc)) from exc
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "api-image-release-evidence",
        "createdAt": _utc_timestamp(),
        "state": "built",
        "deploymentAuthorized": False,
        "plan": asdict(plan),
        "image": inspection,
        **evidence,
        "publication": {
            "immutableTagPushed": False,
            "immutableDigest": None,
            "latestConvenienceTagPushed": False,
            "latestAllowedForDeployment": False,
        },
    }
    _write_json_atomic(repository_root / plan.receipt_path, receipt)
    return receipt


def publish_release_image(
    repository_root: Path,
    app_id: str,
    target_version: str,
    *,
    image_name: str | None = None,
    python_version: str = DEFAULT_PYTHON_VERSION,
    pdm_version: str = DEFAULT_PDM_VERSION,
    scanner: str = "auto",
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Prove and publish a greater selected-app version.

    Args:
        repository_root: Canonical API repository.
        app_id: Explicit selected backend app.
        target_version: Greater strict semantic version.
        image_name: Optional registry repository override.
        python_version: Python base image tag.
        pdm_version: Exact PDM build-tool version.
        scanner: Image SBOM and vulnerability scanner.
        runner: Optional injectable command runner.

    Returns:
        dict[str, Any]: Receipt bound to the immutable registry digest.

    Side Effects:
        Updates and commits the app version, builds/scans the image, pushes the
        source commit, and pushes immutable plus ``latest`` image tags. It never
        deploys.

    Raises:
        ReleaseError: If preflight, commit, build evidence, Git push, immutable
            image push, digest extraction, or convenience-tag push fails.
    """

    runner = runner or CommandRunner()
    repository_root = repository_root.resolve()
    _ensure_clean_worktree(repository_root, runner)
    _ensure_release_branch(repository_root, runner)
    manifest_path = repository_root / "app" / "apps" / app_id / "pyproject.toml"
    manifest_argument = manifest_path.relative_to(repository_root).as_posix()
    _, current_version = _read_project_manifest(manifest_path)
    if _version_tuple(target_version) <= _version_tuple(current_version):
        raise ReleaseError(
            "Build & Push requires a version greater than the current app version "
            f"({current_version})."
        )

    target_image_name = (
        image_name
        or f"{DEFAULT_IMAGE_NAMESPACE}/python-api-{_normalize_app_image_segment(app_id)}"
    )
    _ensure_immutable_tag_absent(
        repository_root,
        f"{target_image_name}:{target_version}",
        runner,
    )

    _update_project_version(manifest_path, current_version, target_version)
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

    plan = create_release_plan(
        repository_root,
        app_id,
        version=target_version,
        image_name=image_name,
        python_version=python_version,
        pdm_version=pdm_version,
        runner=runner,
    )
    receipt = build_release_image(
        repository_root,
        plan,
        runner=runner,
        scanner=scanner,
    )

    # The local release commit is now proven by the build/inspect/SBOM/scan
    # gates. Push source before publishing the image that names its revision.
    runner.run(("git", "push"), cwd=repository_root)

    immutable_push = runner.run(
        ("docker", "push", plan.image_ref),
        cwd=repository_root,
    )
    immutable_digest = _extract_push_digest(
        f"{immutable_push.stdout}\n{immutable_push.stderr}"
    )
    if immutable_digest is None:
        raise ReleaseError(
            "Immutable image push succeeded without a registry digest; "
            "deployment evidence cannot be bound."
        )

    publication = receipt["publication"]
    publication["immutableTagPushed"] = True
    publication["immutableDigest"] = immutable_digest
    receipt["state"] = "immutable-pushed"
    _write_json_atomic(repository_root / plan.receipt_path, receipt)

    latest_ref = f"{plan.image_name}:latest"
    runner.run(("docker", "tag", plan.image_ref, latest_ref), cwd=repository_root)
    runner.run(("docker", "push", latest_ref), cwd=repository_root)
    publication["latestConvenienceTagPushed"] = True
    publication["latestAllowedForDeployment"] = False
    receipt["state"] = "published"
    receipt["publishedAt"] = _utc_timestamp()
    _write_json_atomic(repository_root / plan.receipt_path, receipt)
    return receipt


def _print_plan(plan: ReleasePlan, action: str) -> None:
    """Print a concise secret-free preview.

    Args:
        plan: Validated release identity.
        action: Human-readable action label.

    Side Effects:
        Writes public plan fields to standard output.
    """

    print("API image release plan")
    print("======================")
    print(f"Action:          {action}")
    print(f"Selected app:    {plan.app_id}")
    print(f"Runtime profile: {plan.app_profile}")
    print(f"Image:           {plan.image_ref}")
    print(f"Platform:        {plan.platform}")
    print(f"Git revision:    {plan.git_revision}")
    print(f"Dependency lock: sha256:{plan.dependency_lock_sha256}")
    print(f"PDM:             {plan.pdm_version} (pinned)")
    print(f"Receipt:         {plan.receipt_path}")
    print(f"Image SBOM:      {plan.sbom_path}")
    print(f"Lock SBOM:       {plan.dependency_sbom_path}")
    print("Deployment:      not authorized")


def _build_parser() -> argparse.ArgumentParser:
    """Create the release command-line parser.

    Returns:
        argparse.ArgumentParser: Parser for plan, build, and publish actions.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        """Add shared selected-app image arguments.

        Args:
            subparser: Action parser to extend.

        Side Effects:
            Mutates the parser's accepted argument schema.
        """

        subparser.add_argument("--app", required=True)
        subparser.add_argument("--image-name")
        subparser.add_argument("--python-version", default=DEFAULT_PYTHON_VERSION)
        subparser.add_argument("--pdm-version", default=DEFAULT_PDM_VERSION)

    plan_parser = subparsers.add_parser("plan", help="Validate and preview only.")
    add_common(plan_parser)
    plan_parser.add_argument("--json", action="store_true")

    build_parser = subparsers.add_parser(
        "build",
        help="Build, inspect, scan, and receipt locally without pushing.",
    )
    add_common(build_parser)
    build_parser.add_argument(
        "--scanner",
        choices=("auto", "trivy", "docker-scout"),
        default="auto",
    )

    publish_parser = subparsers.add_parser(
        "publish",
        help="Commit/push a version bump, then push immutable and latest images.",
    )
    add_common(publish_parser)
    publish_parser.add_argument("--version", required=True)
    publish_parser.add_argument(
        "--scanner",
        choices=("auto", "trivy", "docker-scout"),
        default="auto",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected-app image release CLI.

    Args:
        argv: Optional explicit arguments; defaults to process arguments.

    Returns:
        int: Zero on success and one for a safely reported release failure.

    Side Effects:
        Depending on the selected action, prints a plan, builds local evidence,
        or performs the explicitly confirmed Git and registry publication flow.
    """

    arguments = _build_parser().parse_args(argv)
    repository_root = arguments.repository_root.resolve()
    try:
        if arguments.action == "publish":
            print("Build & Push performs these explicit external effects:")
            print("  1. Commit the selected app version bump locally")
            print("  2. Build, inspect, inventory, and vulnerability-scan the image")
            print("  3. Push the proven source commit")
            print("  4. Push the immutable version tag and latest convenience tag")
            print("  5. Never deploy an image or authorize latest for deployment")
            receipt = publish_release_image(
                repository_root,
                arguments.app,
                arguments.version,
                image_name=arguments.image_name,
                python_version=arguments.python_version,
                pdm_version=arguments.pdm_version,
                scanner=arguments.scanner,
            )
            plan = ReleasePlan(**receipt["plan"])
            _print_plan(plan, "published")
            print(
                "Immutable digest: "
                f"{receipt['publication']['immutableDigest']}"
            )
            return 0

        plan = create_release_plan(
            repository_root,
            arguments.app,
            image_name=arguments.image_name,
            python_version=arguments.python_version,
            pdm_version=arguments.pdm_version,
        )
        if arguments.action == "plan":
            if arguments.json:
                print(json.dumps(asdict(plan), indent=2, sort_keys=True))
            else:
                _print_plan(plan, "plan only")
            return 0

        _print_plan(plan, "local build only")
        receipt = build_release_image(
            repository_root,
            plan,
            scanner=arguments.scanner,
        )
        print(f"Built exact image ID: {receipt['image']['imageId']}")
        print(f"Evidence written: {plan.receipt_path}")
        print("No registry push or deployment was performed.")
        return 0
    except ReleaseError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
