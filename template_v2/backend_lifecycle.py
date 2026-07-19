"""Public facade for Python-owned Template V2 backend lifecycle operations.

Read-only operations always return a content-free plan. Create, apply, detach,
and exact create rollback delegate to rollback-safe transactions only after an
exact plan digest and operation-specific write intent are supplied.
"""

from __future__ import annotations

from pathlib import Path

from .backend_lifecycle_models import BackendLifecycleError
from .backend_lifecycle_planning import (
    BackendLifecycleContext,
    build_backend_lifecycle_plan,
    load_backend_lifecycle_context,
)
from .backend_lifecycle_transaction import (
    apply_backend_target,
    create_backend_target,
    detach_backend_paths,
    rollback_created_backend_target,
)


READ_ONLY_OPERATIONS = frozenset({"check", "plan", "diff", "reconcile"})
WRITE_OPERATIONS = frozenset({"create", "apply", "detach", "rollback-create"})


def _execute_write(
    operation: str,
    context: BackendLifecycleContext,
    expected_plan_sha256: str | None,
    write_intent: str | None,
    detach_paths: tuple[str, ...],
) -> str:
    """Build and execute one explicitly authorized write operation.

    Args:
        operation: Create, apply, detach, or rollback-create operation.
        context: Fresh validated lifecycle context.
        expected_plan_sha256: Exact reviewed current-state plan identity.
        write_intent: Exact operation-specific write authority.
        detach_paths: Generated paths selected for ownership transfer.

    Returns:
        Newline-terminated content-free transaction result JSON.
    """

    plan = build_backend_lifecycle_plan(context, operation, detach_paths)
    authority = {
        "expected_plan_sha256": expected_plan_sha256,
        "write_intent": write_intent,
    }
    if operation == "create":
        return create_backend_target(context, plan, **authority).render()
    if operation == "apply":
        return apply_backend_target(context, plan, **authority).render()
    if operation == "detach":
        return detach_backend_paths(
            context,
            plan,
            detach_paths,
            **authority,
        ).render()
    return rollback_created_backend_target(context, plan, **authority).render()


def execute_backend_lifecycle(
    operation: str,
    *,
    template_root: Path,
    repository_root: Path,
    bundle_root: Path,
    target_directory: str,
    expected_plan_sha256: str | None = None,
    write_intent: str | None = None,
    detach_paths: tuple[str, ...] = (),
) -> str:
    """Execute one read-only or explicitly authorized lifecycle operation.

    Args:
        operation: Check, plan, diff, reconcile, create, apply, detach, or
            rollback-create.
        template_root: Python API template root owning B1/B2 contracts.
        repository_root: Explicit backend publication repository.
        bundle_root: Isolated desired complete target tree.
        target_directory: Exact ``app/apps/<app_id>`` destination.
        expected_plan_sha256: Required exact plan identity for writes.
        write_intent: Required exact operation-specific write authority.
        detach_paths: Generated paths selected for detach.

    Returns:
        Newline-terminated content-free plan or result JSON.

    Raises:
        BackendLifecycleError: If operation, source, state, or authority is
            unsupported or unsafe.
    """

    if operation not in READ_ONLY_OPERATIONS | WRITE_OPERATIONS:
        raise BackendLifecycleError([f"operation: unsupported lifecycle choice {operation!r}"])
    detach_plan_operations = frozenset({"plan", "diff", "reconcile", "detach"})
    if detach_paths and operation not in detach_plan_operations:
        raise BackendLifecycleError(
            ["detach_path: values are valid only for plan, diff, reconcile, or detach"]
        )
    context = load_backend_lifecycle_context(
        template_root,
        repository_root,
        bundle_root,
        target_directory,
    )
    if operation in READ_ONLY_OPERATIONS:
        if expected_plan_sha256 is not None or write_intent is not None:
            raise BackendLifecycleError(["read-only lifecycle operations reject write authority"])
        plan = build_backend_lifecycle_plan(context, operation, detach_paths)
        return plan.render()
    return _execute_write(
        operation,
        context,
        expected_plan_sha256,
        write_intent,
        detach_paths,
    )
