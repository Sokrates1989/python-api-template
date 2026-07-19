# Template V2 Networked Recipe Catalog

## Purpose

`networked_recipes_contract.json` is the Python repository's machine-readable
B4 catalog for hybrid synchronization, authenticated Web Push, AI chat, and
account erasure. It fixes each backend recipe identity and its matching Flutter
recipe version before renderable source templates are promoted.

## Ownership And Structure

The Python template owns the catalog schema, backend revisions, deterministic
recipe order, dependency order, API-service-relative routes, migration and
service paths, public/secret configuration key names, and exact removal paths.
`implementation_status` remains `contract_only` until a recipe has canonical
checksum-pinned templates plus selected/absent lifecycle proof in both repos.

The catalog contains names and paths only. It never contains a provider value,
credential, endpoint value, prompt, quota, retention policy, VAPID key, model,
proof identity, or customer schema. Routes must begin with `/` and must never
begin with `/api`.

## Generation And Validation

Run the standard-library validator from the repository root:

```powershell
python tools/validate_template_v2_networked_recipes.py --json
```

The Flutter pair orchestrator independently validates the same exact contract
identity and verifies the three already implemented Flutter recipe versions.
The account-erasure Flutter client remains an explicit B4 implementation task;
its declared version is reserved but not treated as implemented.

## Safe Editing

Do not change a route, dependency, path, configuration key, Flutter mapping, or
status without updating both repositories' compatibility tests. Promote one
recipe from `contract_only` only in the same change that adds its complete
Python-owned source contract and proves selected, absent, add, and remove
lifecycle behavior. Increment `catalog_revision` for semantic catalog changes
and `contract_version` only for incompatible schema changes.
