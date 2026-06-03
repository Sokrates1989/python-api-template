"""Provider-specific startup probes for readiness diagnostics."""
from __future__ import annotations

from typing import Any, Dict

from backend.adapters.provider_capability_factory import normalize_provider_db_type


async def _probe_sql(handler: Any) -> Dict[str, Any]:
    """Run SQL provider probe."""
    from sqlalchemy import text

    async with handler.AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))

    dialect = getattr(getattr(handler, "engine", None), "dialect", None)
    dialect_name = getattr(dialect, "name", "unknown")
    base_obj = getattr(handler, "Base", None)
    metadata = getattr(base_obj, "metadata", None)
    table_count = len(metadata.tables) if metadata is not None else 0

    return {
        "status": "success",
        "provider_profile": "sql",
        "checks": {
            "connectivity": "ok",
            "dialect": dialect_name,
            "declared_sql_models": table_count,
        },
    }


def _probe_neo4j(handler: Any) -> Dict[str, Any]:
    """Run Neo4j provider probe."""
    with handler.driver.session() as session:
        session.run("RETURN 1 AS probe").single()
        component = session.run(
            "CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS version LIMIT 1"
        ).single()

    return {
        "status": "success",
        "provider_profile": "neo4j",
        "checks": {
            "connectivity": "ok",
            "component": component["name"] if component else "neo4j",
            "version": component["version"] if component else "unknown",
        },
    }


async def _probe_mongodb(handler: Any) -> Dict[str, Any]:
    """Run MongoDB provider probe with required index checks."""
    await handler.client.admin.command("ping")

    users = handler.database["users"]
    examples = handler.database["examples"]

    # Align startup requirements with Mongo domain services.
    await users.create_index("id", unique=True, name="idx_users_id_unique")
    await users.create_index("email", unique=True, name="idx_users_email_unique")
    await users.create_index("username", unique=True, name="idx_users_username_unique")
    await examples.create_index("id", unique=True, name="idx_examples_id_unique")
    await examples.create_index("name", name="idx_examples_name")
    await examples.create_index("created_at", name="idx_examples_created_at")

    users_indexes = {index.get("name", "") async for index in users.list_indexes()}
    examples_indexes = {index.get("name", "") async for index in examples.list_indexes()}

    required_users = {
        "idx_users_id_unique",
        "idx_users_email_unique",
        "idx_users_username_unique",
    }
    required_examples = {
        "idx_examples_id_unique",
        "idx_examples_name",
        "idx_examples_created_at",
    }

    missing_users = sorted(required_users - users_indexes)
    missing_examples = sorted(required_examples - examples_indexes)
    if missing_users or missing_examples:
        raise RuntimeError(
            "MongoDB startup index verification failed: "
            f"missing users={missing_users}, missing examples={missing_examples}"
        )

    return {
        "status": "success",
        "provider_profile": "mongodb",
        "checks": {
            "connectivity": "ok",
            "users_indexes": sorted(users_indexes),
            "examples_indexes": sorted(examples_indexes),
            "missing_users_indexes": missing_users,
            "missing_examples_indexes": missing_examples,
        },
    }


async def run_provider_startup_probe(handler: Any) -> Dict[str, Any]:
    """Run provider-specific startup checks and return structured probe output."""
    raw_db_type = (getattr(handler, "db_type", "") or "").strip().lower()
    provider_profile = normalize_provider_db_type(raw_db_type)

    try:
        if provider_profile == "sql":
            return await _probe_sql(handler)
        if provider_profile == "neo4j":
            return _probe_neo4j(handler)
        if provider_profile == "mongodb":
            return await _probe_mongodb(handler)

        return {
            "status": "error",
            "provider_profile": provider_profile,
            "checks": {},
            "message": f"Unsupported provider profile: {provider_profile}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider_profile": provider_profile,
            "checks": {},
            "message": str(exc),
        }
