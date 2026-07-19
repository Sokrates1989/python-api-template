"""Read, validate, and plan Python-owned Template V2 backend lifecycle state.

Planning is repository-read-only. Desired bytes come from an isolated bundle
directory, while current generated, detached, and unowned state is classified
through the target ownership manifest. Every returned plan is content-free and
binds exact current state so stale write attempts fail closed.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .backend_foundation_contract import BackendFoundationIdentity, validate_backend_foundation
from .backend_lifecycle_models import (
    OWNERSHIP_RELATIVE_PATH,
    BackendLifecycleError,
    BackendLifecyclePlan,
    LifecycleChange,
    LifecycleFile,
)


_APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ROUTE_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put"})
_MAX_FILE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class BundleFile:
    """Hold one validated desired/current file for internal transactions.

    Attributes:
        relative_path: Portable target-relative path.
        content: Exact file bytes retained only inside the local process.
    """

    relative_path: str
    content: bytes

    @property
    def metadata(self) -> LifecycleFile:
        """Return content-free metadata for this file.

        Returns:
            Generated file path, size, and digest metadata.
        """

        return LifecycleFile(
            relative_path=self.relative_path,
            byte_count=len(self.content),
            sha256=hashlib.sha256(self.content).hexdigest(),
        )


@dataclass(frozen=True)
class BackendLifecycleContext:
    """Contain validated desired and current backend lifecycle state.

    Attributes:
        template_root: Python API template root owning the lifecycle contract.
        repository_root: Explicit backend publication repository.
        target_directory: Portable generated backend target path.
        target_path: Resolved target path below the repository.
        app_id: Backend application identifier derived from the target.
        registration_relative_path: Owned root registration file path.
        registration_path: Resolved root registration file path.
        foundation_identity: Validated B1 compatibility identity.
        desired_files: Complete desired target bytes including ownership.
        desired_ownership: Parsed desired ownership mapping.
        desired_bundle_sha256: Desired complete bundle digest.
        current_files: Complete existing target bytes, or empty when absent.
        current_ownership: Parsed existing ownership mapping, or ``None``.
        current_bundle_sha256: Current complete bundle digest, or ``None``.
        registration: Parsed existing root registration, or ``None``.
    """

    template_root: Path
    repository_root: Path
    target_directory: str
    target_path: Path
    app_id: str
    registration_relative_path: str
    registration_path: Path
    foundation_identity: BackendFoundationIdentity
    desired_files: tuple[BundleFile, ...]
    desired_ownership: dict[str, Any]
    desired_bundle_sha256: str
    current_files: tuple[BundleFile, ...]
    current_ownership: dict[str, Any] | None
    current_bundle_sha256: str | None
    registration: dict[str, Any] | None


def _validate_relative_path(value: str, label: str) -> str:
    """Validate and normalize one portable repository-relative path.

    Args:
        value: Candidate forward-slash relative path.
        label: Diagnostic field name.

    Returns:
        Unchanged validated portable path.

    Raises:
        BackendLifecycleError: If the path is unsafe.
    """

    path = PurePosixPath(value)
    invalid = (
        not value
        or value != value.strip()
        or path.is_absolute()
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", "..", ".git", ".hg", ".svn"} for part in path.parts)
        or path.as_posix() != value
    )
    if invalid:
        raise BackendLifecycleError([f"{label}: expected a safe portable relative path"])
    return value


def _read_tree(root: Path, label: str) -> tuple[BundleFile, ...]:
    """Read one regular bounded tree into stable internal bundle files.

    Args:
        root: Existing tree root.
        label: Diagnostic owner such as desired or current bundle.

    Returns:
        Path-sorted file bytes.

    Raises:
        BackendLifecycleError: If the tree contains unsafe or unreadable state.
    """

    if root.is_symlink() or not root.is_dir():
        raise BackendLifecycleError([f"{label}: expected a regular directory"])
    files: list[BundleFile] = []
    issues: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative_path = path.relative_to(root).as_posix()
        if path.is_symlink():
            issues.append(f"{label}: symbolic link is forbidden at {relative_path}")
        elif path.is_file():
            try:
                content = path.read_bytes()
            except OSError:
                issues.append(f"{label}: unreadable file at {relative_path}")
                continue
            if len(content) > _MAX_FILE_BYTES:
                issues.append(f"{label}: file exceeds bounded size at {relative_path}")
            else:
                files.append(BundleFile(_validate_relative_path(relative_path, label), content))
        elif not path.is_dir():
            issues.append(f"{label}: unsupported filesystem entry at {relative_path}")
    if issues or not files:
        raise BackendLifecycleError(issues or [f"{label}: at least one file is required"])
    return tuple(files)


def _bundle_sha256(files: tuple[BundleFile, ...]) -> str:
    """Calculate the shared path-and-content backend bundle identity.

    Args:
        files: Stable path-sorted complete target files.

    Returns:
        Lowercase SHA-256 matching the Flutter generation transaction.
    """

    digest = hashlib.sha256()
    for item in sorted(files, key=lambda value: value.relative_path):
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(item.content).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _parse_json_file(files: tuple[BundleFile, ...], relative_path: str, label: str) -> dict[str, Any]:
    """Parse one required UTF-8 JSON file from an internal bundle.

    Args:
        files: Complete bundle files.
        relative_path: Required JSON path.
        label: Diagnostic object name.

    Returns:
        Parsed JSON object.

    Raises:
        BackendLifecycleError: If the file is absent or malformed.
    """

    item = next((candidate for candidate in files if candidate.relative_path == relative_path), None)
    try:
        document = json.loads(item.content.decode("utf-8")) if item is not None else None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackendLifecycleError([f"{label}: expected valid UTF-8 JSON"]) from error
    if not isinstance(document, dict):
        raise BackendLifecycleError([f"{label}: expected a JSON object"])
    return document


def _ownership_files(document: dict[str, Any], label: str) -> tuple[LifecycleFile, ...]:
    """Validate and return ownership records from a generated manifest.

    Args:
        document: Parsed ownership manifest.
        label: Diagnostic manifest owner.

    Returns:
        Canonically ordered ownership records.

    Raises:
        BackendLifecycleError: If versions or records are unsupported.
    """

    versions = (
        document.get("generator_version"),
        document.get("ownership_schema_version"),
        document.get("blueprint_schema_version"),
        document.get("transaction_schema_version"),
    )
    if versions != (1, 1, 1, 1) or not isinstance(document.get("files"), list):
        raise BackendLifecycleError([f"{label}: unsupported ownership contract"])
    records: list[LifecycleFile] = []
    issues: list[str] = []
    for index, raw in enumerate(document["files"]):
        if not isinstance(raw, dict):
            issues.append(f"{label}.files[{index}]: expected an object")
            continue
        path = raw.get("path")
        digest = raw.get("sha256")
        byte_count = raw.get("bytes")
        classification = raw.get("classification")
        detached = raw.get("detached")
        try:
            normalized_path = _validate_relative_path(path, label) if isinstance(path, str) else ""
        except BackendLifecycleError as error:
            issues.extend(error.issues)
            continue
        valid = (
            isinstance(byte_count, int)
            and byte_count >= 0
            and isinstance(digest, str)
            and _SHA256_PATTERN.fullmatch(digest)
            and classification in {"generated", "handwritten"}
            and isinstance(detached, bool)
            and ((classification == "handwritten") == detached)
        )
        if not valid:
            issues.append(f"{label}.files[{index}]: invalid ownership record")
            continue
        records.append(LifecycleFile(normalized_path, byte_count, digest, classification, detached))
    paths = [item.relative_path for item in records]
    if paths != sorted(paths, key=str.casefold) or len(set(path.casefold() for path in paths)) != len(paths):
        issues.append(f"{label}.files: paths must be unique and sorted")
    if issues:
        raise BackendLifecycleError(issues)
    return tuple(records)


def _desired_ownership_issues(files: tuple[BundleFile, ...], document: dict[str, Any]) -> list[str]:
    """Return completeness and byte-parity issues for desired ownership.

    Args:
        files: Complete desired bundle files.
        document: Parsed desired ownership manifest.

    Returns:
        Stable desired ownership diagnostics.
    """

    records = _ownership_files(document, "desired ownership")
    actual = {item.relative_path: item.metadata for item in files if item.relative_path != OWNERSHIP_RELATIVE_PATH}
    expected = {item.relative_path: item for item in records}
    issues: list[str] = []
    if set(actual) != set(expected):
        issues.append("desired ownership: manifest must own every non-manifest file")
    for path in sorted(set(actual) & set(expected)):
        if actual[path].byte_count != expected[path].byte_count or actual[path].sha256 != expected[path].sha256:
            issues.append(f"desired ownership: generated bytes drifted at {path}")
        if expected[path].classification != "generated" or expected[path].detached:
            issues.append(f"desired ownership: detached source is forbidden at {path}")
    return issues


def _literal_string(call: ast.Call, keyword: str, positional: int | None = None) -> str | None:
    """Return one literal route value from a Python call expression.

    Args:
        call: AST call expression.
        keyword: Preferred keyword name.
        positional: Optional positional fallback index.

    Returns:
        Literal string, or ``None`` for dynamic or absent values.
    """

    for item in call.keywords:
        if item.arg == keyword and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            return item.value.value
    if positional is not None and len(call.args) > positional:
        value = call.args[positional]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _route_issues(files: tuple[BundleFile, ...]) -> list[str]:
    """Return forbidden literal ``/api`` route-prefix diagnostics.

    Args:
        files: Complete desired bundle files.

    Returns:
        Stable route and Python syntax diagnostics.
    """

    issues: list[str] = []
    for item in files:
        if not item.relative_path.endswith(".py"):
            continue
        try:
            tree = ast.parse(item.content.decode("utf-8-sig"), filename=item.relative_path)
        except (UnicodeDecodeError, SyntaxError):
            issues.append(f"desired bundle: invalid Python source at {item.relative_path}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            value = None
            if name in {"APIRouter", "include_router"}:
                value = _literal_string(node, "prefix")
            elif name in _ROUTE_METHODS:
                value = _literal_string(node, "path", 0)
            elif name == "RouteRegistration":
                value = _literal_string(node, "external_prefix")
            if value == "/api" or (isinstance(value, str) and value.startswith("/api/")):
                issues.append(f"desired bundle: forbidden /api prefix at {item.relative_path}")
                break
    return issues


def _validate_foundation_identity(files: tuple[BundleFile, ...], identity: BackendFoundationIdentity) -> None:
    """Verify the generated target records the validated B1 identity.

    Args:
        files: Complete desired target files.
        identity: Current validated Python foundation identity.

    Returns:
        None when exact identities match.

    Raises:
        BackendLifecycleError: If the target identity is absent or stale.
    """

    document = _parse_json_file(files, ".template_v2/backend_foundation.json", "foundation identity")
    expected = {
        "contract_id": identity.contract_id,
        "contract_version": identity.contract_version,
        "foundation_revision": identity.foundation_revision,
        "manifest_sha256": identity.manifest_sha256,
        "source_file_count": identity.source_file_count,
        "source_sha256": identity.source_sha256,
    }
    if document != expected:
        raise BackendLifecycleError(["foundation identity: desired bundle is incompatible"])


def _registration_path(repository_root: Path, app_id: str) -> tuple[str, Path]:
    """Return the owned per-app root registration path.

    Args:
        repository_root: Resolved backend publication repository.
        app_id: Validated backend app identifier.

    Returns:
        Portable relative path and resolved absolute path.
    """

    relative_path = f".template_v2/apps/{app_id}.json"
    return relative_path, repository_root.joinpath(*relative_path.split("/"))


def _read_registration(path: Path) -> dict[str, Any] | None:
    """Read one optional regular root registration JSON document.

    Args:
        path: Expected per-app registration path.

    Returns:
        Parsed registration, or ``None`` when absent.

    Raises:
        BackendLifecycleError: If existing registration state is unsafe.
    """

    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise BackendLifecycleError(["backend registration: expected a regular file"])
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackendLifecycleError(["backend registration: expected valid UTF-8 JSON"]) from error
    if not isinstance(document, dict):
        raise BackendLifecycleError(["backend registration: expected an object"])
    return document


def load_backend_lifecycle_context(
    template_root: Path,
    repository_root: Path,
    bundle_root: Path,
    target_directory: str,
) -> BackendLifecycleContext:
    """Load and validate desired, current, foundation, and registration state.

    Args:
        template_root: Python API template root owning B1/B2 tooling.
        repository_root: Explicit backend publication repository.
        bundle_root: Isolated desired complete target tree.
        target_directory: Exact portable backend target path.

    Returns:
        Complete validated lifecycle context.

    Raises:
        BackendLifecycleError: If any source or repository state is unsafe.
    """

    resolved_template = template_root.resolve()
    resolved_repository = repository_root.resolve()
    if not resolved_repository.is_dir() or resolved_repository.is_symlink():
        raise BackendLifecycleError(["repository_root: expected a regular directory"])
    normalized_target = _validate_relative_path(target_directory, "target_directory")
    target_parts = PurePosixPath(normalized_target).parts
    if len(target_parts) != 3 or target_parts[:2] != ("app", "apps") or not _APP_ID_PATTERN.fullmatch(target_parts[2]):
        raise BackendLifecycleError(["target_directory: expected app/apps/<app_id>"])
    app_id = target_parts[2]
    identity = validate_backend_foundation(resolved_template)
    desired_files = _read_tree(bundle_root, "desired bundle")
    desired_ownership = _parse_json_file(desired_files, OWNERSHIP_RELATIVE_PATH, "desired ownership")
    issues = [*_desired_ownership_issues(desired_files, desired_ownership), *_route_issues(desired_files)]
    if issues:
        raise BackendLifecycleError(issues)
    _validate_foundation_identity(desired_files, identity)
    target_path = resolved_repository.joinpath(*target_parts)
    current_files = _read_tree(target_path, "current target") if target_path.exists() else ()
    current_ownership = _parse_json_file(current_files, OWNERSHIP_RELATIVE_PATH, "current ownership") if current_files else None
    registration_relative_path, registration_path = _registration_path(resolved_repository, app_id)
    return BackendLifecycleContext(
        template_root=resolved_template,
        repository_root=resolved_repository,
        target_directory=normalized_target,
        target_path=target_path,
        app_id=app_id,
        registration_relative_path=registration_relative_path,
        registration_path=registration_path,
        foundation_identity=identity,
        desired_files=desired_files,
        desired_ownership=desired_ownership,
        desired_bundle_sha256=_bundle_sha256(desired_files),
        current_files=current_files,
        current_ownership=current_ownership,
        current_bundle_sha256=_bundle_sha256(current_files) if current_files else None,
        registration=_read_registration(registration_path),
    )


def _current_classification(context: BackendLifecycleContext) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Classify current drift, detached ownership, and unowned paths.

    Args:
        context: Validated desired/current lifecycle context.

    Returns:
        Drifted generated paths, detached paths, and unowned paths.
    """

    if context.current_ownership is None:
        return (), (), ()
    owned = _ownership_files(context.current_ownership, "current ownership")
    current = {item.relative_path: item.metadata for item in context.current_files}
    drifted: list[str] = []
    detached: list[str] = []
    for record in owned:
        actual = current.get(record.relative_path)
        if record.detached:
            detached.append(record.relative_path)
        elif actual is None or actual.byte_count != record.byte_count or actual.sha256 != record.sha256:
            drifted.append(record.relative_path)
    owned_paths = {item.relative_path for item in owned} | {OWNERSHIP_RELATIVE_PATH}
    unowned = sorted(set(current) - owned_paths, key=str.casefold)
    return tuple(sorted(drifted, key=str.casefold)), tuple(sorted(detached, key=str.casefold)), tuple(unowned)


