# Support Matrix

This document defines the current stability matrix for this template.

## Officially Supported (stability target)

- `postgresql` / `postgres`
- `neo4j`
- `mongodb`

These providers are the target for setup flows, local compose profiles, and CI quality gates.

## Legacy Compatibility (best effort)

- `mysql`
- `sqlite`

These values may still work in parts of the codebase, but they are not part of the current stability commitment.

## Notes

- Startup should fail fast when DB init or required migrations fail.
- Lock checks should fail closed by default to avoid write corruption during restore windows.
- Sensitive HTTP data logging must stay disabled by default.

