# Hybrid Sync API (Phase 1)

This document describes the first backend sync slice implemented for offline-first Flutter clients.

## Scope

Current implementation supports one syncable entity:

- `user_profile`

Supported operations:

- `update`
- `upsert`

The operation payload currently supports these fields:

- `username`
- `email`
- `first_name`
- `last_name`

## Endpoints

1. `POST /v1/sync/push`
2. `GET /v1/sync/pull`
3. `POST /v1/sync/conflicts/resolve`

All endpoints require bearer authentication and apply ownership checks against the authenticated user id.

## Push (`POST /v1/sync/push`)

Accepts batched operations and returns per-operation results:

- `applied`
- `conflict`
- `rejected`
- `retryable_error`

### Idempotency

- Processed operation results are stored in `sync_operation_log` keyed by `op_id`.
- Replaying the same `op_id` returns the stored result instead of re-applying writes.

## Pull (`GET /v1/sync/pull`)

Returns incremental changes after an opaque cursor.

- Cursor is base64-encoded JSON with `updated_at` and `entity_id`.
- Ordering is deterministic by `(updated_at, entity_id)`.
- Current implementation emits at most one change for the authenticated `user_profile`.

## Conflict Resolution (`POST /v1/sync/conflicts/resolve`)

Supports strategies:

- `prefer_server`
- `prefer_local`
- `merged_payload`

When `expected_server_version` does not match the current server version, conflict details are returned.

## Data Model Changes

Migration: `009_add_sync_support`

1. Add `users.version` for optimistic concurrency.
2. Ensure `users.updated_at` is always non-null with default `now()`.
3. Add `sync_operation_log` table for idempotent replay.

## Notes

- This is the initial vertical slice intended to validate hybrid sync behavior.
- Additional entities, delete tombstones, and broader feed semantics can be layered in later phases.
