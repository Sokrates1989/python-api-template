# Startup Probes and Provider Diagnostics

This template now runs provider-specific startup probes during API startup.

## Startup sequence

1. Initialize configured database handler (`DB_TYPE`).
2. Run connection retry loop (fail-fast after max retries).
3. Run provider startup probe:
   - SQL: connectivity + dialect/model metadata summary
   - Neo4j: connectivity + component/version check
   - MongoDB: connectivity + required index verification for `users` and `examples`
4. Run SQL migrations (SQL providers only).
5. Serve requests.

If a provider probe fails, startup fails immediately.

## Health endpoint

`GET /health` now includes startup probe context:

```json
{
  "status": "OK",
  "database_type": "sql",
  "provider_profile": "sql",
  "startup_probe_status": "success"
}
```

## Structured log events

Startup/shutdown and diagnostics now emit structured key-value events, for example:

- `event=startup.begin`
- `event=database.initialize.connection_retry`
- `event=startup.provider_probe_ok`
- `event=startup.provider_probe_failed`
- `event=shutdown.complete`

HTTP debug middleware (when explicitly enabled) also emits structured events:

- `event=http.request`
- `event=http.response`

Authentication failures emit a safe warning even when HTTP debug body/header
logging is disabled:

- `event=auth.failure`

The auth event includes method, path, provider, status code, response detail,
and whether an Authorization header was present. It does not log bearer token
contents.

## Notes for external backup/restore integration

The provider startup probe complements `GET /database/provider-info`:

- `provider-info` is for external orchestrators.
- startup probes are internal readiness checks enforced before serving traffic.