def _validate_current_registration(context: BackendLifecycleContext) -> None:
    """Verify that existing root registration exactly describes the target.

    Args:
        context: Validated lifecycle context with an existing target and
            registration.

    Returns:
        None when registration identity matches current target state.

    Raises:
        BackendLifecycleError: If registration metadata is stale or altered.
    """

    identity = context.foundation_identity
    expected_identity = {
        "registration_schema_version": 1,
        "app_id": context.app_id,
        "target_directory": context.target_directory,
        "foundation": {
            "contract_id": identity.contract_id,
            "contract_version": identity.contract_version,
            "foundation_revision": identity.foundation_revision,
            "source_sha256": identity.source_sha256,
        },
    }
    registration = context.registration or {}
    actual_identity = {
        key: registration.get(key) for key in expected_identity
    }
    registered_digest = registration.get("bundle_sha256")
    registered_count = registration.get("file_count")
    valid_snapshot = (
        set(registration) == {*expected_identity, "bundle_sha256", "file_count"}
        and isinstance(registered_digest, str)
        and _SHA256_PATTERN.fullmatch(registered_digest) is not None
        and isinstance(registered_count, int)
        and registered_count > 0
    )
    if actual_identity != expected_identity or not valid_snapshot:
        raise BackendLifecycleError(
            ["backend registration: metadata is invalid for the current target"]
        )


