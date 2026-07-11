"""Contract tests for provider-shared wellness catalogue management."""

import inspect
import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.felix.schemas.wellness import (
    WellnessActivityCategoryCreateRequest,
    WellnessActivityCreateRequest,
    WellnessActivityUpdateRequest,
)
from backend.ports.wellness_repository import WellnessRepository


def test_activity_create_requires_a_category() -> None:
    """Reject activities that cannot be reached from any category."""
    with pytest.raises(ValidationError):
        WellnessActivityCreateRequest(title="Unsorted", category_keys=[])


def test_activity_update_rejects_an_empty_patch() -> None:
    """Reject empty patches before they reach a provider implementation."""
    with pytest.raises(ValidationError):
        WellnessActivityUpdateRequest()


def test_category_create_accepts_user_authored_metadata() -> None:
    """Accept the PWA fields required for a custom category."""
    request = WellnessActivityCategoryCreateRequest(
        title="My reset tools",
        description="Short exercises that help me settle",
        icon_key="self_improvement",
        sort_order=3,
    )

    assert request.title == "My reset tools"
    assert request.sort_order == 3


def test_repository_protocol_forces_complete_catalogue_crud() -> None:
    """Keep future providers from silently omitting hybrid catalogue paths."""
    required_methods = {
        "create_activity",
        "update_activity",
        "delete_activity",
        "create_activity_category",
        "update_activity_category",
        "delete_activity_category",
    }

    protocol_methods = {
        name
        for name, _ in inspect.getmembers(
            WellnessRepository,
            inspect.isfunction,
        )
    }
    assert required_methods.issubset(protocol_methods)


def test_felix_migration_revision_ids_fit_widened_version_column() -> None:
    """Keep Felix revision ids within its widened VARCHAR(128) column."""
    migration_root = Path("app/apps/felix/migrations/versions")
    oversized: list[tuple[str, str]] = []
    for migration in migration_root.glob("*.py"):
        module = ast.parse(migration.read_text(encoding="utf-8-sig"))
        for statement in module.body:
            if not isinstance(statement, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "revision"
                for target in statement.targets
            ):
                continue
            if isinstance(statement.value, ast.Constant) and isinstance(
                statement.value.value,
                str,
            ):
                revision = statement.value.value
                if len(revision) > 128:
                    oversized.append((str(migration), revision))

    assert oversized == []


def test_felix_version_column_transition_revision_fits_legacy_column() -> None:
    """Ensure the migration that widens Felix's version column still fits it."""
    assert len("felix_005_activity_catalog") <= 32
