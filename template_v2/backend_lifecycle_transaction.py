"""Apply rollback-safe Python-owned Template V2 backend lifecycle changes.

Create, managed apply, detach, and exact create rollback use complete staging
trees and atomic renames. Root registration participates in the same logical
transaction. Any failure restores the prior target and registration whenever
their bytes remain under lifecycle ownership.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .backend_lifecycle_models import (
    APPLY_INTENT,
    CREATE_INTENT,
    DETACH_INTENT,
    OWNERSHIP_RELATIVE_PATH,
    ROLLBACK_CREATE_INTENT,
    BackendLifecycleError,
    BackendLifecyclePlan,
    BackendLifecycleResult,
)
from .backend_lifecycle_planning import (
    BackendLifecycleContext,
    BundleFile,
    _bundle_sha256,
    _ownership_files,
    build_backend_lifecycle_plan,
    render_registration,
)


TransactionObserver = Callable[[str], None]


def _require_write_authority(
    plan: BackendLifecyclePlan,
    expected_plan_sha256: str | None,
    write_intent: str | None,
    expected_intent: str,
) -> None:
    """Validate exact stale-plan and write-intent authority.

    Args:
        plan: Fresh read-only plan for current state.
        expected_plan_sha256: Caller-bound plan identity.
        write_intent: Caller-provided exact operation intent.
        expected_intent: Required operation-specific intent value.

    Returns:
        None when both authorities match.

    Raises:
        BackendLifecycleError: If the plan is stale or intent is absent.
    """

    issues: list[str] = []
    if expected_plan_sha256 != plan.plan_sha256:
        issues.append("lifecycle plan: expected plan SHA-256 is stale or missing")
    if write_intent != expected_intent:
        issues.append(f"write_intent: expected exact value {expected_intent}")
    if issues:
        raise BackendLifecycleError(issues)


def _notify(observer: TransactionObserver | None, event: str) -> None:
    """Notify an optional deterministic transaction observer.

    Args:
        observer: Optional test/progress callback.
        event: Stable lifecycle event name.

    Returns:
        None after callback completion.
    """

    if observer is not None:
        observer(event)


def _write_tree(root: Path, files: tuple[BundleFile, ...]) -> None:
    """Write and byte-verify one complete staging tree.

    Args:
        root: Existing empty staging directory.
        files: Complete target files to materialize.

    Returns:
        None after exact verification.

    Raises:
        BackendLifecycleError: If staging or verification fails.
    """

    try:
        for item in files:
            target = root.joinpath(*item.relative_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.content)
            if target.read_bytes() != item.content:
                raise BackendLifecycleError([f"lifecycle staging: byte verification failed at {item.relative_path}"])
    except BackendLifecycleError:
        raise
    except OSError as error:
        raise BackendLifecycleError(["lifecycle staging: target tree write failed"]) from error


def _exact_tree_digest(root: Path) -> tuple[str, int]:
    """Read an exact regular target tree and return bundle identity/count.

    Args:
        root: Existing target or backup tree.

    Returns:
        Bundle SHA-256 and file count.

    Raises:
        BackendLifecycleError: If unsafe filesystem state is found.
    """

    files: list[BundleFile] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative_path = path.relative_to(root).as_posix()
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise BackendLifecycleError([f"lifecycle target: unsafe path {relative_path}"])
        if path.is_file():
            try:
                files.append(BundleFile(relative_path, path.read_bytes()))
            except OSError as error:
                raise BackendLifecycleError([f"lifecycle target: unreadable path {relative_path}"]) from error
    typed = tuple(files)
    return _bundle_sha256(typed), len(typed)


def _registration_bytes(context: BackendLifecycleContext) -> bytes | None:
    """Return existing registration bytes for transaction restoration.

    Args:
        context: Validated lifecycle context.

    Returns:
        Existing exact bytes, or ``None`` when registration is absent.

    Raises:
        BackendLifecycleError: If existing bytes cannot be read.
    """

    if context.registration is None:
        return None
    try:
        return context.registration_path.read_bytes()
    except OSError as error:
        raise BackendLifecycleError(["backend registration: existing bytes are unreadable"]) from error


def _replace_registration(context: BackendLifecycleContext, content: bytes) -> None:
    """Atomically create or replace one owned root registration.

    Args:
        context: Validated registration path ownership.
        content: Complete canonical registration bytes.

    Returns:
        None after exact replacement.

    Raises:
        BackendLifecycleError: If staging or replacement fails.
    """

    parent = context.registration_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".registration-", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        if temporary.read_bytes() != content:
            raise BackendLifecycleError(["backend registration: byte verification failed"])
        os.replace(temporary, context.registration_path)
    except BackendLifecycleError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise BackendLifecycleError(["backend registration: atomic replacement failed"]) from error


def _restore_registration(context: BackendLifecycleContext, previous: bytes | None) -> None:
    """Restore exact prior registration bytes after transaction failure.

    Args:
        context: Validated registration path ownership.
        previous: Prior bytes, or ``None`` when it was absent.

    Returns:
        None after restoration and empty-directory cleanup.
    """

    if previous is None:
        context.registration_path.unlink(missing_ok=True)
        _remove_empty_registration_directories(context)
    else:
        _replace_registration(context, previous)


def _remove_empty_registration_directories(context: BackendLifecycleContext) -> None:
    """Remove lifecycle-created empty registration parent directories.

    Args:
        context: Registration path and repository root boundary.

    Returns:
        None after best-effort bounded empty-directory cleanup.
    """

    for path in (context.registration_path.parent, context.registration_path.parent.parent):
        if path != context.repository_root:
            try:
                path.rmdir()
            except OSError:
                break


def _result(
    operation: str,
    context: BackendLifecycleContext,
    plan: BackendLifecyclePlan,
    bundle_sha256: str | None,
    file_count: int,
    writes: bool,
) -> BackendLifecycleResult:
    """Build one content-free lifecycle transaction result.

    Args:
        operation: Completed operation name.
        context: Validated target/registration identity.
        plan: Exact applied read-only plan.
        bundle_sha256: Resulting bundle identity, or ``None`` after rollback.
        file_count: Resulting file count.
        writes: Whether repository state changed.

    Returns:
        Immutable lifecycle result.
    """

    return BackendLifecycleResult(
        operation=operation,
        app_id=context.app_id,
        target_directory=context.target_directory,
        bundle_sha256=bundle_sha256,
        registration_relative_path=context.registration_relative_path,
        plan_sha256=plan.plan_sha256,
        file_count=file_count,
        writes=writes,
    )


def create_backend_target(
    context: BackendLifecycleContext,
    plan: BackendLifecyclePlan,
    *,
    expected_plan_sha256: str | None,
    write_intent: str | None,
    observer: TransactionObserver | None = None,
) -> BackendLifecycleResult:
    """Atomically create one backend target and root registration.

    Args:
        context: Validated absent target lifecycle context.
        plan: Fresh create plan.
        expected_plan_sha256: Exact caller-approved plan identity.
        write_intent: Exact create intent.
        observer: Optional deterministic test/progress callback.

    Returns:
        Successful target and registration metadata.

    Raises:
        BackendLifecycleError: If authorization, staging, publication, or
            rollback fails.
        KeyboardInterrupt: After complete rollback on cancellation.
    """

    _require_write_authority(plan, expected_plan_sha256, write_intent, CREATE_INTENT)
    if plan.action != "create" or context.target_path.exists() or context.registration is not None:
        raise BackendLifecycleError(["create: target and registration must both be absent"])
    context.target_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".template-v2-{context.app_id}-", dir=context.target_path.parent))
    previous_registration = _registration_bytes(context)
    published = False
    try:
        _write_tree(staging, context.desired_files)
        _notify(observer, "before_target_publish")
        os.rename(staging, context.target_path)
        published = True
        _notify(observer, "before_registration_publish")
        registration = render_registration(context, context.desired_bundle_sha256, len(context.desired_files))
        _replace_registration(context, registration)
        _notify(observer, "after_registration_publish")
    except (KeyboardInterrupt, SystemExit):
        _rollback_create_failure(context, staging, published, previous_registration)
        raise
    except Exception as error:
        _rollback_create_failure(context, staging, published, previous_registration)
        if isinstance(error, BackendLifecycleError):
            raise
        raise BackendLifecycleError(["create: publication failed and was rolled back"]) from error
    return _result("create", context, plan, context.desired_bundle_sha256, len(context.desired_files), True)


def _rollback_create_failure(
    context: BackendLifecycleContext,
    staging: Path,
    published: bool,
    previous_registration: bytes | None,
) -> None:
    """Withdraw partial create state after failure or cancellation.

    Args:
        context: Validated target and registration identity.
        staging: Original lifecycle staging path.
        published: Whether staging was renamed to the final target.
        previous_registration: Registration bytes before the attempt.

    Returns:
        None after exact rollback.

    Raises:
        BackendLifecycleError: If changed partial state cannot be withdrawn.
    """

    _restore_registration(context, previous_registration)
    if published:
        digest, _count = _exact_tree_digest(context.target_path)
        if digest != context.desired_bundle_sha256:
            raise BackendLifecycleError(["create rollback: published target drifted; manual recovery required"])
        shutil.rmtree(context.target_path)
    elif staging.exists():
        shutil.rmtree(staging)


def _merged_apply_files(context: BackendLifecycleContext) -> tuple[BundleFile, ...]:
    """Build desired generated bytes plus preserved detached/unowned files.

    Args:
        context: Validated existing target and desired lifecycle state.

    Returns:
        Complete target files with a merged ownership manifest.

    Raises:
        BackendLifecycleError: If desired paths collide with preserved state.
    """

    if context.current_ownership is None:
        raise BackendLifecycleError(["apply: existing ownership manifest is required"])
    desired = {item.relative_path: item for item in context.desired_files}
    current = {item.relative_path: item for item in context.current_files}
    current_records = _ownership_files(context.current_ownership, "current ownership")
    detached_records = [item for item in current_records if item.detached]
    owned_paths = {item.relative_path for item in current_records} | {OWNERSHIP_RELATIVE_PATH}
    unowned_paths = set(current) - owned_paths
    collisions = set(desired) & unowned_paths
    if collisions:
        raise BackendLifecycleError([f"apply: desired path collides with preserved state: {path}" for path in sorted(collisions)])
    resulting = {path: item for path, item in desired.items() if path != OWNERSHIP_RELATIVE_PATH}
    for record in detached_records:
        resulting.pop(record.relative_path, None)
        if record.relative_path in current:
            resulting[record.relative_path] = current[record.relative_path]
    for path in sorted(unowned_paths):
        resulting[path] = current[path]
    ownership = json.loads(json.dumps(context.desired_ownership))
    refreshed_detached = []
    for record in detached_records:
        if record.relative_path not in current:
            refreshed_detached.append(record.to_mapping())
            continue
        metadata = current[record.relative_path].metadata
        refreshed_detached.append(
            {
                "path": record.relative_path,
                "bytes": metadata.byte_count,
                "sha256": metadata.sha256,
                "classification": "handwritten",
                "detached": True,
            }
        )
    detached_paths = {item.relative_path for item in detached_records}
    generated_records = [
        item
        for item in ownership["files"]
        if item["path"] not in detached_paths
    ]
    ownership["files"] = sorted(
        [*generated_records, *refreshed_detached],
        key=lambda item: item["path"].casefold(),
    )
    resulting[OWNERSHIP_RELATIVE_PATH] = BundleFile(
        OWNERSHIP_RELATIVE_PATH,
        (json.dumps(ownership, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return tuple(sorted(resulting.values(), key=lambda item: item.relative_path.casefold()))


def _swap_existing_target(
    context: BackendLifecycleContext,
    files: tuple[BundleFile, ...],
    observer: TransactionObserver | None,
) -> tuple[str, int]:
    """Atomically swap one existing target and registration with rollback.

    Args:
        context: Validated existing lifecycle context.
        files: Complete replacement target bytes.
        observer: Optional deterministic test/progress callback.

    Returns:
        Resulting bundle SHA-256 and file count.

    Raises:
        BackendLifecycleError: If staging, swap, registration, or rollback fails.
    """

    staging = Path(tempfile.mkdtemp(prefix=f".template-v2-{context.app_id}-", dir=context.target_path.parent))
    backup = context.target_path.parent / f".template-v2-backup-{context.app_id}-{uuid.uuid4().hex}"
    previous_registration = _registration_bytes(context)
    resulting_digest = _bundle_sha256(files)
    swapped = False
    try:
        _write_tree(staging, files)
        _notify(observer, "before_target_swap")
        os.rename(context.target_path, backup)
        os.rename(staging, context.target_path)
        swapped = True
        _notify(observer, "before_registration_publish")
        _replace_registration(context, render_registration(context, resulting_digest, len(files)))
        _notify(observer, "after_registration_publish")
        shutil.rmtree(backup)
    except (KeyboardInterrupt, SystemExit):
        _restore_failed_swap(context, staging, backup, swapped, previous_registration)
        raise
    except Exception as error:
        _restore_failed_swap(context, staging, backup, swapped, previous_registration)
        if isinstance(error, BackendLifecycleError):
            raise
        raise BackendLifecycleError(["apply: target swap failed and was rolled back"]) from error
    return resulting_digest, len(files)


def _restore_failed_swap(
    context: BackendLifecycleContext,
    staging: Path,
    backup: Path,
    swapped: bool,
    previous_registration: bytes | None,
) -> None:
    """Restore exact target and registration state after a failed swap.

    Args:
        context: Validated lifecycle context.
        staging: Possible unpublished replacement tree.
        backup: Possible prior target tree.
        swapped: Whether the replacement reached the final target path.
        previous_registration: Exact registration bytes before the swap.

    Returns:
        None after restoration and staging cleanup.
    """

    _restore_registration(context, previous_registration)
    if swapped:
        if context.target_path.exists():
            shutil.rmtree(context.target_path)
        os.rename(backup, context.target_path)
    elif backup.exists() and not context.target_path.exists():
        os.rename(backup, context.target_path)
    if staging.exists():
        shutil.rmtree(staging)


def apply_backend_target(
    context: BackendLifecycleContext,
    plan: BackendLifecyclePlan,
    *,
    expected_plan_sha256: str | None,
    write_intent: str | None,
    observer: TransactionObserver | None = None,
) -> BackendLifecycleResult:
    """Apply one no-op or safe managed backend update.

    Args:
        context: Validated existing lifecycle context.
        plan: Fresh apply plan.
        expected_plan_sha256: Exact caller-approved plan identity.
        write_intent: Exact apply intent.
        observer: Optional deterministic test/progress callback.

    Returns:
        No-op or successful managed apply metadata.

    Raises:
        BackendLifecycleError: If drift, stale authority, or transaction failure
            prevents a safe update.
    """

    _require_write_authority(plan, expected_plan_sha256, write_intent, APPLY_INTENT)
    if plan.action == "create":
        raise BackendLifecycleError(["apply: existing owned target is required"])
    if plan.drifted_paths:
        raise BackendLifecycleError([f"apply: generated drift requires restore or detach: {path}" for path in plan.drifted_paths])
    if plan.action == "noop":
        return _result("apply", context, plan, context.current_bundle_sha256, len(context.current_files), False)
    files = _merged_apply_files(context)
    digest, count = _swap_existing_target(context, files, observer)
    return _result("apply", context, plan, digest, count, True)


def _detached_files(context: BackendLifecycleContext, paths: tuple[str, ...]) -> tuple[BundleFile, ...]:
    """Build current bytes with selected ownership records detached.

    Args:
        context: Validated existing lifecycle context.
        paths: Generated paths selected for ownership transfer.

    Returns:
        Complete current target with updated ownership manifest.
    """

    if context.current_ownership is None:
        raise BackendLifecycleError(["detach: existing ownership manifest is required"])
    current = {item.relative_path: item for item in context.current_files}
    records = _ownership_files(context.current_ownership, "current ownership")
    selected = set(paths)
    rendered_records: list[dict[str, object]] = []
    for record in records:
        if record.relative_path in selected:
            metadata = (
                current[record.relative_path].metadata
                if record.relative_path in current
                else record
            )
            rendered_records.append(
                {
                    "path": record.relative_path,
                    "bytes": metadata.byte_count,
                    "sha256": metadata.sha256,
                    "classification": "handwritten",
                    "detached": True,
                }
            )
        else:
            rendered_records.append(record.to_mapping())
    ownership = json.loads(json.dumps(context.current_ownership))
    ownership["files"] = sorted(rendered_records, key=lambda item: str(item["path"]).casefold())
    current[OWNERSHIP_RELATIVE_PATH] = BundleFile(
        OWNERSHIP_RELATIVE_PATH,
        (json.dumps(ownership, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return tuple(sorted(current.values(), key=lambda item: item.relative_path.casefold()))


def detach_backend_paths(
    context: BackendLifecycleContext,
    plan: BackendLifecyclePlan,
    paths: tuple[str, ...],
    *,
    expected_plan_sha256: str | None,
    write_intent: str | None,
    observer: TransactionObserver | None = None,
) -> BackendLifecycleResult:
    """Transfer selected generated paths to handwritten ownership atomically.

    Args:
        context: Validated existing lifecycle context.
        plan: Fresh detach plan.
        paths: Exact generated paths selected for detach.
        expected_plan_sha256: Exact caller-approved plan identity.
        write_intent: Exact detach intent.
        observer: Optional deterministic test/progress callback.

    Returns:
        Successful detach metadata.
    """

    _require_write_authority(plan, expected_plan_sha256, write_intent, DETACH_INTENT)
    if plan.action != "detach":
        raise BackendLifecycleError(["detach: plan does not contain detach changes"])
    files = _detached_files(context, paths)
    digest, count = _swap_existing_target(context, files, observer)
    return _result("detach", context, plan, digest, count, True)


def rollback_created_backend_target(
    context: BackendLifecycleContext,
    plan: BackendLifecyclePlan,
    *,
    expected_plan_sha256: str | None,
    write_intent: str | None,
) -> BackendLifecycleResult:
    """Withdraw one exact unchanged create publication and registration.

    Args:
        context: Validated existing target matching the desired create bundle.
        plan: Fresh current-state plan.
        expected_plan_sha256: Exact caller-approved plan identity.
        write_intent: Exact internal create-rollback intent.

    Returns:
        Successful rollback metadata with no resulting bundle.

    Raises:
        BackendLifecycleError: If target/registration drift prevents withdrawal.
    """

    _require_write_authority(plan, expected_plan_sha256, write_intent, ROLLBACK_CREATE_INTENT)
    if context.current_bundle_sha256 != context.desired_bundle_sha256 or context.registration is None:
        raise BackendLifecycleError(["rollback-create: exact unchanged publication is required"])
    if context.registration.get("bundle_sha256") != context.desired_bundle_sha256:
        raise BackendLifecycleError(["rollback-create: registration identity drifted"])
    withdrawal = context.target_path.parent / f".template-v2-withdraw-{context.app_id}-{uuid.uuid4().hex}"
    registration_bytes = _registration_bytes(context)
    try:
        os.rename(context.target_path, withdrawal)
        context.registration_path.unlink()
        _remove_empty_registration_directories(context)
        digest, _count = _exact_tree_digest(withdrawal)
        if digest != context.desired_bundle_sha256:
            raise BackendLifecycleError(["rollback-create: withdrawn target drifted"])
        shutil.rmtree(withdrawal)
    except (KeyboardInterrupt, SystemExit):
        _restore_failed_withdrawal(context, withdrawal, registration_bytes)
        raise
    except Exception as error:
        _restore_failed_withdrawal(context, withdrawal, registration_bytes)
        if isinstance(error, BackendLifecycleError):
            raise
        raise BackendLifecycleError(["rollback-create: withdrawal failed and was restored"]) from error
    return _result("rollback-create", context, plan, None, 0, True)


def _restore_failed_withdrawal(
    context: BackendLifecycleContext,
    withdrawal: Path,
    registration_bytes: bytes | None,
) -> None:
    """Restore an interrupted exact-create withdrawal.

    Args:
        context: Validated lifecycle target and registration paths.
        withdrawal: Temporary withdrawn target path.
        registration_bytes: Exact registration bytes before withdrawal.

    Returns:
        None after target and registration restoration.
    """

    if withdrawal.exists() and not context.target_path.exists():
        os.rename(withdrawal, context.target_path)
    if registration_bytes is not None and not context.registration_path.exists():
        _replace_registration(context, registration_bytes)
