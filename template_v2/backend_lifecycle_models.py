"""Models for Python-owned Template V2 backend lifecycle operations.

The models are deliberately content-free. They retain portable paths, byte
counts, hashes, ownership classifications, and transaction identities without
holding credentials or exposing generated source in plans and results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


BACKEND_LIFECYCLE_SCHEMA_VERSION = 1
CREATE_INTENT = "CREATE_TEMPLATE_V2_BACKEND"
APPLY_INTENT = "APPLY_TEMPLATE_V2_BACKEND"
DETACH_INTENT = "DETACH_TEMPLATE_V2_BACKEND"
ROLLBACK_CREATE_INTENT = "ROLLBACK_TEMPLATE_V2_BACKEND_CREATE"
OWNERSHIP_RELATIVE_PATH = ".template_v2/ownership.json"
REGISTRATION_SCHEMA_VERSION = 1


class BackendLifecycleError(ValueError):
    """Report one or more content-free backend lifecycle failures.

    Attributes:
        issues: Stable sorted diagnostics using only portable paths.
    """

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        """Initialize an aggregate lifecycle error.

        Args:
            issues: Non-empty lifecycle diagnostics.

        Raises:
            ValueError: If no diagnostic is supplied.
        """

        normalized = tuple(sorted(set(issues)))
        if not normalized:
            raise ValueError("BackendLifecycleError requires an issue")
        self.issues = normalized
        super().__init__("\n".join(normalized))


@dataclass(frozen=True)
class LifecycleFile:
    """Describe one desired or current target file without leaking content.

    Attributes:
        relative_path: Portable path below the backend app target.
        byte_count: Exact file byte length.
        sha256: Lowercase content digest.
        classification: Generated or handwritten ownership classification.
        detached: Whether generator ownership was explicitly transferred.
    """

    relative_path: str
    byte_count: int
    sha256: str
    classification: str = "generated"
    detached: bool = False

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical JSON-compatible ownership record.

        Returns:
            Portable path, size, digest, classification, and detach state.
        """

        return {
            "path": self.relative_path,
            "bytes": self.byte_count,
            "sha256": self.sha256,
            "classification": self.classification,
            "detached": self.detached,
        }


@dataclass(frozen=True)
class LifecycleChange:
    """Describe one content-free desired/current path difference.

    Attributes:
        relative_path: Portable target-relative path.
        action: Add, update, remove, preserve, or detach action.
    """

    relative_path: str
    action: str

    def to_mapping(self) -> dict[str, str]:
        """Return the change as stable JSON-compatible metadata.

        Returns:
            Path and action mapping.
        """

        return {"path": self.relative_path, "action": self.action}


@dataclass(frozen=True)
class BackendLifecyclePlan:
    """Describe one read-only backend lifecycle decision.

    Attributes:
        operation: Requested check, plan, diff, reconcile, create, apply, or
            detach operation.
        action: Required create, noop, update, or detach transaction.
        app_id: Validated backend application identifier.
        target_directory: Portable target below the backend repository.
        desired_bundle_sha256: Content digest of the desired complete target.
        current_bundle_sha256: Current managed bundle digest when available.
        registration_relative_path: Owned root registration file path.
        changes: Content-free ordered path actions.
        drifted_paths: Modified or missing generated paths requiring a decision.
        detached_paths: Handwritten paths already outside generator ownership.
        unowned_paths: Existing target paths preserved during apply.
        plan_sha256: Digest binding every decision and current state.
    """

    operation: str
    action: str
    app_id: str
    target_directory: str
    desired_bundle_sha256: str
    current_bundle_sha256: str | None
    registration_relative_path: str
    changes: tuple[LifecycleChange, ...]
    drifted_paths: tuple[str, ...]
    detached_paths: tuple[str, ...]
    unowned_paths: tuple[str, ...]
    plan_sha256: str

    def to_mapping(self) -> dict[str, object]:
        """Return a content-free canonical plan mapping.

        Returns:
            Lifecycle schema, identities, state, and ordered path metadata.
        """

        return {
            "lifecycle_schema_version": BACKEND_LIFECYCLE_SCHEMA_VERSION,
            "operation": self.operation,
            "action": self.action,
            "writes": False,
            "app_id": self.app_id,
            "target_directory": self.target_directory,
            "desired_bundle_sha256": self.desired_bundle_sha256,
            "current_bundle_sha256": self.current_bundle_sha256,
            "registration_relative_path": self.registration_relative_path,
            "changes": [item.to_mapping() for item in self.changes],
            "drifted_paths": list(self.drifted_paths),
            "detached_paths": list(self.detached_paths),
            "unowned_paths": list(self.unowned_paths),
            "plan_sha256": self.plan_sha256,
        }

    def render(self) -> str:
        """Render stable newline-terminated plan JSON.

        Returns:
            Sorted content-free JSON text.
        """

        return json.dumps(self.to_mapping(), indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class BackendLifecycleResult:
    """Describe one completed create, apply, detach, or rollback transaction.

    Attributes:
        operation: Completed lifecycle operation.
        app_id: Backend application identifier.
        target_directory: Portable backend target path.
        bundle_sha256: Exact resulting bundle digest, or ``None`` after rollback.
        registration_relative_path: Owned root registration path.
        plan_sha256: Exact applied read-only plan identity.
        file_count: Resulting target file count, or zero after rollback.
        writes: Whether repository state changed.
    """

    operation: str
    app_id: str
    target_directory: str
    bundle_sha256: str | None
    registration_relative_path: str
    plan_sha256: str
    file_count: int
    writes: bool

    def render(self) -> str:
        """Render stable newline-terminated result JSON.

        Returns:
            Sorted content-free JSON text.
        """

        mapping = {
            "lifecycle_schema_version": BACKEND_LIFECYCLE_SCHEMA_VERSION,
            "operation": self.operation,
            "writes": self.writes,
            "app_id": self.app_id,
            "target_directory": self.target_directory,
            "bundle_sha256": self.bundle_sha256,
            "registration_relative_path": self.registration_relative_path,
            "plan_sha256": self.plan_sha256,
            "file_count": self.file_count,
        }
        return json.dumps(mapping, indent=2, sort_keys=True) + "\n"
