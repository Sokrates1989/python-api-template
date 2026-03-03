# External Backup and Restore

This API template no longer provides built-in `/backup/*` endpoints.

Backup and restore operations are handled by the dedicated backup service repositories:

- `D:\Development\Code\python\backup-restore`
- `D:\Development\Code\swarm\swarm-backup-restore`

## What This API Provides

This template exposes only lock coordination endpoints for external orchestration:

- `POST /database/lock`
- `POST /database/unlock`
- `GET /database/lock-status`

These endpoints are used by the external backup service to block writes during restore windows.

## Authentication for Lock Endpoints

The lock endpoints accept either:

- `X-Admin-Key: <ADMIN_API_KEY>`
- `Authorization: Bearer <ADMIN_API_KEY_OR_TOKEN>`

This dual mode keeps compatibility with backup-restore deployments that send bearer tokens.

## Typical Restore Flow

1. External backup service calls `POST /database/lock`.
2. External backup service restores the target database.
3. External backup service calls `POST /database/unlock`.

## Notes

- Read/write blocking behavior is enforced by middleware in this API.
- Configure timeout and fail-closed behavior with:
  - `DB_LOCK_TIMEOUT_SECONDS`
  - `DB_LOCK_FAIL_CLOSED`

See [DATABASE_LOCK.md](./DATABASE_LOCK.md) for details.
