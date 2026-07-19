# Hybrid Sync Recipe Source Contract

## Purpose

`recipe.json` pins the Python-owned, app-scoped source templates for backend
recipe `hybrid_sync` revision `1.0.0`. It covers the neutral `record` sync
entity/change/idempotency state, repository, service, schemas, authenticated
`/sync/push` and `/sync/pull` routes, and app-scoped Alembic migration.

## Ownership And Structure

The manifest is maintained by `python-api-template`. Every `template_path` is
relative to this directory's `templates/` folder. Every `output_path` is
relative to the generated backend app and must exactly match the catalog's
migration and service paths. SHA-256 values cover LF-normalized UTF-8 source.

The recipe deliberately synchronizes only the neutral B3 `record` contract.
Product entity vocabularies, payload policy, retention changes, quotas,
credentials, provider setup, and deployment secrets remain app-owned.

## Generation And Verification

Run the catalog validator and focused source tests from the Python repository
root. A consumer must validate identity, complete output coverage, safe paths,
and every checksum before substituting the validated app id.

## Safe Editing Rules

- Never add credentials, owner identities, deployment URLs, or customer data.
- Never add an `/api/` route prefix.
- Update source, checksum, tests, catalog revision, and companion docs together.
- Do not expose another renderable recipe through composition until its source
  contract and selected, absent, add, and removal gates pass.
