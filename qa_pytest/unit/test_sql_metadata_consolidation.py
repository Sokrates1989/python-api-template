from models.sql import Base, Example, SyncOperationLog, User


def test_models_share_single_base_metadata() -> None:
    assert Example.metadata is Base.metadata
    assert User.metadata is Base.metadata
    assert SyncOperationLog.metadata is Base.metadata


def test_expected_tables_present_in_shared_metadata() -> None:
    table_names = set(Base.metadata.tables.keys())
    assert "examples" in table_names
    assert "users" in table_names
    assert "sync_operation_log" in table_names
