# Template V2 Backend Foundation Contract

## Purpose

This directory is the Python repository's canonical Template V2 compatibility
boundary. `backend_foundation_contract.json` declares the exact registry,
application-definition, authentication, migration, Compose, dependency, and
route-policy surfaces consumed by the Flutter Template V2 pair orchestrator.

## Ownership And Structure

- `backend_foundation_contract.json` is the machine-readable contract.
- `backend_foundation_contract.py` is the standard-library validator and digest
  implementation.
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
