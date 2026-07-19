"""Contract tests for the Python-owned Template V2 records starter."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from template_v2.records_starter_contract import (
    CONTRACT_RELATIVE_PATH,
    TEMPLATE_ROOT_RELATIVE_PATH,
    RecordsStarterContractError,
    validate_records_starter_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _copy_contract(tmp_path: Path) -> Path:
    """Copy the bounded records contract surface into a temporary root.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Temporary repository root containing manifest and templates.
    """

    manifest = REPOSITORY_ROOT.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
    target_manifest = tmp_path.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
    target_manifest.parent.mkdir(parents=True)
    shutil.copyfile(manifest, target_manifest)

    # Canonical sources are copied without unrelated backend files.
    source_templates = REPOSITORY_ROOT.joinpath(*TEMPLATE_ROOT_RELATIVE_PATH.split("/"))
    target_templates = tmp_path.joinpath(*TEMPLATE_ROOT_RELATIVE_PATH.split("/"))
    shutil.copytree(source_templates, target_templates)
    return tmp_path


def test_records_contract_renders_complete_subject_scoped_starter() -> None:
    """Render all B3 backend layers with safe routes and no placeholders."""

    contract = validate_records_starter_contract(REPOSITORY_ROOT)
    outputs = contract.render("sample_app")

    assert contract.starter_revision == "1.0.0"
    assert len(outputs) == 13
    assert "migrations/versions/sample_app_001_records.py" in outputs
    assert b'prefix="/records"' in outputs["routes/records.py"]
    assert b"get_user_id_from_token" in outputs["routes/records.py"]
    assert b"RecordRevisionConflict" in outputs["routes/records.py"]
    assert b'path_prefix="/records"' in outputs["definition.py"]
    assert b"/api/" not in b"\n".join(outputs.values())
    assert b"__APP_ID__" not in b"\n".join(outputs.values())
    repository = outputs["repositories/records_repository.py"]
    assert repository.count(b"Record.owner_subject == owner_subject") >= 4
    assert b"with_for_update()" in repository
    assert b"expected_revision" in repository
    schemas = outputs["schemas/records.py"]
    assert b"max_length=120" in schemas
    assert b"max_length=4000" in schemas
    assert b"expected_revision: int = Field(ge=1)" in schemas
    migration = outputs["migrations/versions/sample_app_001_records.py"]
    assert b"def upgrade()" in migration
    assert b"def downgrade()" in migration
    assert b"op.create_table(" in migration
    assert b'"sample_app_records"' in migration
    assert b'op.drop_table("sample_app_records")' in migration

    # Every generated Python file must parse before lifecycle publication.
    for path, content in outputs.items():
        if path.endswith(".py"):
            compile(content, path, "exec")


def test_records_contract_rejects_template_drift(tmp_path: Path) -> None:
    """Reject a source edit unless its canonical contract digest changes too."""

    root = _copy_contract(tmp_path)
    route = root.joinpath(*TEMPLATE_ROOT_RELATIVE_PATH.split("/"), "routes", "records.py.tmpl")
    route.write_text(route.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    with pytest.raises(RecordsStarterContractError) as captured:
        validate_records_starter_contract(root)

    assert "records template routes/records.py.tmpl: checksum drifted" in captured.value.issues


def test_records_contract_rejects_nonstandard_profile(tmp_path: Path) -> None:
    """Keep Cognito and MongoDB dormant instead of silently selecting B3."""

    root = _copy_contract(tmp_path)
    path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["standard_profile"] = {"auth_provider": "cognito", "backend": "mongodb"}
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RecordsStarterContractError) as captured:
        validate_records_starter_contract(root)

    assert captured.value.issues == ("contract.standard_profile: unsupported value",)


def test_records_contract_rejects_unsafe_app_identity() -> None:
    """Prevent substitutions from escaping app-local Python identifiers."""

    contract = validate_records_starter_contract(REPOSITORY_ROOT)

    with pytest.raises(RecordsStarterContractError) as captured:
        contract.render("../unsafe")

    assert captured.value.issues == ("records starter app_id: invalid value",)
