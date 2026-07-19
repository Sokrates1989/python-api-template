"""Generated-route behavior tests for the Template V2 records starter."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

pytest.importorskip("fastapi", reason="generated route tests require app dependencies")
pytest.importorskip("sqlalchemy", reason="generated route tests require app dependencies")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from template_v2.records_starter_contract import validate_records_starter_contract


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class _FakeRecordsService:
    """Provide deterministic subject-scoped behavior behind generated routes."""

    def __init__(self, conflict_type: type[Exception]) -> None:
        """Create an empty store using the generated conflict type.

        Args:
            conflict_type: Generated repository conflict exception class.
        """

        self._conflict_type = conflict_type
        self._records: dict[str, dict[str, SimpleNamespace]] = {}
        self._next_id = 1

    async def list_records(
        self, owner_subject: str, *, limit: int, offset: int
    ) -> tuple[list[SimpleNamespace], int]:
        """Return only the requested subject's deterministic page.

        Args:
            owner_subject: Verified test subject.
            limit: Maximum records returned.
            offset: Matching records skipped.

        Returns:
            Page plus total subject-owned count.
        """

        records = list(self._records.get(owner_subject, {}).values())
        return records[offset : offset + limit], len(records)

    async def create_record(
        self, owner_subject: str, *, title: str, details: str | None
    ) -> SimpleNamespace:
        """Create one in-memory subject-owned record.

        Args:
            owner_subject: Verified test subject.
            title: Validated title.
            details: Optional validated details.

        Returns:
            New record at revision one.
        """

        now = datetime.now(timezone.utc)
        record = SimpleNamespace(
            id=f"00000000-0000-0000-0000-{self._next_id:012d}",
            title=title,
            details=details,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        self._next_id += 1
        self._records.setdefault(owner_subject, {})[record.id] = record
        return record

    async def get_record(
        self, owner_subject: str, record_id: str
    ) -> SimpleNamespace | None:
        """Return an owned record or the non-disclosing missing sentinel.

        Args:
            owner_subject: Verified test subject.
            record_id: Public record id.

        Returns:
            Owned record, or ``None`` for missing and foreign records.
        """

        return self._records.get(owner_subject, {}).get(record_id)

    async def update_record(
        self,
        owner_subject: str,
        record_id: str,
        *,
        title: str,
        details: str | None,
        expected_revision: int,
    ) -> SimpleNamespace | None:
        """Apply an owned optimistic update.

        Args:
            owner_subject: Verified test subject.
            record_id: Public record id.
            title: Replacement title.
            details: Replacement details.
            expected_revision: Client-observed revision.

        Returns:
            Updated record, or ``None`` for missing and foreign records.

        Raises:
            Exception: Generated conflict type when the revision is stale.
        """

        record = await self.get_record(owner_subject, record_id)
        if record is None:
            return None
        if record.revision != expected_revision:
            raise self._conflict_type(record.revision)
        record.title = title
        record.details = details
        record.revision += 1
        record.updated_at = datetime.now(timezone.utc)
        return record

    async def delete_record(self, owner_subject: str, record_id: str) -> bool:
        """Idempotently delete only an owned record.

        Args:
            owner_subject: Verified test subject.
            record_id: Public record id.

        Returns:
            Whether an owned record was removed.
        """

        records = self._records.get(owner_subject, {})
        return records.pop(record_id, None) is not None


def _load_generated_routes(tmp_path: Path) -> ModuleType:
    """Render and import the canonical generated records route module.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Imported generated routes module.
    """

    app_id = "b3_contract_test"
    contract = validate_records_starter_contract(REPOSITORY_ROOT)
    target = tmp_path / "app" / "apps" / app_id
    target.mkdir(parents=True)
    (target / "__init__.py").write_text('"""Generated route test app."""\n', encoding="utf-8")
    for relative_path, content in contract.render(app_id).items():
        path = target.joinpath(*relative_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    # Extend the already imported backend apps package with the isolated app.
    import apps

    apps.__path__.append(str(tmp_path / "app" / "apps"))
    module_name = f"apps.{app_id}.routes.records"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _build_client(module: ModuleType) -> tuple[TestClient, dict[str, str], _FakeRecordsService]:
    """Build a FastAPI client with explicit auth and service overrides.

    Args:
        module: Imported generated records route module.

    Returns:
        Test client, mutable current-subject state, and fake service.
    """

    app = FastAPI()
    app.include_router(module.router)
    current = {"subject": "proof-user-a"}
    service = _FakeRecordsService(module.RecordRevisionConflict)

    async def current_subject() -> str:
        """Return the currently selected proof subject.

        Returns:
            Subject selected by the test before each request.
        """

        return current["subject"]

    app.dependency_overrides[module.get_user_id_from_token] = current_subject
    app.dependency_overrides[module.get_records_service] = lambda: service
    return TestClient(app), current, service


def test_generated_routes_enforce_subject_isolation_conflict_and_idempotency(
    tmp_path: Path,
) -> None:
    """Prove two-user isolation, revisions, pagination, and repeated deletion."""

    module = _load_generated_routes(tmp_path)
    client, current, _service = _build_client(module)

    created = client.post("/records", json={"title": " First ", "details": "Body"})
    assert created.status_code == 201
    record = created.json()
    assert record["title"] == "First"

    # A second verified subject receives non-disclosing absence for every mutation.
    current["subject"] = "proof-user-b"
    assert client.get(f"/records/{record['id']}").status_code == 404
    foreign_update = client.put(
        f"/records/{record['id']}",
        json={"title": "Foreign", "details": None, "expected_revision": 1},
    )
    assert foreign_update.status_code == 404
    assert client.delete(f"/records/{record['id']}").json() == {"deleted": False}

    current["subject"] = "proof-user-a"
    updated = client.put(
        f"/records/{record['id']}",
        json={"title": "Updated", "details": None, "expected_revision": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    conflict = client.put(
        f"/records/{record['id']}",
        json={"title": "Stale", "details": None, "expected_revision": 1},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "record_revision_conflict"
    assert client.get("/records?limit=1&offset=0").json()["total"] == 1
    assert client.delete(f"/records/{record['id']}").json() == {"deleted": True}
    assert client.delete(f"/records/{record['id']}").json() == {"deleted": False}


def test_generated_routes_reject_whitespace_and_unbounded_payloads(tmp_path: Path) -> None:
    """Prove schema validation rejects empty, oversized, and invalid revision data."""

    module = _load_generated_routes(tmp_path)
    client, _current, _service = _build_client(module)

    assert client.post("/records", json={"title": "   "}).status_code == 422
    assert client.post("/records", json={"title": "x" * 121}).status_code == 422
    assert client.post(
        "/records", json={"title": "Valid", "details": "x" * 4001}
    ).status_code == 422