def _change_set(context: BackendLifecycleContext, detached: tuple[str, ...]) -> tuple[LifecycleChange, ...]:
    """Build content-free desired/current generated path actions.

    Args:
        context: Validated desired/current lifecycle context.
        detached: Existing handwritten paths to preserve.

    Returns:
        Stable add, update, remove, and preserve actions.
    """

    desired = {item.relative_path: item.metadata for item in context.desired_files}
    current = {item.relative_path: item.metadata for item in context.current_files}
    changes: list[LifecycleChange] = []
    for path in sorted(set(desired) | set(current), key=str.casefold):
        if path in detached:
            changes.append(LifecycleChange(path, "preserve"))
        elif path not in current:
            changes.append(LifecycleChange(path, "add"))
        elif path not in desired:
            changes.append(LifecycleChange(path, "remove"))
        elif desired[path].sha256 != current[path].sha256:
            changes.append(LifecycleChange(path, "update"))
    return tuple(changes)


def _plan_digest(mapping: dict[str, Any]) -> str:
    """Hash one canonical content-free plan payload.

    Args:
        mapping: Plan fields excluding the final plan digest.

    Returns:
        Lowercase SHA-256 of canonical JSON bytes.
    """

    content = json.dumps(mapping, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _normalize_detach_selection(
    context: BackendLifecycleContext,
    target_exists: bool,
    detach_paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate and normalize generated paths selected for detach.

    Args:
        context: Validated desired/current lifecycle context.
        target_exists: Whether the target and registration currently exist.
        detach_paths: Caller-selected generated paths.

    Returns:
        Stable unique portable detach paths.

    Raises:
        BackendLifecycleError: If no owned target exists or a path is not
            currently generator-owned.
    """

    normalized = tuple(
        sorted(
            {_validate_relative_path(path, "detach_path") for path in detach_paths},
            key=str.casefold,
        )
    )
    if not normalized:
        return ()
    if not target_exists or context.current_ownership is None:
        raise BackendLifecycleError(["detach: an owned existing target is required"])
    generated = {
        item.relative_path
        for item in _ownership_files(context.current_ownership, "current ownership")
        if not item.detached
    }
    missing = set(normalized) - generated
    if missing:
        raise BackendLifecycleError(
            [
                f"detach: path is not generator-owned: {path}"
                for path in sorted(missing)
            ]
        )
    return normalized


def _planned_actions(
    target_exists: bool,
    detach_paths: tuple[str, ...],
    changes: tuple[LifecycleChange, ...],
) -> tuple[str, str]:
    """Select public plan action and compatible write operation.

    Args:
        target_exists: Whether managed target and registration state exists.
        detach_paths: Validated ownership-transfer selection.
        changes: Content-free desired/current changes.

    Returns:
        Public action and compatible create, apply, or detach operation.
    """

    action = "detach" if detach_paths else (
        "create" if not target_exists else ("noop" if not changes else "update")
    )
    write_operation = "detach" if detach_paths else (
        "create" if action == "create" else "apply"
    )
    return action, write_operation


def build_backend_lifecycle_plan(
    context: BackendLifecycleContext,
    operation: str,
    detach_paths: tuple[str, ...] = (),
) -> BackendLifecyclePlan:
    """Build one stale-state-bound read-only backend lifecycle plan.

    Args:
        context: Validated desired/current lifecycle context.
        operation: Requested lifecycle operation.
        detach_paths: Generated paths explicitly selected for detach.

    Returns:
        Content-free deterministic lifecycle plan.

    Raises:
        BackendLifecycleError: If target/registration state is inconsistent.
    """

    target_exists = bool(context.current_files)
    registration_exists = context.registration is not None
    if target_exists != registration_exists:
        raise BackendLifecycleError(["backend lifecycle: target and registration state disagree"])
    if target_exists:
        _validate_current_registration(context)
    drifted, detached, unowned = _current_classification(context)
    normalized_detach = _normalize_detach_selection(
        context,
        target_exists,
        detach_paths,
    )
    changes = (
        tuple(LifecycleChange(path, "detach") for path in normalized_detach)
        if normalized_detach
        else _change_set(context, detached)
    )
    action, write_operation = _planned_actions(target_exists, normalized_detach, changes)
    payload = {
        "write_operation": write_operation,
        "action": action,
        "app_id": context.app_id,
        "target_directory": context.target_directory,
        "desired_bundle_sha256": context.desired_bundle_sha256,
        "current_bundle_sha256": context.current_bundle_sha256,
        "registration_relative_path": context.registration_relative_path,
        "changes": [item.to_mapping() for item in changes],
        "drifted_paths": list(drifted),
        "detached_paths": list(detached),
        "unowned_paths": list(unowned),
    }
    return BackendLifecyclePlan(
        operation=operation,
        action=action,
        app_id=context.app_id,
        target_directory=context.target_directory,
        desired_bundle_sha256=context.desired_bundle_sha256,
        current_bundle_sha256=context.current_bundle_sha256,
        registration_relative_path=context.registration_relative_path,
        changes=changes,
        drifted_paths=drifted,
        detached_paths=detached,
        unowned_paths=unowned,
        plan_sha256=_plan_digest(payload),
    )


def render_registration(
    context: BackendLifecycleContext,
    bundle_sha256: str,
    file_count: int,
) -> bytes:
    """Render secret-free selected-app root registration bytes.

    Args:
        context: Validated backend lifecycle context.
        bundle_sha256: Exact resulting target bundle digest.
        file_count: Exact resulting target file count.

    Returns:
        Canonical newline-terminated UTF-8 JSON bytes.
    """

    identity = context.foundation_identity
    document = {
        "registration_schema_version": 1,
        "app_id": context.app_id,
        "target_directory": context.target_directory,
        "bundle_sha256": bundle_sha256,
        "file_count": file_count,
        "foundation": {
            "contract_id": identity.contract_id,
            "contract_version": identity.contract_version,
            "foundation_revision": identity.foundation_revision,
            "source_sha256": identity.source_sha256,
        },
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
