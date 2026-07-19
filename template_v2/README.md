# Template V2 Backend Foundation And Lifecycle

## Purpose

This directory is the Python repository's canonical Template V2 compatibility
boundary. `backend_foundation_contract.json` declares the exact registry,
application-definition, authentication, migration, Compose, dependency, and
route-policy surfaces consumed by the Flutter Template V2 pair orchestrator.
The lifecycle modules own read-only planning, managed creation/update, explicit
detach, root registration, and exact create rollback for generated backend
applications.

## Ownership And Structure

- `backend_foundation_contract.json` is the machine-readable contract.
- `backend_foundation_contract.py` is the standard-library validator and digest
  implementation.
- `backend_lifecycle.py` is the public in-process lifecycle facade.
- `backend_lifecycle_planning.py` validates desired/current ownership and
  returns content-free stale-state-bound plans.
- `backend_lifecycle_transaction.py` owns atomic create, apply, detach, and
  exact-create rollback together with `.template_v2/apps/<app_id>.json`.
- `tools/template_v2_backend_lifecycle.py` is the cross-repository CLI boundary
  used by the Flutter paired creator.
- `contract_version` changes only for a machine-schema incompatibility.
- `foundation_revision` changes when supported semantics change.
- `source_sha256` covers every sorted `source_files` entry after canonical LF
  normalization. Paths, byte lengths, and bytes are domain-separated.
- `standard_connected_profile` is Keycloak with PostgreSQL.
- Cognito and MongoDB remain explicit retained compatibility, not defaults.

The contract contains no credentials or machine-specific paths. Generated
service routes must remain relative to the API host and must never begin with
`/api` or `/api/`.

## Safe Editing

When a declared source file changes, run:

```powershell
python tools/validate_template_v2_backend_foundation.py --print-source-sha256
```

Review whether the change preserves `foundation_revision`. Update the revision
for a semantic compatibility change, then set the printed digest in the JSON
and rerun the validator. Never weaken a marker or route rule just to accept an
incompatible source tree. The Flutter repository must explicitly adopt any new
contract version or foundation revision before generation resumes.

The JSON format cannot contain comments. This README is its companion
documentation and must evolve in the same commit.

## Managed Lifecycle

Every lifecycle invocation requires an isolated complete desired bundle and an
exact `app/apps/<app_id>` target. `check`, `plan`, `diff`, and `reconcile` are
read-only. A write requires the exact `plan_sha256` returned for current state
plus its fixed intent:

- create: `CREATE_TEMPLATE_V2_BACKEND`;
- apply: `APPLY_TEMPLATE_V2_BACKEND`;
- detach: `DETACH_TEMPLATE_V2_BACKEND`; and
- internal paired rollback: `ROLLBACK_TEMPLATE_V2_BACKEND_CREATE`.

Example read-only plan:

```powershell
python tools/template_v2_backend_lifecycle.py plan `
  --repository-root D:\path\to\backend `
  --bundle-root D:\path\to\isolated-bundle `
  --target-directory app/apps/sample_connected
```

To review a detach without writing, add `--detach-path routes/custom.py` to a
`plan`, `diff`, or `reconcile` command. Apply the resulting exact plan with the
`detach` operation and detach intent. Generated drift always requires an
explicit restore or detach decision. Detached and unowned routes, migrations,
schemas, and services are preserved during managed apply.

The lifecycle never provisions services, reads credentials, or creates local
environment files. Its root registration is public metadata only. Any literal
service route beginning with `/api` or `/api/` is rejected before mutation.
